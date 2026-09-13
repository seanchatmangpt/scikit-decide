#!/usr/bin/env bash
# orphan_sweep.sh -- AUTHORED, NEVER RUN.
#
# Standing: NOT_RUN.
#   BLOCKED:AZURE_CLI_ABSENT              -- `which az` returns nothing here.
#   BLOCKED:NO_APPROVED_TEST_SUBSCRIPTION -- nothing has ever been created.
# Both blockers must clear independently. Nothing this script would delete
# exists, so its delete path has never executed and is UNVERIFIED.
#
# Purpose: find and (with an explicit flag) remove resource groups left over
# from an ephemeral autofde-breach-clock run, keyed on the `run` and `expiry`
# tags that main.tf stamps on every resource.
#
# `run` is a NEW CONVENTION in this codebase -- no existing IaC under ~ has a
# run_id concept; the nearest existing idiom is random_string.suffix, which
# is unusable for sweeping because the operator never holds the value.
#
# DRY RUN IS THE DEFAULT. --delete must be passed explicitly, and even then
# the script refuses any group whose name lacks the skd-autofde-test- prefix.

set -euo pipefail

PREFIX="skd-autofde-test-"
DELETE=0
RUN_ID=""
BEFORE="$(date -u +%Y-%m-%d)"
SUBSCRIPTION=""

usage() {
  cat <<'USAGE'
usage: orphan_sweep.sh --subscription <guid> [--run-id <id>] [--before YYYY-MM-DD] [--delete]

  --subscription  REQUIRED. Target subscription id, supplied explicitly.
                  The active `az` CLI context is never used to infer one.
  --run-id        Sweep only resources tagged run=<id>. Omit to sweep all
                  expired runs.
  --before        Treat expiry tags strictly before this date as orphans.
                  Defaults to today (UTC).
  --delete        Actually delete. Without it this script only lists.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --subscription) SUBSCRIPTION="${2:-}"; shift 2 ;;
    --run-id)       RUN_ID="${2:-}";       shift 2 ;;
    --before)       BEFORE="${2:-}";       shift 2 ;;
    --delete)       DELETE=1;              shift   ;;
    -h|--help)      usage; exit 0 ;;
    *) echo "REFUSED: unknown argument $1" >&2; usage >&2; exit 2 ;;
  esac
done

if ! command -v az >/dev/null 2>&1; then
  echo "UNSUPPORTED:AZURE_CLI_ABSENT -- az is not on PATH." >&2
  exit 3
fi

if [[ -z "$SUBSCRIPTION" ]]; then
  # Refusal-first: no fallback to `az account show`. An operator with a
  # production context selected must not be able to sweep by omission.
  echo "REFUSED: --subscription is required and is never inferred from the active az context." >&2
  exit 2
fi

if [[ ! "$BEFORE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "REFUSED: --before must be YYYY-MM-DD." >&2
  exit 2
fi

query="[?starts_with(name, '${PREFIX}')]"
if [[ -n "$RUN_ID" ]]; then
  query="[?starts_with(name, '${PREFIX}') && tags.run == '${RUN_ID}']"
fi

echo "# subscription : ${SUBSCRIPTION}"
echo "# prefix       : ${PREFIX}"
echo "# run filter   : ${RUN_ID:-<all>}"
echo "# expiry before: ${BEFORE}"
echo "# mode         : $([[ $DELETE -eq 1 ]] && echo DELETE || echo DRY-RUN)"

az group list \
  --subscription "$SUBSCRIPTION" \
  --query "${query}.{name:name, run:tags.run, expiry:tags.expiry, owner:tags.owner}" \
  -o tsv |
while IFS=$'\t' read -r name run expiry owner; do
  [[ -z "${name:-}" ]] && continue

  # Belt and braces: the JMESPath filter already constrains the prefix, but
  # a deletion path must re-check locally rather than trust a remote query.
  if [[ "$name" != "$PREFIX"* ]]; then
    echo "SKIP  ${name} -- prefix guard (this should be unreachable)"
    continue
  fi

  if [[ -z "${expiry:-}" || "$expiry" == "None" ]]; then
    echo "SKIP  ${name} -- no expiry tag; refusing to sweep an untagged group"
    continue
  fi

  if [[ ! "$expiry" < "$BEFORE" ]]; then
    echo "KEEP  ${name} (run=${run} expiry=${expiry} owner=${owner}) -- not yet expired"
    continue
  fi

  if [[ $DELETE -eq 1 ]]; then
    echo "DELETE ${name} (run=${run} expiry=${expiry} owner=${owner})"
    az group delete --subscription "$SUBSCRIPTION" --name "$name" --yes --no-wait
  else
    echo "ORPHAN ${name} (run=${run} expiry=${expiry} owner=${owner}) -- would delete; pass --delete"
  fi
done
