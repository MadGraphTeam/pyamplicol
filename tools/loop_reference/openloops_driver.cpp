// SPDX-License-Identifier: 0BSD
// Generic OpenLoops 2 reference driver. Command stream on stdin:
//   int <name> <value> | double <name> <value> | string <name> <value>
//   register <amptype> <process string, e.g. 21 21 -> 6 -6>
//   points <count>, then <count> lines "mu E1 px1 py1 pz1 ... En pxn pyn pzn"
// Point 1 is evaluated once untimed (initialization), then points 2..n,1 are
// timed with "mu" set per point. Loop values are returned as provided by
// ol_evaluate_loop (finite, 1/eps, 1/eps^2).
#include <chrono>
#include <cmath>
#include <cstdio>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include "openloops.h"

int main() {
  try {
    std::string line;
    int id = -1, legs = 0;
    while (std::getline(std::cin, line)) {
      std::istringstream in(line);
      std::string command;
      if (!(in >> command)) continue;
      if (command == "int" || command == "double" || command == "string") {
        std::string name, value;
        if (!(in >> name >> value)) throw std::runtime_error("bad parameter line: " + line);
        if (command == "int") ol_setparameter_int(name.c_str(), std::stoi(value));
        else if (command == "double") ol_setparameter_double(name.c_str(), std::stod(value));
        else ol_setparameter_string(name.c_str(), value.c_str());
      } else if (command == "register") {
        int amptype;
        in >> amptype;
        std::string process;
        std::getline(in, process);
        process.erase(0, process.find_first_not_of(' '));
        id = ol_register_process(process.c_str(), amptype);
        if (id <= 0) throw std::runtime_error("OpenLoops process unavailable: " + process);
        legs = ol_n_external(id);
        const auto start = std::chrono::steady_clock::now();
        ol_start();
        std::printf("START_SECONDS %.8e\n",
                    std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count());
      } else if (command == "points") {
        std::size_t count;
        if (id <= 0 || !(in >> count) || !count) throw std::runtime_error("points before register");
        std::vector<double> scales(count), momenta(count * 5 * legs, 0.);
        for (std::size_t i = 0; i < count; ++i) {
          if (!(std::cin >> scales[i])) throw std::runtime_error("bad point scale");
          for (int leg = 0; leg < legs; ++leg)
            for (int mu = 0; mu < 4; ++mu)
              if (!(std::cin >> momenta[(i * legs + leg) * 5 + mu]))
                throw std::runtime_error("bad momentum");
        }
        auto evaluate = [&](std::size_t i, double *out) {
          ol_setparameter_double("mu", scales[i]);
          double loop[3];
          ol_evaluate_loop(id, &momenta[i * legs * 5], &out[0], loop, &out[4]);
          out[1] = loop[0]; out[2] = loop[1]; out[3] = loop[2];
        };
        double out[5];
        auto start = std::chrono::steady_clock::now();
        evaluate(0, out);
        std::printf("INITIAL_CALL_SECONDS %.8e\n",
                    std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count());
        for (std::size_t k = 1; k <= count; ++k) {
          const std::size_t i = k == count ? 0 : k;
          start = std::chrono::steady_clock::now();
          evaluate(i, out);
          const double seconds =
              std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
          for (double x : out)
            if (!std::isfinite(x)) throw std::runtime_error("non-finite OpenLoops result");
          std::printf("ROW %zu %.8e %.17e %.17e %.17e %.17e %.17e\n", i + 1, seconds, out[0],
                      out[1], out[2], out[3], out[4]);
        }
      } else {
        throw std::runtime_error("unknown command: " + command);
      }
    }
    ol_finish();
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "openloops driver: " << error.what() << '\n';
    return 1;
  }
}
