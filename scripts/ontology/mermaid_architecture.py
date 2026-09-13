from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from rdflib import BNode, Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef
from rdflib.namespace import DCTERMS, PROV, SKOS, XSD

ARCH = Namespace('urn:autofde-lab:architecture:')
AFL = Namespace('urn:autofde-lab:')

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRS = [ROOT / 'docs' / 'c4', ROOT / 'docs' / 'diagrams']
CATALOG_DIR = ROOT / 'ontology' / 'architecture' / 'catalog'
CORE = URIRef('urn:autofde-lab:ontology:architecture')

KIND_MAP = {
    'C4Context': ARCH.C4ContextDiagram,
    'C4Container': ARCH.C4ContainerDiagram,
    'C4Component': ARCH.C4ComponentDiagram,
    'C4Dynamic': ARCH.C4DynamicDiagram,
    'C4Deployment': ARCH.C4DeploymentDiagram,
    'sequenceDiagram': ARCH.SequenceDiagram,
    'stateDiagram-v2': ARCH.StateDiagram,
    'flowchart': ARCH.FlowDiagram,
    'classDiagram': ARCH.ClassDiagram,
    'erDiagram': ARCH.ERDiagram,
}

C4_ELEMENT_TYPES = {
    'Person': ARCH.Person,
    'System': ARCH.SoftwareSystem,
    'System_Ext': ARCH.ExternalSystem,
    'Container': ARCH.Container,
    'Component': ARCH.Component,
    'Deployment_Node': ARCH.DeploymentNode,
    'System_Boundary': ARCH.SystemBoundary,
    'Container_Boundary': ARCH.ContainerBoundary,
}

CANONICAL = {
    'gymact': ARCH.System_GymAct,
    'autofde sota lab': ARCH.System_AutoFDE_SOTA_Lab,
    'autofde lab': ARCH.System_AutoFDE_SOTA_Lab,
    'autofde runtime': ARCH.System_AutoFDE_Runtime,
    'ggen': ARCH.System_ggen,
    'external benchmarks': ARCH.System_ExternalBenchmarks,
    'external environments': ARCH.System_ExternalEnvironments,
    'external consequential worlds': ARCH.System_ExternalEnvironments,
    'researcher / operator': ARCH.Actor_ResearcherOperator,
    'authorized operator': ARCH.Actor_AuthorizedOperator,
    'independent verifier': ARCH.System_IndependentVerifier,
    'independent evidence / standing': ARCH.System_IndependentVerifier,
}


def slug(text: str) -> str:
    s = re.sub(r'[^A-Za-z0-9]+', '-', text.strip()).strip('-').lower()
    return s or 'unnamed'


def unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] == '"':
        return s[1:-1]
    return s


def split_args(arg_text: str) -> list[str]:
    out, cur, quoted, depth = [], [], False, 0
    i = 0
    while i < len(arg_text):
        ch = arg_text[i]
        if ch == '"' and (i == 0 or arg_text[i-1] != '\\'):
            quoted = not quoted
            cur.append(ch)
        elif ch == '(' and not quoted:
            depth += 1; cur.append(ch)
        elif ch == ')' and not quoted:
            depth -= 1; cur.append(ch)
        elif ch == ',' and not quoted and depth == 0:
            out.append(''.join(cur).strip()); cur = []
        else:
            cur.append(ch)
        i += 1
    if cur:
        out.append(''.join(cur).strip())
    return out


def diagram_kind(text: str):
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith('%%'):
            continue
        token = s.split()[0]
        if token in KIND_MAP:
            return KIND_MAP[token], token
    raise ValueError('Unknown Mermaid diagram kind')


def source_files() -> list[Path]:
    """The 50 catalogued sources are exactly the ``NN_*.mmd`` numbered set.

    ``docs/c4/autofde_lab_planner_*.mmd`` is deliberately unnumbered -- see
    ``docs/autofde-lab-planner-generalized-architecture.md``'s own "See also"
    section: that set is named to avoid colliding with this catalog's own
    sequence. A blanket ``*.mmd`` glob would silently pull it in (and crash
    on its unnumbered filenames), so this only matches names starting with
    digits.
    """
    files = []
    for d in SOURCE_DIRS:
        files.extend(sorted(d.glob('[0-9]*.mmd')))
    return sorted(files, key=lambda p: int(p.name.split('_', 1)[0]))


