# SPDX-License-Identifier: 0BSD
"""Checks of the loop-induced analytic oracles (li_analytic.py) against
published values and against Feynman-parameter integrals.

Published values (sources under workspace/reference/papers/li-*):
* Spira hep-ph/9705337 / the HEFT expansion of the gg>H form factor:
  A_Q = 1 + 7/120 r + 1/168 r^2 + 13/16800 r^3 + 2/17325 r^4 + O(r^5);
* Djouadi hep-ph/0503172 sec. 2.3.1: A_1/2^H -> 4/3 and A_1^H -> -7 for heavy
  loop particles, A_1^H = -5 - 3 pi^2/4 at the WW threshold;
* Jikia, Tkabladze hep-ph/9312228: W-loop low-energy amplitudes 14/5 s^2/M^4,
  (s^2 + t^2 + u^2)/(10 M^4), 0 and sigma_W = 2751 alpha^4 s^3/(16000 pi M^8);
* Euler-Heisenberg / Karplus-Neuman: sigma(gamma gamma -> gamma gamma) =
  973 alpha^4 omega^6/(10125 pi m^8) at omega << m;
* Bern et al. hep-ph/0109079 eq. (OneLoopFunctions): the massless fermion loop;
* Plehn, Spira, Zerwas hep-ph/9603205 eq. (19): the gg>HH normalisation.
"""

import sys
from pathlib import Path

import mpmath as mp
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import li_analytic as L  # noqa: E402


@pytest.fixture(autouse=True)
def _precision():
    with mp.workdps(30):
        yield


def test_spira_form_factor_reproduces_the_heavy_quark_expansion():
    series = [1, mp.mpf(7) / 120, mp.mpf(1) / 168, mp.mpf(13) / 16800, mp.mpf(2) / 17325]
    for r in (mp.mpf("1e-2"), mp.mpf("1e-3")):
        residual = mp.re(L.a_q(4 / r)) - sum(c * r ** k for k, c in enumerate(series))
        assert abs(residual) < 3e-5 * r ** 5


def test_djouadi_photon_form_factors_limits_and_threshold():
    assert abs(L.a_half(mp.mpf("1e-12")) - mp.mpf(4) / 3) < 1e-10
    assert abs(L.a_one(mp.mpf("1e-12")) + 7) < 1e-10
    assert abs(L.a_one(mp.mpf(1)) - (-5 - 3 * mp.pi ** 2 / 4)) < mp.mpf(10) ** -25


def _angular(s, loops):
    """d sigma/d cos (alpha^4 extracted) at the four-point Gauss-Legendre nodes."""
    nodes = [(-mp.sqrt((3 + 2 * mp.sqrt(mp.mpf(6) / 5)) / 7), (18 - mp.sqrt(30)) / 36),
             (-mp.sqrt((3 - 2 * mp.sqrt(mp.mpf(6) / 5)) / 7), (18 + mp.sqrt(30)) / 36)]
    nodes += [(-x, w) for x, w in nodes]
    total = 0
    for c, w in nodes:
        t, u = -s / 2 * (1 - c), -s / 2 * (1 + c)
        total += w * L.lbl_helicity_sum(L._box_sum(loops, s, t, u)) / 4 / (32 * mp.pi * s)
    return total / 2  # identical photons


def test_jikia_tkabladze_w_loop_low_energy_limits():
    m = mp.mpf(80)
    s = mp.mpf("1e-2") * m ** 2
    t, u = -s / 2 * (1 - mp.mpf("0.3")), -s / 2 * (1 + mp.mpf("0.3"))
    pppp, pppm, ppmm = L.lbl_w(s, t, u, m)
    assert abs(pppp / (mp.mpf(14) / 5 * s ** 2 / m ** 4) - 1) < 2e-3
    assert abs(ppmm / ((s * s + t * t + u * u) / (10 * m ** 4)) - 1) < 2e-3
    assert abs(pppm) < 10 * (s / m ** 2) ** 3  # no O(s^2/M^4) term
    sigma = _angular(s, [(1, "w", m)])
    assert abs(sigma / (mp.mpf(2751) / (16000 * mp.pi) * s ** 3 / m ** 8) - 1) < 2e-3


