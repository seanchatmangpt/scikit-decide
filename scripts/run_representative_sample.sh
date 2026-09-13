#!/bin/bash
# Re-run of the 2026-08-09 stride-5 unbiased 25-problem representative sample,
# with new detector/remediator coverage (anti-affinity, CoreDNS, CronJob,
# ingress/targetPort, rolling-update-misconfig) wired in. Same problem list,
# same --agent-timeout 600 / outer timeout 750 as the original measurement.
#
# Hardened 2026-08-09 after a real failure this session: the first launch
# omitted AGENT_API_BASE/AGENT_API_KEY, so all 25 trials would have burned
# their full timeout failing a judge auth pre-flight in ~35s each, with the
# failure only visible by reading a per-problem log after the fact. This
# version front-loads every check that failure would have caught in <5s
# instead of ~5 hours, and aborts the WHOLE batch (not just one problem) on
# a systemic signature so a config error can't silently consume the run.
set -uo pipefail
cd "$(dirname "$0")/../vendor/gyms/sregym" || exit 1

export AGENT_API_BASE="http://127.0.0.1:8080/v1"
export AGENT_API_KEY="local"

# Real-time OCEL 2.0 process telemetry, one .ocel2.sqlite per problem, flushed
# live as each kubectl/submit call completes (see
# src/autofde_lab/ocel/live_flush.py and driver.py's call_kubectl/submit
# instrumentation). This is the same default driver.py computes on its own
# (via importlib.util.find_spec against the real autofde_lab package
# location) -- set explicitly here so the batch's output location is visible
# in one place rather than only inside the vendored submodule.
# Live report at any point: .venv/bin/python scripts/ocel_procint_report.py
export AUTOFDE_OCEL_DIR="/Users/sac/autofde-lab/docs/ocel/sregym"

OUT="/Users/sac/autofde-lab/docs/2026-08-09-representative-sample-batch-results-v2.tsv"
LOGDIR="/Users/sac/autofde-lab/logs"

# ---- Pre-flight (fails fast, before touching the cluster or burning any timeout) ----

preflight_fail() {
  echo "PREFLIGHT FAILED: $1" >&2
  exit 1
}

[ -x ".venv/bin/python" ] || preflight_fail "vendor/gyms/sregym/.venv/bin/python not found/executable"
[ -f "main.py" ] || preflight_fail "main.py not found in $(pwd)"

[ -n "${AGENT_API_BASE:-}" ] || preflight_fail "AGENT_API_BASE not set"
[ -n "${AGENT_API_KEY:-}" ] || preflight_fail "AGENT_API_KEY not set"

judge_health_url="${AGENT_API_BASE%/v1}/health"
if ! curl -s -m 5 -o /dev/null -w "%{http_code}" "$judge_health_url" 2>/dev/null | grep -q "^200$"; then
  preflight_fail "judge server not reachable/healthy at $judge_health_url"
fi

if ! kubectl cluster-info >/dev/null 2>&1; then
  preflight_fail "kubectl cluster-info failed -- no reachable k8s cluster"
fi

echo "PREFLIGHT OK: judge=$AGENT_API_BASE reachable, cluster reachable, venv present" >&2

# ---- Fatal-signature early-abort watcher ----
# Patterns that mean "this problem cannot possibly produce a real result" --
# no point waiting out the full 750s timeout to discover it.
FATAL_PATTERNS='AuthenticationError|Judge pre-flight check failed|ModuleNotFoundError|Traceback \(most recent call last\)|ConnectionRefusedError|ImportError:'

# Consecutive fatal-abort count that trips a whole-batch stop (a systemic
# config/env problem, not a per-problem benchmark failure).
CONSECUTIVE_FATAL_LIMIT=2
consecutive_fatal=0

PROBLEMS=(
  admission_webhook_outage_hotel_reservation
  astronomy_shop_ad_service_image_slow_load
  astronomy_shop_payment_service_unreachable
  cfs_cpu_throttling_hotel_reservation
  duplicate_pvc_mounts_astronomy_shop
  ephemeral_port_range_hotel_reservation
  finalizer_deadlock_controller_hotel_reservation
  ingress_misroute
  k8s_target_port-misconfig
  kubelet_eviction_threshold_misconfig
  liveness_probe_too_aggressive_astronomy_shop
  misconfig_app_hotel_res
  missing_service_hotel_reservation
  nightly_rebalance_oom_hotel_reservation
  operator_overload_replicas
  pod_anti_affinity_deadlock
  pvc_claim_mismatch
  resource_request_too_large
  rolling_update_misconfigured_social_network
  service_dns_resolution_failure_social_network
  sidecar_port_conflict_astronomy_shop
  stale_coredns_config_social_network
  trainticket_f22_sql_column_name_mismatch_error
  workload_imbalance
  wrong_service_selector_astronomy_shop
)