def bind(g: Graph):
    g.bind('arch', ARCH)
    g.bind('afl', AFL)
    g.bind('dcterms', DCTERMS)
    g.bind('prov', PROV)
    g.bind('skos', SKOS)
    g.bind('owl', OWL)
    g.bind('rdf', RDF)
    g.bind('rdfs', RDFS)
    g.bind('xsd', XSD)


def add_element(g: Graph, diagram: URIRef, base: str, local_id: str, label: str, cls: URIRef, line_no: int, description: str | None = None, technology: str | None = None):
    uri = BNode(slug(base.split(':diagram:')[-1].split(':')[0]) + '-e-' + slug(local_id))
    g.add((uri, RDF.type, ARCH.ArchitectureElement))
    g.add((uri, RDF.type, cls))
    g.add((uri, RDFS.label, Literal(label)))
    g.add((uri, ARCH.localIdentifier, Literal(local_id)))
    g.add((uri, ARCH.belongsToDiagram, diagram))
    g.add((diagram, ARCH.depicts, uri))
    if technology:
        g.add((uri, ARCH.technology, Literal(technology)))
    canonical = CANONICAL.get(label.strip().lower())
    if canonical:
        g.add((uri, ARCH.refersTo, canonical))
    return uri


def add_relationship(g: Graph, diagram: URIRef, base: str, idx: int, src: URIRef, dst: URIRef, kind: URIRef, label: str | None, line_no: int, seq: int | None = None, notation: str | None = None):
    rel = BNode(slug(base.split(':diagram:')[-1].split(':')[0]) + f'-r-{idx:04d}')
    g.add((rel, RDF.type, ARCH.Relationship))
    g.add((rel, RDF.type, kind))
    g.add((rel, ARCH.source, src))
    g.add((rel, ARCH.target, dst))
    g.add((rel, ARCH.belongsToDiagram, diagram))
    if label:
        g.add((rel, RDFS.label, Literal(label.strip())))
    if seq is not None:
        g.add((rel, ARCH.sequenceIndex, Literal(seq, datatype=XSD.integer)))
    if notation:
        g.add((rel, ARCH.notation, Literal(notation)))
    return rel


def ensure_node(g, diagram, base, nodes, local_id, label=None, cls=ARCH.ArchitectureElement, line_no=0):
    if local_id not in nodes:
        nodes[local_id] = add_element(g, diagram, base, local_id, label or local_id, cls, line_no)
    return nodes[local_id]


def parse_c4(g, diagram, base, text):
    nodes = {}; rel_idx = 0
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line.startswith('title '):
            g.set((diagram, DCTERMS.title, Literal(line[6:].strip())))
        m = re.match(r'(?P<fn>Person|System|System_Ext|Container|Component|Deployment_Node|System_Boundary|Container_Boundary)\((?P<args>.*)\)\s*\{?$', line)
        if m:
            args = split_args(m.group('args'))
            if not args: continue
            local_id = args[0].strip()
            label = unquote(args[1]) if len(args) > 1 else local_id
            technology = None; desc = None
            if m.group('fn') in {'Container', 'Component'}:
                technology = unquote(args[2]) if len(args) > 2 else None
                desc = unquote(args[3]) if len(args) > 3 else None
            elif m.group('fn') == 'Deployment_Node':
                desc = unquote(args[2]) if len(args) > 2 else None
            else:
                desc = unquote(args[2]) if len(args) > 2 else None
            nodes[local_id] = add_element(g, diagram, base, local_id, label, C4_ELEMENT_TYPES[m.group('fn')], n, desc, technology)
            continue
        m = re.match(r'Rel\((?P<args>.*)\)$', line)
        if m:
            args = split_args(m.group('args'))
            if len(args) >= 2:
                src_id, dst_id = args[0].strip(), args[1].strip()
                label = unquote(args[2]) if len(args) > 2 else None
                src = ensure_node(g, diagram, base, nodes, src_id, line_no=n)
                dst = ensure_node(g, diagram, base, nodes, dst_id, line_no=n)
                rel_idx += 1
                add_relationship(g, diagram, base, rel_idx, src, dst, ARCH.ArchitectureRelationship, label, n, notation='Rel')
    return nodes, rel_idx


