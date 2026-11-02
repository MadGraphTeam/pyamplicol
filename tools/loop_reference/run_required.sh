#!/usr/bin/env bash
# SPDX-License-Identifier: 0BSD
# Evaluate one provider for one required process and refresh its merged JSON.
#   run_required.sh <process> <madloop|recola|openloops> [cpu]
# Work directory: $LOOP_REFERENCE_ROOT/runs/required/<process>/ holding
# points.json (created if absent), madloop-export/ (from madloop_export.py),
# <provider>-run/ logs, <provider>-result.json, status-<provider>.json and
# reference.json. LOOP_REFERENCE_RECOLA / LOOP_REFERENCE_OPENLOOPS override the
# provider trees (e.g. a patched Recola build).
set -euo pipefail
process=$1
provider=$2
cpu=${3:-}
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=${LOOP_REFERENCE_ROOT:?set LOOP_REFERENCE_ROOT to the workspace reference directory}
python=${LOOP_REFERENCE_PYTHON:-python3}
work=$root/runs/required/$process
mkdir -p "$work"
if [ ! -f "$work/points.json" ]; then
  "$python" "$here/exact_points.py" --process "$process" --output "$work/points.json"
fi
"$python" "$here/references.py" run --process "$process" --points "$work/points.json" \
  --work-dir "$work" --provider "$provider" --reference-root "$root" \
  --mg5 "$root/sources/MG5_aMC_v3_7_0" \
  --madloop-export "$work/madloop-export" \
  --recola "${LOOP_REFERENCE_RECOLA:-$root/sources/recola2-2.3.0}" \
  --openloops "${LOOP_REFERENCE_OPENLOOPS:-$root/sources/OpenLoops-2.1.5}" ${cpu:+--cpu "$cpu"}
"$python" "$here/references.py" merge --process "$process" --points "$work/points.json" \
  --work-dir "$work" --output "$work/reference.json" || true
