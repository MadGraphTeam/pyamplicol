// Small reference-control driver. Provider calls and timing loops stay native.
#pragma once
#include <array>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace loop_reference {
using Point = std::array<std::array<double, 4>, 4>;
struct Parameters { double alpha_s, mu, mt, mb; };
struct Result {
  double born{}, finite{}, single{}, doub{}, accuracy{-1.};
  bool initialized{true};
};

template<class Provider> int run() {
  try {
    std::size_t batch, repetitions;
    Parameters parameters{};
    if (!(std::cin >> batch >> repetitions >> parameters.alpha_s >> parameters.mu
                   >> parameters.mt >> parameters.mb) || !batch || !repetitions)
      throw std::runtime_error("invalid reference input header");
    std::vector<Point> points(batch);
    for (auto &point : points) for (auto &leg : point) for (auto &x : leg)
      if (!(std::cin >> x) || !std::isfinite(x))
        throw std::runtime_error("invalid reference momentum");
    Provider provider(parameters);
    std::vector<Result> results(batch);
    // Initialization/helicity filtering is excluded from warm evaluation time.
    bool initialized = false;
    for (int attempt = 0; attempt < 64 && !initialized; ++attempt) {
      initialized = true;
      for (std::size_t i = 0; i < batch; ++i) {
        results[i] = provider.evaluate(points[i]);
        initialized = initialized && results[i].initialized;
      }
    }
    if (!initialized) throw std::runtime_error("provider initialization did not finish");
    const auto start = std::chrono::steady_clock::now();
    for (std::size_t repeat = 0; repeat < repetitions; ++repeat)
      for (std::size_t i = 0; i < batch; ++i) results[i] = provider.evaluate(points[i]);
    const double seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - start).count();
    std::cout << std::setprecision(17) << "\nLOOP_REFERENCE_JSON {\"provider\":\""
              << Provider::name << "\",\"batch_size\":" << batch
              << ",\"repetitions\":" << repetitions << ",\"seconds\":" << seconds
              << ",\"actual_poles\":true,\"results\":[";
    for (std::size_t i = 0; i < batch; ++i) {
      const auto &r = results[i];
      if (!(std::isfinite(r.born) && std::isfinite(r.finite) &&
            std::isfinite(r.single) && std::isfinite(r.doub)))
        throw std::runtime_error("non-finite reference result");
      if (i) std::cout << ',';
      std::cout << "{\"born\":" << r.born << ",\"finite\":" << r.finite
                << ",\"single_pole\":" << r.single << ",\"double_pole\":"
                << r.doub << ",\"accuracy\":" << r.accuracy << '}';
    }
    std::cout << "]}\n";
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "reference driver: " << error.what() << '\n';
    return 1;
  }
}
}