def parse_sequence(g, diagram, base, text):
    nodes = {}; rel_idx = 0; seq = 0
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        m = re.match(r'(actor|participant)\s+([A-Za-z0-9_]+)\s+as\s+(.+)$', line)
        if m:
            cls = ARCH.Actor if m.group(1) == 'actor' else ARCH.Participant
            nodes[m.group(2)] = add_element(g, diagram, base, m.group(2), m.group(3).strip(), cls, n)
            continue
        m = re.match(r'([A-Za-z0-9_]+)([-.]+>>?|[-.]+>)([A-Za-z0-9_]+):\s*(.+)$', line)
        if m:
            src_id, notation, dst_id, label = m.groups()
            src = ensure_node(g, diagram, base, nodes, src_id, cls=ARCH.Participant, line_no=n)
            dst = ensure_node(g, diagram, base, nodes, dst_id, cls=ARCH.Participant, line_no=n)
            seq += 1; rel_idx += 1
            add_relationship(g, diagram, base, rel_idx, src, dst, ARCH.Message, label, n, seq, notation)
    return nodes, rel_idx


def parse_state(g, diagram, base, text):
    nodes = {}; rel_idx = 0
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        m = re.match(r'(.+?)\s+-->\s+(.+?)(?::\s*(.*))?$', line)
        if not m or line.startswith('stateDiagram'): continue
        src_id, dst_id, label = [x.strip() if x is not None else None for x in m.groups()]
        src_key = 'initial' if src_id == '[*]' else src_id
        dst_key = 'final' if dst_id == '[*]' else dst_id
        src_cls = ARCH.Pseudostate if src_id == '[*]' else ARCH.State
        dst_cls = ARCH.Pseudostate if dst_id == '[*]' else ARCH.State
        src = ensure_node(g, diagram, base, nodes, src_key, src_id, src_cls, n)
        dst = ensure_node(g, diagram, base, nodes, dst_key, dst_id, dst_cls, n)
        rel_idx += 1
        add_relationship(g, diagram, base, rel_idx, src, dst, ARCH.StateTransition, label, n, notation='-->')
    return nodes, rel_idx

NODE_RE = re.compile(r'([A-Za-z0-9_]+)(?:\["([^"]*)"\]|\[([^\]]*)\]|\{"([^"]*)"\}|\{([^}]*)\})?')

def parse_flow(g, diagram, base, text):
    nodes = {}; rel_idx = 0
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('flowchart') or line.startswith('%%'): continue
        m = re.match(r'(.+?)\s+(-\.->|-->|-.->|==>|---)(?:\s*\|([^|]*)\|)?\s+(.+)$', line)
        if not m:
            m = re.match(r'(.+?)\s+--\s+"?([^"]*?)"?\s+-->\s+(.+)$', line)
            if m:
                left, label, right = m.group(1), m.group(2), m.group(3); notation='-->'
            else:
                continue
        else:
            left, notation, label, right = m.groups()
        def parse_node(expr):
            mm = NODE_RE.search(expr.strip())
            if not mm: return expr.strip(), expr.strip()
            node_id = mm.group(1)
            labelv = next((x for x in mm.groups()[1:] if x is not None), None) or node_id
            labelv = labelv.replace('<br/>', ' / ')
            return node_id, labelv
        s_id, s_label = parse_node(left); d_id, d_label = parse_node(right)
        src = ensure_node(g, diagram, base, nodes, s_id, s_label, ARCH.FlowNode, n)
        dst = ensure_node(g, diagram, base, nodes, d_id, d_label, ARCH.FlowNode, n)
        rel_idx += 1
        add_relationship(g, diagram, base, rel_idx, src, dst, ARCH.FlowEdge, label, n, notation=notation)
    return nodes, rel_idx


