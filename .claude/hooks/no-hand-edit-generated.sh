#!/usr/bin/env bash
# Refuse edits to generated artifacts.
#
# `ontology/autofde-lab-capabilities.ttl` is produced by
# `python -m autofde_lab.fabric.ontology` from entry points + a live import probe
# + get_domain_requirements() MRO derivation. Its credibility rests on the
# probe being the same act as the use -- a hand-edit silently converts it from
# a measurement into an assertion, and `tests/ecosystem/` would then be
# checking a claim against itself.
#
# Guidance in a rules file cannot enforce this; a hook can. Exit 2 blocks the
# tool call and returns stderr to the model.
set -euo pipefail

payload=$(cat)

# Prefer jq; fall back to python3 so the hook still works without it.
if command -v jq >/dev/null 2>&1; then
  target=$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty')
else
  target=$(printf '%s' "$payload" | python3 -c \
    'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))')
fi

[ -n "$target" ] || exit 0

case "$target" in
  */ontology/autofde-lab-capabilities.ttl|ontology/autofde-lab-capabilities.ttl)
    cat >&2 <<'REFUSED'
REFUSED:GENERATED_ARTIFACT_HAND_EDIT

ontology/autofde-lab-capabilities.ttl is generated, not authored. Regenerate it:

    python -m autofde_lab.fabric.ontology ontology/autofde-lab-capabilities.ttl

If the content you intended to change is not what the generator emits, the
generator is what needs changing -- src/autofde_lab/fabric/ontology.py. Editing
the .ttl directly makes the file assert what it is supposed to measure, and
tests/ecosystem/ would then verify the ontology against itself.
REFUSED
    exit 2
    ;;
esac

exit 0