def test_fermion_box_gives_the_euler_heisenberg_cross_section():
    m, s = mp.mpf(1), mp.mpf("1e-2")
    omega = mp.sqrt(s) / 2
    sigma = _angular(s, [(1, "fermion", m)])
    assert abs(sigma / (mp.mpf(973) / (10125 * mp.pi) * omega ** 6 / m ** 8) - 1) < 2e-3


def test_massless_limit_is_the_published_massless_box():
    s = mp.mpf(1000) ** 2
    t, u = -s / 2 * (1 - mp.mpf("0.37")), -s / 2 * (1 + mp.mpf("0.37"))
    massive = L._box_sum([(1, "fermion", L._massless_regulator(s))], s, t, u)
    pppp, mppp, mmpp, pmmp_tu, pmmp_ut = L.lbl_massless(s, t, u)
    assert abs(massive[0][0] / 8 - pppp) < 1e-9
    assert abs(massive[0][1] / 8 - mppp) < 1e-9 and abs(massive[0][2] / 8 - mmpp) < 1e-9
    assert abs(massive[1] / 8 - pmmp_tu) < 1e-9 and abs(massive[2] / 8 - pmmp_ut) < 1e-9


def _c0_numeric(s, m2):
    return mp.quad(lambda x1: mp.quad(lambda x3: -1 / (m2 - s * x1 * x3), [0, 1 - x1]), [0, 1])


def test_scalar_integrals_match_feynman_parameter_integrals():
    with mp.workdps(15):
        # Euclidean and above threshold with a finite width (no i0 ambiguity).
        for s, m2 in ((-3, mp.mpf(1)), (10, mp.mpc(1, -0.2))):
            m = mp.sqrt(m2)
            delta = L._delta
            L._delta = lambda: 0  # the closed forms at the given complex mass itself
            try:
                assert abs(L.c0(s, m) - _c0_numeric(s, m2)) < 1e-9 * abs(L.c0(s, m))
                if s < 0:
                    numeric = mp.quad(lambda r, a, c: r * (1 - r) / (m2 - s * r * r * a * (1 - a) + 2 * (1 - r) ** 2
                                                                    * c * (1 - c)) ** 2,
                                      [0, 1], [0, 1], [0, 1], maxdegree=4)
                    assert abs(L.d0(s, -2, m) - numeric) < 1e-7 * abs(numeric)
            finally:
                L._delta = delta


def test_box_is_continuous_as_the_width_vanishes():
    # Physical region (s > 4 m^2, t < 0) and below threshold: the closed form
    # at m^2 (1 - i delta) converges as delta -> 0 (no branch jump).
    for s, t in ((10, -3), (2, -5), (4.5, -0.3)):
        values = []
        for d in ("1e-8", "1e-16", "1e-24"):
            delta = L._delta
            L._delta = lambda d=d: mp.mpf(d)
            try:
                values.append(L.d0(mp.mpf(s), mp.mpf(t), mp.mpf(1)))
            finally:
                L._delta = delta
        assert abs(values[1] - values[2]) < 1e-12 * abs(values[2])
        assert abs(values[0] - values[2]) < 1e-6 * abs(values[2])


def test_let_matches_the_plehn_spira_zerwas_normalisation():
    class Par:
        alpha_s, MH = mp.mpf("0.118"), mp.mpf(125)
        v = mp.mpf(246)

    s = mp.mpf(500) ** 2
    point = [[mp.sqrt(s) / 2, 0, 0, mp.sqrt(s) / 2], [mp.sqrt(s) / 2, 0, 0, -mp.sqrt(s) / 2],
             [mp.sqrt(s) / 2, 0, 0, 0], [mp.sqrt(s) / 2, 0, 0, 0]]
    gf = 1 / (mp.sqrt(2) * Par.v ** 2)
    # PSZ (19) with F_tri = 2/3, F_box = -2/3, C_tri = 3 M_H^2/(s - M_H^2): d sigma/dt
    # = |M|^2_avg/(16 pi s^2) without the identical-particle factor.
    combination = mp.mpf(2) / 3 * 3 * Par.MH ** 2 / (s - Par.MH ** 2) - mp.mpf(2) / 3
    dsdt = gf ** 2 * Par.alpha_s ** 2 / (256 * (2 * mp.pi) ** 3) * combination ** 2
    assert abs(2 * L.gg_hh_let(point, Par) / (16 * mp.pi * s ** 2) / dsdt - 1) < 1e-25
