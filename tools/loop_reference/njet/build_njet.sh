#!/usr/bin/env bash
# Release build of QD and NJet (one-loop numerical library, 2->5 channels and
# double-double precision enabled; no analytic or two-loop parts).
#
#   build_njet.sh <njet-source> <qd-source|-> <new-build-dir> [jobs] [extra configure args]
#
# <njet-source> and <qd-source> are extracted release tarballs from
# https://bitbucket.org/njet/njet/downloads/ and
# https://www.davidhbailey.com/dhbsoftware/ (NJet 3.x needs an external QD
# >= 2.3.23; NJet 2.x bundles its own copy in lib-qd: pass "-"). The build
# directory must not exist; it receives qd/{build,prefix} (NJet 3 only),
# njet/{build,prefix}, the logs and build-info.txt (compiler, flags, configure
# lines, timings). Everything is built out of tree; the sources are not
# modified.
#
# NJet's configure adds "-std=c++17 -O2 -march=native -mtune=native" itself
# (configure.ac NJET_CXXFLAGS); its Makefiles lower the 2->5 colour-sum
# libraries to -O1 (double) and -O0 (double-double) as shipped. The library is
# therefore tuned to the build host; it is a host-local reference, not a
# portable artefact. The toolchain is the workspace gcc 15.2.0 (env.sh).
set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "usage: $0 <njet-source> <qd-source> <new-build-dir> [jobs]" >&2
  exit 2
fi
njet_src=$(cd "$1" && pwd)
if [ -d "$njet_src/lib-qd" ]; then
  bundled_qd=1
  qd_src="bundled ($njet_src/lib-qd)"
else
  bundled_qd=0
  qd_src=$(cd "$2" && pwd)
fi
out=$3
jobs=${4:-32}
shift $(( $# < 4 ? $# : 4 ))
# Further NJet configure arguments, e.g. --with-oneloop: OneLOop's
# double-double scalar integrals instead of QCDLoop's double-only ones.
extra_conf=("$@")
if [ -e "$out" ]; then
  echo "refusing to overwrite existing build dir $out" >&2
  exit 3
fi
mkdir -p "$out"
out=$(cd "$out" && pwd)

: "${PKG_CONFIG_BIN:=/nix/store/1c6lyixjky1pfr9ia3mvpy01sxxh307a-pkg-config-0.29.2/bin}"
: "${MAKE_BIN:=/nix/store/0xw6y53ijaqwfd9c99wyaqiinychzv1f-gnumake-4.4.1/bin}"
export PATH="$PKG_CONFIG_BIN:$MAKE_BIN:$PATH"
# The release tarballs ship generated autotools files whose extracted mtimes can
# look older than configure.ac; never regenerate them (no autotools needed).
noregen=(ACLOCAL=: AUTOCONF=: AUTOHEADER=: AUTOMAKE=:)

info="$out/build-info.txt"
{
  echo "date: $(date -u +%FT%TZ)"
  echo "host: $(hostname) $(grep -m1 'model name' /proc/cpuinfo | sed 's/.*: //')"
  echo "njet_source: $njet_src"
  echo "qd_source: $qd_src"
  echo "cxx: $(command -v g++) $(g++ --version | head -1)"
  echo "cc: $(command -v gcc) $(gcc --version | head -1)"
  echo "fc: $(command -v gfortran) $(gfortran --version | head -1)"
  echo "make: $(make --version | head -1)"
  echo "pkg-config: $(pkg-config --version)"
  echo "jobs: $jobs"
} > "$info"

stage() { echo "[$(date -u +%T)] $*" | tee -a "$info"; }

if [ "$bundled_qd" = 0 ]; then
# QD: shared + PIC (NJet links it into a shared library), C++ only.
mkdir -p "$out/qd/build" "$out/qd/prefix"
stage "qd configure"
# OneLOop's double-double integrals (NJet --with-oneloop) use QD's Fortran 90
# module, so QD's Fortran interface is built only then.
qd_fortran=--disable-fortran
for arg in "${extra_conf[@]}"; do
  [ "$arg" = --with-oneloop ] && qd_fortran="--enable-fortran"
done
qd_conf=("$qd_src/configure" --prefix="$out/qd/prefix" --with-pic=yes
         --enable-shared=yes --enable-static=no "$qd_fortran"
         CXX=g++ CC=gcc FC=gfortran CXXFLAGS="-O2" CFLAGS="-O2" FCFLAGS="-O2")
echo "qd_configure: ${qd_conf[*]}" >> "$info"
(cd "$out/qd/build" && "${qd_conf[@]}") > "$out/qd/configure.log" 2>&1
stage "qd make"
make -C "$out/qd/build" "${noregen[@]}" -j"$jobs" > "$out/qd/make.log" 2>&1
make -C "$out/qd/build" "${noregen[@]}" install > "$out/qd/install.log" 2>&1
stage "qd done"

export PKG_CONFIG_PATH="$out/qd/prefix/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
export LD_LIBRARY_PATH="$out/qd/prefix/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

# NJet: one-loop numerical library with the 2->5 channels (--enable-5jet) and
# double-double precision (--enable-f128) for the quad-precision rescue/runs.
# QCDLoop (default) supplies the scalar integrals in double precision; the
# double-double path uses OneLOop only with --with-oneloop (not used here).
mkdir -p "$out/njet/build" "$out/njet/prefix"
stage "njet configure"
if [ "$bundled_qd" = 0 ]; then
  # NJet 3: --enable-f128 builds the dd_real (double-double) channels.
  nj_conf=("$njet_src/configure" --prefix="$out/njet/prefix" --enable-5jet
           --enable-f128 --disable-dependency-tracking --with-vc=no
           CXX=g++ CC=gcc FC=gfortran F77=gfortran)
else
  # NJet 2: double-double is always built with the bundled QD. Its bundled
  # QCDLoop/FF Fortran passes a 2-element array section to a 3-element dummy
  # in ffxd0p.f (two calls that NJet 3's copy comments out), which gfortran
  # >= 10 rejects; -std=legacy turns that diagnostic back into a warning
  # (code generation unchanged).
  nj_conf=("$njet_src/configure" --prefix="$out/njet/prefix" --enable-5jet
           --disable-dependency-tracking --with-vc=no
           CXX=g++ CC=gcc FC=gfortran F77=gfortran
           FFLAGS="-g -O2 -std=legacy" FCFLAGS="-g -O2 -std=legacy")
fi
nj_conf+=("${extra_conf[@]}")
echo "njet_configure: ${nj_conf[*]}" >> "$info"
(cd "$out/njet/build" && "${nj_conf[@]}") > "$out/njet/configure.log" 2>&1
grep -E "^NJET_CXXFLAGS|^CXXFLAGS|^FFLAGS|^FCFLAGS|^CFLAGS" "$out/njet/build/Makefile" \
  | sed 's/^/njet_makefile: /' >> "$info"
stage "njet make"
make -C "$out/njet/build" "${noregen[@]}" -j"$jobs" > "$out/njet/make.log" 2>&1 \
  || { stage "njet make FAILED"; exit 4; }
make -C "$out/njet/build" "${noregen[@]}" install > "$out/njet/install.log" 2>&1
stage "njet done"
echo "BUILD DONE" >> "$info"