def parse_class(g, diagram, base, text):
    nodes = {}; rel_idx = 0; current = None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        m = re.match(r'class\s+([A-Za-z0-9_]+)\s*\{?', line)
        if m:
            current = m.group(1)
            nodes[current] = add_element(g, diagram, base, current, current, ARCH.ModelClass, n)
            continue
        if line == '}': current = None; continue
        if current and (line.startswith('+') or line.startswith('-') or line.startswith('#') or ':' in line):
            attr = BNode(slug(base.split(':diagram:')[-1].split(':')[0]) + '-cm-' + slug(current) + '-' + hashlib.sha1(line.encode()).hexdigest()[:10])
            g.add((attr, RDF.type, ARCH.ClassMember))
            g.add((attr, RDFS.label, Literal(line)))
            g.add((attr, ARCH.belongsToClass, nodes[current]))
            g.add((attr, ARCH.belongsToDiagram, diagram))
            continue
        m = re.match(r'([A-Za-z0-9_]+)(?:\s+"([^"]*)")?\s+([^\s]+)\s+(?:"([^"]*)"\s+)?([A-Za-z0-9_]+)(?:\s*:\s*(.*))?$', line)
        if m and any(x in m.group(3) for x in ['--', '..', '<|', '*--', 'o--']):
            s_id, s_card, notation, d_card, d_id, label = m.groups()
            src = ensure_node(g, diagram, base, nodes, s_id, cls=ARCH.ModelClass, line_no=n)
            dst = ensure_node(g, diagram, base, nodes, d_id, cls=ARCH.ModelClass, line_no=n)
            rel_idx += 1
            rel = add_relationship(g, diagram, base, rel_idx, src, dst, ARCH.ClassRelationship, label, n, notation=notation)
            if s_card: g.add((rel, ARCH.sourceCardinality, Literal(s_card)))
            if d_card: g.add((rel, ARCH.targetCardinality, Literal(d_card)))
    return nodes, rel_idx


def parse_er(g, diagram, base, text):
    nodes = {}; rel_idx = 0; current = None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        m = re.match(r'([A-Z][A-Z0-9_]*)\s*\{', line)
        if m:
            current = m.group(1)
            nodes[current] = add_element(g, diagram, base, current, current, ARCH.DataEntity, n)
            continue
        if line == '}': current = None; continue
        if current and line:
            parts = line.split()
            if len(parts) >= 2:
                attr_name = parts[1]
                attr = BNode(slug(base.split(':diagram:')[-1].split(':')[0]) + '-da-' + slug(current) + '-' + slug(attr_name))
                g.add((attr, RDF.type, ARCH.DataAttribute))
                g.add((attr, RDFS.label, Literal(attr_name)))
                g.add((attr, ARCH.dataType, Literal(parts[0])))
                g.add((attr, ARCH.belongsToEntity, nodes[current]))
                g.add((attr, ARCH.belongsToDiagram, diagram))
                if len(parts) > 2:
                    g.add((attr, ARCH.keyMarker, Literal(' '.join(parts[2:]))))
            continue
        m = re.match(r'([A-Z][A-Z0-9_]*)\s+([^\s]+)\s+([A-Z][A-Z0-9_]*)\s*:\s*(.+)$', line)
        if m:
            s_id, notation, d_id, label = m.groups()
            src = ensure_node(g, diagram, base, nodes, s_id, cls=ARCH.DataEntity, line_no=n)
            dst = ensure_node(g, diagram, base, nodes, d_id, cls=ARCH.DataEntity, line_no=n)
            rel_idx += 1
            add_relationship(g, diagram, base, rel_idx, src, dst, ARCH.EntityRelationship, label, n, notation=notation)
    return nodes, rel_idx

PARSERS = {
    'C4Context': parse_c4,
    'C4Container': parse_c4,
    'C4Component': parse_c4,
    'C4Dynamic': parse_c4,
    'C4Deployment': parse_c4,
    'sequenceDiagram': parse_sequence,
    'stateDiagram-v2': parse_state,
    'flowchart': parse_flow,
    'classDiagram': parse_class,
    'erDiagram': parse_er,
}


def build(source: Path) -> Graph:
    text = source.read_text(encoding='utf-8')
    kind_uri, token = diagram_kind(text)
    rel_source = source.relative_to(ROOT).as_posix()
    stem = source.stem
    base = f'urn:autofde-lab:architecture:diagram:{stem}:'
    diagram = URIRef(base + 'diagram')
    g = Graph(); bind(g)
    g.add((diagram, RDF.type, ARCH.Diagram))
    g.add((diagram, RDF.type, kind_uri))
    g.add((diagram, ARCH.diagramKind, kind_uri))
    g.add((diagram, ARCH.sourcePath, Literal(rel_source)))
    g.add((diagram, ARCH.sourceDigest, Literal(hashlib.sha256(text.encode()).hexdigest())))
    g.add((diagram, ARCH.mermaidSyntax, Literal(token)))
    g.add((diagram, PROV.wasDerivedFrom, URIRef(f'https://github.com/seanchatmangpt/autofde-lab/blob/master/{rel_source}')))
    g.add((diagram, DCTERMS.title, Literal(source.stem.replace('_', ' '))))
    nodes, rels = PARSERS[token](g, diagram, base, text)
    g.set((diagram, ARCH.elementCount, Literal(len(nodes), datatype=XSD.integer)))
    g.set((diagram, ARCH.relationshipCount, Literal(rels, datatype=XSD.integer)))
    g.set((diagram, ARCH.parseStanding, Literal('PARSED')))
    return g


