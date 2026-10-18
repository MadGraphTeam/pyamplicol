// SPDX-License-Identifier: 0BSD
#include "native_driver.hpp"
#include <cstdlib>
#include <filesystem>
extern "C" {
void reference_madloop_init(const char *, int, const char *, int, double, double, double, double);
void reference_madloop_evaluate(const double *, double *, double *, int *);
}
struct MadLoop {
  static constexpr const char *name = "MadLoop-3.7.0-loop_sm-no_b_mass";
  explicit MadLoop(const loop_reference::Parameters &p) {
    const char *root = std::getenv("PYLOOP_MADLOOP_DIR");
    if (!root || p.mb != 0.)
      throw std::runtime_error("MadLoop control requires PYLOOP_MADLOOP_DIR and mb=0");
    const std::string card = (std::filesystem::path(root)/"Cards/param_card.dat").string();
    const std::string resource = (std::filesystem::path(root)/"SubProcesses/MadLoop5_resources").string();
    if (card.size() > 512 || resource.size() > 512)
      throw std::runtime_error("MadLoop path exceeds its Fortran interface limit");
    reference_madloop_init(card.data(), card.size(), resource.data(), resource.size(),
                          p.alpha_s, p.mu, p.mt, p.inverse_alpha_em);
  }
  loop_reference::Result evaluate(const loop_reference::Point &point) {
    loop_reference::Result r;
    double result[4];
    int status;
    reference_madloop_evaluate(point[0].data(), result, &r.accuracy, &status);
    if (status/100 == 4) throw std::runtime_error("MadLoop reports an unstable point");
    r.initialized = (status/10)%10 != 3 && (status/10)%10 != 4;
    r.born = result[0]; r.finite = result[1];
    r.single = result[2]; r.doub = result[3];
    return r;
  }
};
int main() { return loop_reference::run<MadLoop>(); }
