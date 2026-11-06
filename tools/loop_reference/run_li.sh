#!/usr/bin/env bash
# SPDX-License-Identifier: 0BSD
# One loop-induced reference end to end (li_references.py): points, MadLoop export,
# the MadLoop reference run (1e-11, helicity filter off, every helicity), Recola,
# OpenLoops (where the specification names a library), the analytic oracles,
# merge and the committed fixture. Steps already done are kept (rerun to resume).
# Every provider step runs under timeout (default 2700 s, REQUIREMENTS_ADDENDUM F);
# a timeout is recorded as a 45-minute miss in <step>.status.json.
#   run_li.sh <process> <cpu> [fixture-dir]
set -u
process=$1
cpu=$2
here=$(cd "$(dirname "$0")" && pwd)
root=${LOOP_REFERENCE_ROOT:?set LOOP_REFERENCE_ROOT}
fixtures=${3:-$here/../../tests/fixtures/loop/required/li}
python=${LOOP_REFERENCE_PYTHON:-python3}
limit=${LI_TIMEOUT:-2700}
work=$root/runs/li/$process
mkdir -p "$work"
cd "$work" || exit 1
spec() { "$python" -I -c "import json,sys; sys.path.insert(0,'$here'); import required_spec as r; \
p=r.load_process(r.DEFAULT_SPEC,'$process'); print($1)"; }
step() {  # step <label> <command...>
  local label=$1; shift
  if [ -f "$work/$label.done" ]; then return 0; fi
  local start=$(date +%s)
  timeout "$limit" "$@" > "$work/$label.log" 2>&1
  local rc=$?
  local wall=$(( $(date +%s) - start ))
  if [ $rc -eq 124 ]; then
    printf '{"step": "%s", "returncode": 124, "wall_seconds": %s, "miss": "45-minute rule: %s did not finish within %s s"}\n' \
      "$label" "$wall" "$label" "$limit" > "$work/$label.status.json"
  else
    printf '{"step": "%s", "returncode": %s, "wall_seconds": %s}\n' "$label" "$rc" "$wall" > "$work/$label.status.json"
  fi
  [ $rc -eq 0 ] && touch "$work/$label.done"
  return $rc
}
li="$python $here/li_references.py"
step points $li points --process "$process" --output "$work/points.json" || exit 1
if [ ! -f "$work/madloop-export.generation.json" ] || ! grep -q '"compiled"' "$work/madloop-export.generation.json"; then
  [ -d "$work/madloop-export" ] && [ ! -f "$work/export.done" ] && { echo "incomplete export at $work/madloop-export: remove it to retry" >&2; exit 1; }
  step export $li export --process "$process" --mg5 "$root/sources/MG5_aMC_v3_7_0" --output "$work/madloop-export" \
    --timeout "$limit" || echo "MadLoop export failed" >&2
fi
if [ -f "$work/export.done" ] || grep -q '"compiled"' "$work/madloop-export.generation.json" 2>/dev/null; then
  step madloop $li run --process "$process" --provider madloop --points "$work/points.json" --work-dir "$work" \
    --mg5 "$root/sources/MG5_aMC_v3_7_0" --madloop-export "$work/madloop-export" --helicities --cpu "$cpu" \
    --reference-root "$root" || echo "MadLoop run failed" >&2
fi
[ "$(spec "'unavailable' in p['recola']")" = True ] || step recola $li run --process "$process" --provider recola --points "$work/points.json" --work-dir "$work" \
  --recola "${LOOP_REFERENCE_RECOLA:-$root/sources/recola2-2.3.0}" --cpu "$cpu" --reference-root "$root" \
  || echo "Recola run failed" >&2
if [ "$(spec "'library' in p.get('openloops', {})")" = True ]; then
  step openloops $li run --process "$process" --provider openloops --points "$work/points.json" --work-dir "$work" \
    --openloops "${LOOP_REFERENCE_OPENLOOPS:-$root/sources/OpenLoops-2.1.5}" --cpu "$cpu" --reference-root "$root" \
    || echo "OpenLoops run failed" >&2
fi
if [ "$(spec "bool(p.get('analytic') or p.get('analytic_limit'))")" = True ]; then
  step analytic $li run --process "$process" --provider analytic --points "$work/points.json" --work-dir "$work" \
    || echo "analytic oracle failed" >&2
fi
$li merge --process "$process" --points "$work/points.json" --work-dir "$work" --output "$work/reference.json" \
  && $li fixture --reference "$work/reference.json" --output "$fixtures/$process.json" --reference-root "$root"