def serialize(g: Graph) -> str:
    return g.serialize(format='turtle')


def group_for(source: Path) -> str:
    n = int(source.name.split('_', 1)[0])
    if 1 <= n <= 5: return '01_c4_ecosystem'
    if 6 <= n <= 10: return '02_c4_sota_lab'
    if 11 <= n <= 15: return '03_c4_gymact'
    if 16 <= n <= 20: return '04_c4_autofde_runtime'
    if 21 <= n <= 25: return '05_c4_ggen'
    if 26 <= n <= 30: return '06_sequence'
    if 31 <= n <= 35: return '07_state'
    if 36 <= n <= 40: return '08_flow'
    if 41 <= n <= 45: return '09_class'
    if 46 <= n <= 50: return '10_er'
    raise ValueError(source)


def build_detail_bundle(name: str, sources: list[Path]) -> Graph:
    g = Graph(); bind(g)
    ontology = URIRef(f'urn:autofde-lab:architecture:detail-bundle:{name}')
    g.add((ontology, RDF.type, OWL.Ontology))
    g.add((ontology, OWL.imports, CORE))
    g.add((ontology, DCTERMS.title, Literal(f'Generated detailed architecture graph bundle: {name}')))
    for src in sources:
        sg = build(src)
        for triple in sg:
            g.add(triple)
    return g


def build_catalog_bundle(name: str, sources: list[Path]) -> Graph:
    g = Graph(); bind(g)
    ontology = URIRef(f'urn:autofde-lab:architecture:catalog:{name}')
    g.add((ontology, RDF.type, OWL.Ontology))
    g.add((ontology, OWL.imports, CORE))
    g.add((ontology, DCTERMS.title, Literal(f'Generated architecture catalog bundle: {name}')))
    for src in sources:
        sg = build(src)
        diagram = next(sg.subjects(RDF.type, ARCH.Diagram))
        for predicate in (
            RDF.type, DCTERMS.title, ARCH.diagramKind, ARCH.sourcePath,
            ARCH.sourceDigest, ARCH.mermaidSyntax, ARCH.elementCount,
            ARCH.relationshipCount, ARCH.parseStanding,
        ):
            for value in sg.objects(diagram, predicate):
                g.add((diagram, predicate, value))
    return g


def grouped_sources() -> dict[str, list[Path]]:
    sources = source_files()
    if len(sources) != 50:
        raise SystemExit(f'expected exactly 50 Mermaid sources, found {len(sources)}')
    groups: dict[str, list[Path]] = {}
    for src in sources:
        groups.setdefault(group_for(src), []).append(src)
    if len(groups) != 10 or any(len(v) != 5 for v in groups.values()):
        raise SystemExit(f'expected ten groups of five, got {[(k, len(v)) for k, v in groups.items()]}')
    return groups


def generate_catalog(check: bool = False) -> int:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    drift = []
    for name, sources in sorted(grouped_sources().items()):
        out = CATALOG_DIR / f'{name}.ttl'
        rendered = serialize(build_catalog_bundle(name, sources))
        if check:
            if not out.exists() or out.read_text(encoding='utf-8') != rendered:
                drift.append(out)
        else:
            out.write_text(rendered, encoding='utf-8')
    if drift:
        print('architecture ontology drift:')
        for p in drift:
            print(p.relative_to(ROOT))
        return 1
    return 0


def emit_detail(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, sources in sorted(grouped_sources().items()):
        (directory / f'{name}.ttl').write_text(
            serialize(build_detail_bundle(name, sources)), encoding='utf-8'
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--detail-dir', type=Path)
    args = ap.parse_args()
    rc = generate_catalog(check=args.check)
    if rc == 0 and args.detail_dir is not None:
        emit_detail(args.detail_dir)
    raise SystemExit(rc)

if __name__ == '__main__':
    main()