echo -e "problem_id\tdiagnosis_success\tdiagnosis_score\tmitigation_success\tstatus" > "$OUT"

for p in "${PROBLEMS[@]}"; do
  echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] START $p ===" >&2
  logfile="${LOGDIR}/repsample_v2_${p}.log"
  : > "$logfile"
  iter_start=$SECONDS

  .venv/bin/python main.py --agent autofde_lab_planner \
    --model "openai/gemma-4-26b-a4b-it" \
    --problem "$p" \
    --agent-timeout 600 \
    >> "$logfile" 2>&1 &
  pypid=$!

  # Grace window: watch the log for a fatal signature for up to 60s before
  # committing to the full 750s wait. Real trials are still deploying infra
  # at 60s (confirmed this session); a fatal config error surfaces in <40s.
  fatal_hit=""
  grace_deadline=$((iter_start + 60))
  while [ $SECONDS -lt $grace_deadline ]; do
    if ! kill -0 "$pypid" 2>/dev/null; then
      break  # process already exited (fast real completion or fast crash)
    fi
    if grep -qE "$FATAL_PATTERNS" "$logfile" 2>/dev/null; then
      fatal_hit=$(grep -oE "$FATAL_PATTERNS" "$logfile" | head -1)
      break
    fi
    sleep 2
  done

  if [ -n "$fatal_hit" ]; then
    echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] EARLY-ABORT $p: fatal signature '$fatal_hit' ===" >&2
    kill "$pypid" 2>/dev/null
    wait "$pypid" 2>/dev/null
    echo -e "${p}\t?\t?\t?\tEARLY_ABORT_FATAL:${fatal_hit}" >> "$OUT"
    consecutive_fatal=$((consecutive_fatal + 1))
    if [ "$consecutive_fatal" -ge "$CONSECUTIVE_FATAL_LIMIT" ]; then
      echo "=== BATCH ABORTED: $consecutive_fatal consecutive fatal signatures -- systemic issue, not a per-problem failure. Fix and re-run rather than burning the remaining problems. ===" >&2
      exit 2
    fi
    continue
  fi

  consecutive_fatal=0
  elapsed=$((SECONDS - iter_start))
  timeout_remaining=$((750 - elapsed))
  [ "$timeout_remaining" -lt 60 ] && timeout_remaining=60
  ( sleep "$timeout_remaining"; kill "$pypid" 2>/dev/null ) &
  killer=$!
  wait "$pypid" 2>/dev/null
  rc=$?
  kill "$killer" 2>/dev/null
  wait "$killer" 2>/dev/null

  echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] END $p rc=$rc ===" >&2

  csvfile=$(find results -iname "${p}_autofde_lab_planner_results.csv" -newer /tmp/repsample_v2_marker 2>/dev/null | sort | tail -1)
  if [ -z "$csvfile" ]; then
    csvfile=$(find results -iname "${p}_autofde_lab_planner_results.csv" 2>/dev/null | sort | tail -1)
  fi
  if [ -n "$csvfile" ] && [ -f "$csvfile" ]; then
    dsucc=$(.venv/bin/python -c "import csv; r=list(csv.DictReader(open('$csvfile'))); print(r[-1].get('Diagnosis.success','?') if r else '?')")
    dscore=$(.venv/bin/python -c "import csv; r=list(csv.DictReader(open('$csvfile'))); print(r[-1].get('Diagnosis.composite_score','?') if r else '?')")
    msucc=$(.venv/bin/python -c "import csv; r=list(csv.DictReader(open('$csvfile'))); print(r[-1].get('Mitigation.success','?') if r else '?')")
    echo -e "${p}\t${dsucc}\t${dscore}\t${msucc}\tOK_rc${rc}" >> "$OUT"
  else
    echo -e "${p}\t?\t?\t?\tNO_CSV_rc${rc}" >> "$OUT"
  fi
  touch /tmp/repsample_v2_marker
done
echo "=== BATCH COMPLETE ===" >&2
