// NJet one-loop driver for the all-gluon channels g g -> (n-2) g, n = 4..7.
//
// Two modes, both reading the same points file and writing one JSON line per
// point to stdout:
//
//   njet_driver blha points=FILE contract=FILE alphas=0.118
//       NJet's public BLHA2 interface (OLP_Start / OLP_EvalSubProcess2) with a
//       contract signed by NJet's njet.py; channel 1 of the contract is used.
//       NJet always runs its scaling test in double precision here and may
//       rescue in double-double (contract options NJetMultiPrec / Precision).
//
//   njet_driver cc points=FILE alphas=0.118 [prec=double|dd]
//       colour-correlated Borns <T_i.T_j> (BLHA 'cctree' normalisation), for
//       the IR-pole prediction of the single pole.
//
//   njet_driver direct points=FILE legs=N amp=standard|ds prec=double|dd
//       scaling=0|1 alphas=0.118 nf=5 nc=3 scheme=cdr|fdh|none renorm=1|0
//       NJet's colour-summed classes (Amp0q<n-2>g and the de-symmetrised
//       Amp0q<n-2>g_ds<n-2>) through NJetAccuracy, without the BLHA layer:
//       scaling=1 calls NJetAccuracy::virt() (two evaluations, the second at
//       momenta rescaled by NJet's SCALEFACTOR_B; value = their average,
//       error = their difference), scaling=0 calls virt_single() (one
//       evaluation, no estimate). prec=dd evaluates in QD's dd_real with the
//       momenta parsed from their decimal text (scalar integrals stay double:
//       QCDLoop). The output applies the BLHA normalisation of
//       njet_olp.cpp Process::eval_loop / setCouplings verbatim:
//       born *= g^(2(n-2)) / rfactor, loop *= g^(2(n-2)) / rfactor * g^2 /
//       (16 pi^2), g^2 = 4 pi alphas, rfactor = 2*2*8*8*(n-2)! (initial
//       helicity and colour average, final-state symmetry; njet.py).
//
// Points file: "npoints nlegs", then per point a line "mu" and nlegs lines
// "E px py pz" (decimal text; legs 1, 2 incoming with physical momenta).
// Timing: the last point is evaluated once untimed (initialisation), then
// every point once, timed with steady_clock around setMomenta + evaluation.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#include <qd/dd_real.h>

#include "njet.h"
#include "chsums/NJetAccuracy.h"
#include "chsums/0q4g.h"
#include "chsums/0q5g.h"
#include "chsums/0q6g.h"
#include "chsums/0q7g.h"
#include "ngluon2/Mom.h"

