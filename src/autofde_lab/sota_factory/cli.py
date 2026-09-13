from __future__ import annotations

import argparse
import json
from pathlib import Path

from .factory import SOTAFactory
from .io import dump_jsonl, load_results, load_spec


def _factory(spec_path: str) -> SOTAFactory:
    spec = load_spec(spec_path)
    return SOTAFactory(
        target=spec.target,
        decision_space=spec.decision_space,
        experiment_bases=spec.experiment_bases,
        baseline=spec.baseline,
        strategy=spec.strategy,
        candidate_limit=spec.candidate_limit,
        max_architectures=spec.max_architectures,
    )


def _ingest(factory: SOTAFactory, results_path: str | None) -> None:
    if results_path:
        factory.ingest(load_results(results_path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m autofde_lab.sota_factory",
        description="SELECT/LEARN SOTA factory control plane. No actuation path.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    compile_p = sub.add_parser(
        "compile", help="compile lawful experiment plans as JSONL"
    )
    compile_p.add_argument("spec")
    compile_p.add_argument("--out")

    status_p = sub.add_parser("status", help="derive scoreboard and learning signals")
    status_p.add_argument("spec")
    status_p.add_argument("--results")
    status_p.add_argument("--out")

    next_p = sub.add_parser("next", help="select next unexecuted experiment batch")
    next_p.add_argument("spec")
    next_p.add_argument("--results")
    next_p.add_argument("--batch-size", type=int, default=8)
    next_p.add_argument("--out")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    factory = _factory(args.spec)

    if args.command == "compile":
        text = dump_jsonl((plan.to_dict() for plan in factory.plans), args.out)
        if not args.out:
            print(text, end="")
        return 0

    _ingest(factory, args.results)

    if args.command == "status":
        text = json.dumps(factory.snapshot().to_dict(), indent=2, sort_keys=True) + "\n"
        if args.out:
            Path(args.out).write_text(text)
        else:
            print(text, end="")
        return 0

    if args.command == "next":
        batch = factory.next_batch(args.batch_size)
        text = dump_jsonl((plan.to_dict() for plan in batch), args.out)
        if not args.out:
            print(text, end="")
        return 0

    raise AssertionError(f"unhandled command: {args.command}")
