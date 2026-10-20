#!/usr/bin/env bash
# SPDX-License-Identifier: 0BSD
# Build an isolated Recola2 copy with recola_colorbranch.patch applied (fixes the
# colorBranch overflow in makeSkeleton at seven gluons; see README).
#   build_recola_patched.sh <recola-source-tree> <collier-dir> <modelfile-dir> <new-output-dir> [jobs]
# <collier-dir>/<modelfile-dir> hold the built Collier and Recola model (their
# *Config.cmake). The output directory must not exist; it receives src-tree/
# (patched source copy; Recola writes librecola.so there), build/ (CMake build
# dir with cmake.log/make.log), the applied patch and the original
# skeleton_rcl.f90. Select the result with
# LOOP_REFERENCE_RECOLA=<new-output-dir>/src-tree.
set -euo pipefail
src=$(cd "$1" && pwd)
collier=$(cd "$2" && pwd)
modelfile=$(cd "$3" && pwd)
out=$4
jobs=${5:-8}
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [ -e "$out" ]; then
  echo "refusing to overwrite $out" >&2
  exit 1
fi
mkdir -p "$out"
out=$(cd "$out" && pwd)
# Copy the sources only: libraries and Fortran modules are rebuilt.
cp -a "$src" "$out/src-tree"
find "$out/src-tree" -type f \( -name '*.so' -o -name '*.so.*' -o -name '*.mod' \) -delete
cp "$src/src/core/skeleton_rcl.f90" "$out/skeleton_rcl.f90.orig"
cp "$here/recola_colorbranch.patch" "$out/colorbranch.patch"
patch --forward "$out/src-tree/src/core/skeleton_rcl.f90" < "$here/recola_colorbranch.patch"
mkdir "$out/build"
cmake -S "$out/src-tree" -B "$out/build" -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -Dcollier_path="$collier" -Dmodelfile_path="$modelfile" > "$out/build/cmake.log" 2>&1
make -C "$out/build" -j"$jobs" > "$out/build/make.log" 2>&1
test -f "$out/src-tree/librecola.so"
echo "$out/src-tree"
