// SPDX-License-Identifier: 0BSD
#include "native_driver.hpp"
#include "openloops.h"

struct OpenLoops {
  static constexpr const char *name = "OpenLoops-2.1.5";
  int id;
  explicit OpenLoops(const loop_reference::Parameters &p) {
    ol_setparameter_int("order_qcd", 2);
    ol_setparameter_int("order_ew", 0);
    ol_setparameter_int("nf", 6);
    ol_setparameter_int("nf_alphasrun", 5);
    ol_setparameter_int("truepoles", 1);
    ol_setparameter_int("polenorm", 0);
    ol_setparameter_int("ct_on", 1);
    ol_setparameter_int("r2_on", 1);
    ol_setparameter_int("iop_on", 0);
    ol_setparameter_double("mass(6)", p.mt);
    ol_setparameter_double("width(6)", 0.);
    ol_setparameter_double("mass(5)", p.mb);
    ol_setparameter_double("alpha_s", p.alpha_s);
    ol_setparameter_double("mu", p.mu);
#ifdef LOOP_REFERENCE_TOP_PAIR
    id = ol_register_process("2 -2 -> 6 -6", 11);
#else
    id = ol_register_process("2 -2 -> 1 -1", 11);
#endif
    if (id <= 0) throw std::runtime_error("OpenLoops control process unavailable");
    ol_start();
  }
  ~OpenLoops() { ol_finish(); }
  loop_reference::Result evaluate(const loop_reference::Point &point) {
    double momenta[20]{};
    for (int leg = 0; leg < 4; ++leg)
      for (int mu = 0; mu < 4; ++mu) momenta[5*leg+mu] = point[leg][mu];
    loop_reference::Result r;
    double loop[3];
    ol_evaluate_loop(id, momenta, &r.born, loop, &r.accuracy);
    r.finite = loop[0]; r.single = loop[1]; r.doub = loop[2];
    return r;
  }
};
int main() { return loop_reference::run<OpenLoops>(); }
