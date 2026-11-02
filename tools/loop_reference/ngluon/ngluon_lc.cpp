// SPDX-License-Identifier: 0BSD
// NGluon (NJet 3.x ngluon2) leading-colour driver for n-gluon one-loop amplitudes (M-FINAL MF-8G-3 (vi)).
//
// Per point it sums, over the colour orderings with leg 1 first (the (n-1)! distinct single traces) and
// every helicity configuration with at least two of each helicity (the others vanish at tree level), the
// tree primitive A0 = NParton2::evalTree and the leading-colour gluon-loop primitive A1 = NParton2::eval(MIXED)
// (c_Gamma and the couplings factored out, as NJet's colour sums take them; FDH, unrenormalised):
//   S0 = sum |A0|^2,   S1 = sum 2 Re(conj(A0) A1)   (Laurent: finite, 1/eps, 1/eps^2).
// tools/loop_reference/ngluon/run_ngluon.py turns S1/S0 into the leading-colour virtual over the leading-colour
// Born (pyAmpliCol's LC: the leading N_c degree, n_f of degree 0), renormalised and converted to CDR as NJet's
// chsums/NJetRenorm.cpp does.
//
// Usage: ngluon_lc points=FILE [first=0 stride=1] [prec=double|dd]
//   points file: "npoints nlegs", then per point a line "mu" and nlegs lines "E px py pz" (decimal text; legs 1
//   and 2 incoming with physical momenta; they are negated to NGluon's all-outgoing convention). first/stride
//   split the orderings across processes (ordering k is evaluated when k % stride == first). One JSON line per
//   point on stdout: index, orderings, helicities, S0, S1 = [finite, single, double], seconds.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <complex>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include <qd/dd_real.h>

#include "njet.h"
#include "ngluon2/Model.h"
#include "ngluon2/Mom.h"
#include "ngluon2/NGluon2.h"
#include "ngluon2/NParton2.h"

namespace {

std::string arg(int argc, char **argv, const std::string &key, const std::string &fallback) {
  const std::string prefix = key + "=";
  for (int i = 1; i < argc; ++i) {
    if (std::strncmp(argv[i], prefix.c_str(), prefix.size()) == 0) return argv[i] + prefix.size();
  }
  return fallback;
}

template <typename T> T parse(const std::string &text);
template <> double parse<double>(const std::string &text) { return std::strtod(text.c_str(), nullptr); }
template <> dd_real parse<dd_real>(const std::string &text) { return dd_real(text.c_str()); }

double as_double(double x) { return x; }
double as_double(const dd_real &x) { return x.x[0]; }

template <typename T> int run(const std::string &file, int first, int stride) {
  std::ifstream in(file);
  int npoints = 0, n = 0;
  in >> npoints >> n;
  std::vector<int> base(n - 1);
  for (int i = 0; i < n - 1; ++i) base[i] = i + 1;
  std::vector<Flavour<double>> flavours(n, StandardModel::G());
  for (int p = 0; p < npoints; ++p) {
    std::string mu_text;
    in >> mu_text;
    const T mu = parse<T>(mu_text);
    std::vector<MOM<T>> moms;
    for (int j = 0; j < n; ++j) {
      std::string e, x, y, z;
      in >> e >> x >> y >> z;
      MOM<T> k(parse<T>(e), parse<T>(x), parse<T>(y), parse<T>(z));
      moms.push_back(j < 2 ? -k : k);
    }
    NParton2<T> amp;
    amp.setProcess(flavours);
    amp.setMomenta(moms);
    amp.setMuR2(mu * mu);
    const auto start = std::chrono::steady_clock::now();
    T s0(0.);
    T s1[3] = {T(0.), T(0.), T(0.)};
    long orderings = 0, helicities = 0;
    std::vector<int> rest = base;
    std::vector<int> order(n);
    long k = 0;
    do {
      const bool mine = (k++ % stride) == first;
      if (!mine) continue;
      ++orderings;
      order[0] = 0;
      for (int i = 0; i < n - 1; ++i) order[i + 1] = rest[i];
      for (int h = 0; h < (1 << n); ++h) {
        const int minus = __builtin_popcount(h);
        if (minus < 2 || n - minus < 2) continue;
        std::vector<int> hel(n);
        for (int i = 0; i < n; ++i) hel[i] = (h >> i) & 1 ? -1 : 1;
        amp.setHelicity(hel);
        const std::complex<T> a0 = amp.evalTree(order.data());
        const Eps3<T> a1 = amp.eval(0, order.data());  // PRIMTYPE MIXED: the gluon loop
        s0 += std::norm(a0);
        const std::complex<T> c0 = std::conj(a0);
        s1[0] += T(2.) * std::real(c0 * a1.get0());
        s1[1] += T(2.) * std::real(c0 * a1.get1());
        s1[2] += T(2.) * std::real(c0 * a1.get2());
        ++helicities;
      }
    } while (std::next_permutation(rest.begin(), rest.end()));
    const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    std::printf("{\"index\": %d, \"first\": %d, \"stride\": %d, \"orderings\": %ld, \"evaluations\": %ld, "
                "\"S0\": %.17e, \"S1\": [%.17e, %.17e, %.17e], \"seconds\": %.3f}\n",
                p, first, stride, orderings, helicities, as_double(s0), as_double(s1[0]), as_double(s1[1]),
                as_double(s1[2]), seconds);
    std::fflush(stdout);
  }
  return 0;
}

}  // namespace

int main(int argc, char **argv) {
  const std::string file = arg(argc, argv, "points", "");
  if (file.empty()) {
    std::fprintf(stderr, "usage: ngluon_lc points=FILE [first=0 stride=1] [prec=double|dd]\n");
    return 2;
  }
  const int first = std::atoi(arg(argc, argv, "first", "0").c_str());
  const int stride = std::atoi(arg(argc, argv, "stride", "1").c_str());
  const std::string prec = arg(argc, argv, "prec", "double");
  if (prec == "dd") return run<dd_real>(file, first, stride);
  return run<double>(file, first, stride);
}
