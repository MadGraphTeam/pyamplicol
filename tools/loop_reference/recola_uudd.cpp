// SPDX-License-Identifier: 0BSD
#include "native_driver.hpp"
extern "C" {
void reference_recola_init(double, double, double, double);
void reference_recola_evaluate(const double *, double *);
void reference_recola_finish();
}

struct RecolaProvider {
  static constexpr const char *name = "Recola-2.3.0-SM-2.2.3";
  explicit RecolaProvider(const loop_reference::Parameters &p) {
    reference_recola_init(p.alpha_s, p.mu, p.mt, p.mb);
  }
  ~RecolaProvider() { reference_recola_finish(); }
  loop_reference::Result evaluate(const loop_reference::Point &point) {
    double momenta[loop_reference::external_legs][4];
    for (int leg = 0; leg < loop_reference::external_legs; ++leg)
      for (int mu = 0; mu < 4; ++mu) momenta[leg][mu] = point[leg][mu];
    loop_reference::Result r;
    double result[4];
    reference_recola_evaluate(&momenta[0][0], result);
    r.born = result[0]; r.finite = result[1];
    r.single = result[2]; r.doub = result[3];
    // Recola's Gamma(1+epsilon) convention -> MadLoop/BLHA convention.
    const double pi = std::acos(-1.);
    r.finite += pi*pi/6. * r.doub;
    return r;
  }
};
int main() { return loop_reference::run<RecolaProvider>(); }