namespace {

struct Point {
  std::string mu;
  std::vector<std::vector<std::string>> p;  // [leg][E, px, py, pz]
};

std::vector<Point> read_points(const std::string &path, int &legs) {
  std::ifstream in(path);
  if (!in) {
    std::cerr << "cannot read " << path << "\n";
    std::exit(2);
  }
  int count = 0;
  in >> count >> legs;
  std::vector<Point> points(count);
  for (auto &pt : points) {
    in >> pt.mu;
    pt.p.assign(legs, std::vector<std::string>(4));
    for (auto &leg : pt.p)
      for (auto &c : leg) in >> c;
  }
  if (!in) {
    std::cerr << "malformed points file " << path << "\n";
    std::exit(2);
  }
  return points;
}

std::map<std::string, std::string> parse_args(int argc, char **argv, int first) {
  std::map<std::string, std::string> args;
  for (int i = first; i < argc; ++i) {
    std::string a(argv[i]);
    const auto eq = a.find('=');
    if (eq == std::string::npos) {
      std::cerr << "expected key=value, got " << a << "\n";
      std::exit(2);
    }
    args[a.substr(0, eq)] = a.substr(eq + 1);
  }
  return args;
}

std::string get(const std::map<std::string, std::string> &args, const std::string &key,
                const std::string &fallback = "") {
  const auto it = args.find(key);
  if (it != args.end()) return it->second;
  if (fallback.empty()) {
    std::cerr << "missing argument " << key << "=\n";
    std::exit(2);
  }
  return fallback;
}

std::string fmt(double x) {
  char buf[64];
  std::snprintf(buf, sizeof buf, "%.17e", x);
  return buf;
}

std::string fmt(const dd_real &x) { return x.to_string(32, 0, std::ios_base::scientific); }

template <typename T> T parse(const std::string &s);
template <> double parse<double>(const std::string &s) { return std::strtod(s.c_str(), nullptr); }
template <> dd_real parse<dd_real>(const std::string &s) { return dd_real(s.c_str()); }

template <typename T> T pi_value();
template <> double pi_value<double>() { return M_PI; }
template <> dd_real pi_value<dd_real>() { return dd_real::_pi; }

double factorial(int n) { return n <= 1 ? 1.0 : n * factorial(n - 1); }

// The momenta exactly as njet_olp.cpp Process::setMom builds them for the
// contract line "21 21 -> 21 ... | ... (-2 -1 3 4 ...)" signed by njet.py:
// NJet's legs 1 and 2 are minus BLHA legs 2 and 1 (all outgoing), and if a
// momentum has |E| == |p_y| (SPIN_AXIS = 2) the axes are cycled.
void axes(const Point &pt, int &ix, int &iy, int &iz) {
  ix = 1;
  iy = 2;
  iz = 3;
  for (const auto &leg : pt.p) {
    if (std::fabs(parse<double>(leg[0])) == std::fabs(parse<double>(leg[2]))) {
      std::swap(ix, iy);
      std::swap(iy, iz);
      break;
    }
  }
}

template <typename T> std::vector<MOM<T>> momenta(const Point &pt) {
  int ix, iy, iz;
  axes(pt, ix, iy, iz);
  std::vector<MOM<T>> moms;
  for (std::size_t i = 0; i < pt.p.size(); ++i) {
    const auto &l = pt.p[i < 2 ? 1 - i : i];
    MOM<T> m(parse<T>(l[0]), parse<T>(l[ix]), parse<T>(l[iy]), parse<T>(l[iz]));
    if (i < 2) m = -m;
    moms.push_back(m);
  }
  return moms;
}

template <typename T> NJetAccuracy<T> *make_amp(int legs, bool ds) {
  switch (legs) {
  case 4:
    // NJet has no de-symmetrised 2->2 gluon class; the BLHA layer maps
    // 'loopds' of g g -> g g onto the standard sum as well.
    return NJetAccuracy<T>::template create<Amp0q4g<T>>();
  case 5:
    return ds ? NJetAccuracy<T>::template create<Amp0q5g_ds3<T>>()
              : NJetAccuracy<T>::template create<Amp0q5g<T>>();
  case 6:
    return ds ? NJetAccuracy<T>::template create<Amp0q6g_ds4<T>>()
              : NJetAccuracy<T>::template create<Amp0q6g<T>>();
  case 7:
    return ds ? NJetAccuracy<T>::template create<Amp0q7g_ds5<T>>()
              : NJetAccuracy<T>::template create<Amp0q7g<T>>();
  default:
    std::cerr << "legs must be 4..7\n";
    std::exit(2);
  }
}

template <typename T>
int run_direct(const std::vector<Point> &points, int legs,
               const std::map<std::string, std::string> &args) {
  const bool ds = get(args, "amp", "standard") == "ds";
  const bool scaling = get(args, "scaling", "1") == "1";
  const std::string scheme = get(args, "scheme", "cdr");
  const int renorm = std::atoi(get(args, "renorm", "1").c_str());
  const T alphas = parse<T>(get(args, "alphas"));
  const double nf = std::strtod(get(args, "nf", "5").c_str(), nullptr);
  const double nc = std::strtod(get(args, "nc", "3").c_str(), nullptr);

  NJetAccuracy<T> *amp = make_amp<T>(legs, ds);
  amp->setNc(nc);
  amp->setNf(nf);
  if (scheme == "cdr") {
    amp->setScheme(NJetRenorm<T>::SCHEME_CDR);
  } else if (scheme == "fdh") {
    amp->setScheme(NJetRenorm<T>::SCHEME_FDH);
  } else if (scheme == "none") {
    amp->setScheme(NJetRenorm<T>::SCHEME_NONE);
  } else {
    std::cerr << "scheme must be cdr, fdh or none\n";
    return 2;
  }
  amp->setRenorm(renorm ? NJetRenorm<T>::QCDRENORM : NJetRenorm<T>::UNRENORM);

  const T pi = pi_value<T>();
  const T gs2 = T(4.) * pi * alphas;
  T tree_cpl = T(1.);
  for (int i = 0; i < legs - 2; ++i) tree_cpl *= gs2;
  tree_cpl /= T(256. * factorial(legs - 2));
  const T loop_cpl = tree_cpl * gs2 / (T(16.) * pi * pi);

  auto evaluate = [&](const Point &pt, double &seconds) {
    const auto moms = momenta<T>(pt);
    const T mu = parse<T>(pt.mu);
    const auto start = std::chrono::steady_clock::now();
    amp->setMuR2(mu * mu);
    amp->setMomenta(moms);
    if (scaling) {
      amp->virt();
    } else {
      amp->virt_single();
    }
    seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
  };

  double seconds = 0.;
  if (points.size() > 1) {
    evaluate(points.back(), seconds);
    std::printf("{\"initialisation_seconds\": %.6f}\n", seconds);
    std::fflush(stdout);
  }
  for (std::size_t i = 0; i < points.size(); ++i) {
    evaluate(points[i], seconds);
    const auto v = amp->virt_value();
    const auto e = amp->virt_error();
    std::printf(
        "{\"index\": %zu, \"seconds\": %.6f, \"born\": \"%s\", \"double_pole\": \"%s\", "
        "\"single_pole\": \"%s\", \"finite\": \"%s\", \"born_error\": \"%s\", "
        "\"errors\": [\"%s\", \"%s\", \"%s\"], \"imaginary\": [\"%s\", \"%s\", \"%s\"]}\n",
        i, seconds, fmt(T(amp->born_value() * tree_cpl)).c_str(),
        fmt(T(v.get2().real() * loop_cpl)).c_str(), fmt(T(v.get1().real() * loop_cpl)).c_str(),
        fmt(T(v.get0().real() * loop_cpl)).c_str(), fmt(T(amp->born_error() * tree_cpl)).c_str(),
        fmt(T(e.get2().real() * loop_cpl)).c_str(), fmt(T(e.get1().real() * loop_cpl)).c_str(),
        fmt(T(e.get0().real() * loop_cpl)).c_str(), fmt(T(v.get2().imag() * loop_cpl)).c_str(),
        fmt(T(v.get1().imag() * loop_cpl)).c_str(), fmt(T(v.get0().imag() * loop_cpl)).c_str());
    std::fflush(stdout);
  }
  delete amp;
  return 0;
}

// Colour-correlated Borns <M0|T_i.T_j|M0> (BLHA cctree convention, i.e. minus
// NJet's internal value, times the Born normalisation), i < j in the input leg
// order; for the IR-pole (Catani) prediction of the single pole.
template <typename T>
int run_cc(const std::vector<Point> &points, int legs,
           const std::map<std::string, std::string> &args) {
  const T alphas = parse<T>(get(args, "alphas"));
  NJetAccuracy<T> *amp = make_amp<T>(legs, false);
  amp->setNc(3.);
  const T pi = pi_value<T>();
  const T gs2 = T(4.) * pi * alphas;
  T tree_cpl = T(1.);
  for (int i = 0; i < legs - 2; ++i) tree_cpl *= gs2;
  tree_cpl /= T(256. * factorial(legs - 2));
  std::vector<T> cc(legs * (legs - 1) / 2);
  for (std::size_t n = 0; n < points.size(); ++n) {
    amp->setMomenta(momenta<T>(points[n]));
    const T born = amp->born_single() * tree_cpl;
    amp->born_cc_single(cc.data());
    std::printf("{\"index\": %zu, \"born\": \"%s\", \"cc\": [", n, fmt(born).c_str());
    bool first = true;
    for (int a = 0; a < legs; ++a) {
      for (int b = a + 1; b < legs; ++b) {
        // input leg a is NJet leg (a < 2 ? 1 - a : a); nis(i, j) for i > j.
        int i = a < 2 ? 1 - a : a, j = b < 2 ? 1 - b : b;
        if (i < j) std::swap(i, j);
        const T value = -cc[j + i * (i - 1) / 2] * tree_cpl;
        std::printf("%s[%d, %d, \"%s\"]", first ? "" : ", ", a, b, fmt(value).c_str());
        first = false;
      }
    }
    std::printf("]}\n");
    std::fflush(stdout);
  }
  delete amp;
  return 0;
}

int run_blha(const std::vector<Point> &points, int legs,
             const std::map<std::string, std::string> &args) {
  const std::string contract = get(args, "contract");
  int status = 0;
  OLP_Start(contract.c_str(), &status);
  if (status != 1) {
    std::cerr << "OLP_Start rejected " << contract << "\n";
    return 3;
  }
  char name[BLHA_NAME_LEN + 1] = {}, version[BLHA_VERSION_LEN + 1] = {},
       message[BLHA_MESSAGE_LEN + 1] = {};
  OLP_Info(name, version, message);
  std::printf("{\"olp\": \"%s\", \"version\": \"%s\", \"message\": \"%s\"}\n", name, version,
              message);
  const double alphas = std::strtod(get(args, "alphas").c_str(), nullptr);
  const double zero = 0.;
  int rstatus = 0;
  OLP_SetParameter("alphas", &alphas, &zero, &rstatus);
  if (rstatus != 1) {
    std::cerr << "OLP_SetParameter(alphas) failed\n";
    return 3;
  }
  const int channel = 1;
  auto evaluate = [&](const Point &pt, double *rval, double &acc, double &seconds) {
    std::vector<double> pp(5 * legs);
    for (int i = 0; i < legs; ++i) {
      for (int mu = 0; mu < 4; ++mu) pp[5 * i + mu] = parse<double>(pt.p[i][mu]);
      pp[5 * i + 4] = 0.;
    }
    const double mu = parse<double>(pt.mu);
    const auto start = std::chrono::steady_clock::now();
    OLP_EvalSubProcess2(&channel, pp.data(), &mu, rval, &acc);
    seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
  };
  double rval[7] = {}, acc = 0., seconds = 0.;
  if (points.size() > 1) {
    evaluate(points.back(), rval, acc, seconds);
    std::printf("{\"initialisation_seconds\": %.6f}\n", seconds);
    std::fflush(stdout);
  }
  for (std::size_t i = 0; i < points.size(); ++i) {
    std::fill(rval, rval + 7, 0.);
    evaluate(points[i], rval, acc, seconds);
    std::printf(
        "{\"index\": %zu, \"seconds\": %.6f, \"born\": \"%s\", \"double_pole\": \"%s\", "
        "\"single_pole\": \"%s\", \"finite\": \"%s\", \"relative_accuracy\": [\"%s\", \"%s\", "
        "\"%s\"], \"blha_accuracy\": \"%s\"}\n",
        i, seconds, fmt(rval[3]).c_str(), fmt(rval[0]).c_str(), fmt(rval[1]).c_str(),
        fmt(rval[2]).c_str(), fmt(rval[4]).c_str(), fmt(rval[5]).c_str(), fmt(rval[6]).c_str(),
        fmt(acc).c_str());
    std::fflush(stdout);
  }
  return 0;
}

}  // namespace

int main(int argc, char **argv) {
  if (argc < 2) {
    std::cerr << "usage: njet_driver blha|direct key=value...\n";
    return 2;
  }
  const std::string mode(argv[1]);
  const auto args = parse_args(argc, argv, 2);
  int legs = 0;
  const auto points = read_points(get(args, "points"), legs);
  if (mode == "blha") return run_blha(points, legs, args);
  if (mode == "cc") {
    return get(args, "prec", "double") == "dd" ? run_cc<dd_real>(points, legs, args)
                                               : run_cc<double>(points, legs, args);
  }
  if (mode != "direct") {
    std::cerr << "mode must be blha or direct\n";
    return 2;
  }
  if (std::atoi(get(args, "legs", std::to_string(legs)).c_str()) != legs) {
    std::cerr << "legs= disagrees with the points file\n";
    return 2;
  }
  const std::string prec = get(args, "prec", "double");
  if (prec == "dd") return run_direct<dd_real>(points, legs, args);
  if (prec != "double") {
    std::cerr << "prec must be double or dd\n";
    return 2;
  }
  return run_direct<double>(points, legs, args);
}
