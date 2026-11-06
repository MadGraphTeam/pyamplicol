#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Analytic oracles for loop-induced |A_loop|^2 (M-LIT rows LI-A1 ... LI-A7, LI-Z*).

Arbitrary precision (mpmath, ``mp.dps`` set by the caller or ``DEFAULT_DPS``).
Every function returns MadLoop's convention for the squared matrix element:
summed over final and averaged over initial helicities and colours, with the
final-state identical-particle factor (``required_spec.normalization``).
Physical couplings, no loop factor extracted.

Sources (TeX sources under ``workspace/reference/papers/li-*``):

* LI-A1/A2 ``g g > h``, ``h > g g``: Spira, hep-ph/9705337, eq. (eq:hgglo),
  ``Gamma(H->gg) = G_F alpha_s^2 M_H^3/(36 sqrt2 pi^3) |sum_Q A_Q(tau_Q)|^2``,
  ``A_Q = 3/2 tau [1 + (1 - tau) f(tau)]``, ``tau = 4 m_Q^2/M_H^2``. Crossing gives
  ``|M|^2_avg(gg>h) = alpha_s^2 M_H^4/(576 pi^2 v^2) |sum A_Q|^2``.
* LI-A3/LI-E2 ``h > a a``, ``a a > h``: Djouadi, hep-ph/0503172, eq. (eq:hgaga),
  ``A_1/2``, ``A_1`` with ``tau = M_H^2/(4 M^2)``.
* LI-A4 ``h > z a``: Spira, hep-ph/9705337, eq. (eq:hzga) (= Djouadi eq. (eq:hzga)
  with his ``g`` read at the argument ``tau^-1``): ``I_1``, ``I_2`` with
  ``tau = 4 M^2/M_H^2``, ``lambda = 4 M^2/M_Z^2``.
* LI-A5/LI-A6 ``g g > a a``, ``a a > a a``: the one-loop helicity amplitudes of
  Gounaris, Porfyriadis, Renard, hep-ph/9902230, Appendix A (W loop of Jikia and
  Tkabladze, hep-ph/9312228; fermion loop of Glover and van der Bij, the
  Karplus-Neuman box) in terms of ``B_0``, ``C_0``, ``D_0`` at equal internal
  masses; the massless fermion loop also from Bern, De Freitas, Dixon, Ghinculov,
  Wong, hep-ph/0109079, eq. (OneLoopFunctions) (= the Bern-Dixon-Schmidt
  ``g g > a a`` functions, hep-ph/0206194, up to the colour factor).
* LI-A7 ``g g > h h`` low-energy theorem: Plehn, Spira, Zerwas, hep-ph/9603205,
  eqs. (13), (19): ``F_tri = 2/3``, ``F_box = -2/3``, ``G_box = 0``; the HEFT
  normalisation of ``g g > h`` (the shipped built-in-sm-heft coupling stops at
  ``r^3``, ``r = M_H^2/m_t^2``).

Scalar integrals: ``B_0``, ``C_0(0,0,s)``, ``D_0(0,0,0,0;s,t)`` at equal internal
mass m (``int d^4q/(i pi^2)``, the Passarino-Veltman normalisation of the
sources), closed forms evaluated with a complex mass ``m^2 (1 - i delta)``:
the ``s + i0`` prescription (``delta = 10^-(dps-10)``; the closed forms are
continuous in delta, ``test_li_analytic.py`` checks them against Feynman-
parameter integrals). The ``D_0`` form is the standard one of the massless-leg
equal-mass box (its overall factor 2 fixed against the Feynman-parameter
integral).

Nothing here is process-keyed beyond the formula of each row.
"""

from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

import mpmath as mp

DEFAULT_DPS = 50
HERE = Path(__file__).resolve().parent

# Charged SM fermions: (charge, colours, weak isospin I3 of the left-handed field).
FERMIONS = {
    "e": (Fraction(-1), 1, Fraction(-1, 2)), "mu": (Fraction(-1), 1, Fraction(-1, 2)),
    "tau": (Fraction(-1), 1, Fraction(-1, 2)),
    "u": (Fraction(2, 3), 3, Fraction(1, 2)), "c": (Fraction(2, 3), 3, Fraction(1, 2)),
    "t": (Fraction(2, 3), 3, Fraction(1, 2)),
    "d": (Fraction(-1, 3), 3, Fraction(-1, 2)), "s": (Fraction(-1, 3), 3, Fraction(-1, 2)),
    "b": (Fraction(-1, 3), 3, Fraction(-1, 2)),
}
QUARKS = ("u", "d", "s", "c", "b", "t")
MASS_NAMES = {"e": "Me", "mu": "MM", "tau": "MTA", "c": "MC", "b": "MB", "t": "MT"}


def _mpf(x):
    return mp.mpf(Fraction(x).numerator) / Fraction(x).denominator if isinstance(x, (Fraction, int)) else mp.mpf(x)


# ----------------------------------------------------------------- parameters

class Parameters:
    """Model inputs of a ``required_processes.json`` scheme as mpmath numbers:
    ``alpha_s``, ``alpha`` (the scheme's: 1/aEWM1 or the G_mu value), ``v`` =
    (sqrt2 G_F)^-1/2 (the tree relation of both schemes), ``MW`` (derived at
    tree level in the fixed-alpha scheme), ``MZ``, ``MH``, ``sw2`` = 1 -
    MW^2/MZ^2, and the fermion masses (0 where the scheme lists none)."""

    def __init__(self, scheme):
        sys.path.insert(0, str(HERE))
        import required_spec

        values = {**scheme["parameters"], **scheme["fixed_parameters"]}
        self.alpha_s = mp.mpf(values["aS"])
        gf = mp.mpf(values["Gf"])
        self.MZ = mp.mpf(values["MZ"])
        self.MH = mp.mpf(values["MH"])
        if "MW" in values:
            self.MW = mp.mpf(values["MW"])
        elif scheme["electroweak_inputs"] == "alpha_fixed":
            # Recomputed at the working precision (required_spec.derived_mw prints 30 digits).
            alpha = 1 / mp.mpf(values["aEWM1"])
            mz2 = self.MZ ** 2
            self.MW = mp.sqrt(mz2 / 2 + mp.sqrt(mz2 ** 2 / 4 - alpha * mp.pi * mz2 / (gf * mp.sqrt(2))))
        else:
            self.MW = mp.mpf(required_spec.derived_mw(scheme))
        self.sw2 = 1 - self.MW ** 2 / self.MZ ** 2
        if scheme["electroweak_inputs"] == "alpha_fixed":
            self.alpha = 1 / mp.mpf(values["aEWM1"])
        elif scheme["electroweak_inputs"] == "gmu":
            self.alpha = mp.sqrt(2) * gf * self.MW ** 2 * self.sw2 / mp.pi
        else:
            raise NotImplementedError(f"electroweak inputs {scheme['electroweak_inputs']!r}")
        if scheme.get("complex_mass_scheme"):
            raise NotImplementedError("the analytic oracles use real masses")
        self.GF = gf
        self.v = 1 / mp.sqrt(mp.sqrt(2) * gf)
        self.masses = {f: mp.mpf(values[MASS_NAMES[f]]) if MASS_NAMES.get(f) in values else mp.mpf(0)
                       for f in FERMIONS}
        for name, f in (("ymb", "b"), ("ymt", "t"), ("ymtau", "tau"), ("ymc", "c"), ("ymm", "mu"), ("yme", "e")):
            if name in values and mp.mpf(values[name]) != self.masses[f]:
                raise NotImplementedError(f"Yukawa mass {name} differs from the pole mass")
        # Yukawa couplings m_f / v (the tree relation of the schemes' UFOs).
        self.yukawa = dict(self.masses)
        self.loop_quark_flavours = int(scheme.get("loop_quark_flavours", 6))


# ----------------------------------------------------------- scalar integrals

def _delta():
    return mp.mpf(10) ** (-(mp.mp.dps - 10))


def _m2(m):
    """m^2 (1 - i delta): the s + i0 prescription of every closed form."""
    return mp.mpc(m * m, -m * m * _delta())


def _beta(x, m2):
    return mp.sqrt(1 - 4 * m2 / x)


def b0_finite(x, m):
    """B_0(x; m, m) minus its UV pole Delta, at mu = m (only differences enter)."""
    m2 = _m2(m)
    b = _beta(x, m2)
    return 2 - b * mp.log((b + 1) / (b - 1))


def c0(x, m):
    """C_0(0, 0, x; m, m, m) = ln^2((beta+1)/(beta-1)) / (2 x)."""
    m2 = _m2(m)
    b = _beta(x, m2)
    return mp.log((b + 1) / (b - 1)) ** 2 / (2 * x)


def d0(s, t, m):
    """D_0(0, 0, 0, 0; s, t; m, m, m, m) (massless external legs, equal masses)."""
    m2 = _m2(m)
    bs, bt = _beta(s, m2), _beta(t, m2)
    bst = mp.sqrt(1 - 4 * m2 * (s + t) / (s * t))
    res = (2 * mp.log((bst + bs) / (bst + bt)) ** 2
           + mp.log((bst - bs) / (bst + bs)) * mp.log((bst - bt) / (bst + bt)) - mp.pi ** 2 / 2)
    for bi in (bs, bt):
        res += (2 * mp.polylog(2, (bi - 1) / (bst + bi)) - 2 * mp.polylog(2, -(bst - bi) / (bi + 1))
                - mp.log((bi + 1) / (bst + bi)) ** 2)
    return 2 * res / (s * t * bst)


# ------------------------------------------------------ light-by-light boxes

def lbl_w(s, t, u, mw):
    """GPR (A.W++++), (A.W+++-), (A.W++--): F^W / alpha^2 of the W loop."""
    dsum = d0(s, t, mw) + d0(s, u, mw) + d0(t, u, mw)
    m2 = mw * mw
    pppp = (12 - 12 * (1 + 2 * u / s) * b0_finite(u, mw) - 12 * (1 + 2 * t / s) * b0_finite(t, mw)
            + 24 * m2 * t * u / s * d0(u, t, mw)
            + 16 * (1 - 3 * m2 / (2 * s) - 3 * t * u / (4 * s * s))
            * (2 * t * c0(t, mw) + 2 * u * c0(u, mw) - t * u * d0(t, u, mw))
            + 8 * (s - m2) * (s - 3 * m2) * dsum)
    pppm = (-12 + 24 * m2 * m2 * dsum
            + 12 * m2 * s * t * u * (d0(s, t, mw) / u ** 2 + d0(s, u, mw) / t ** 2 + d0(t, u, mw) / s ** 2)
            - 24 * m2 * (1 / s + 1 / t + 1 / u) * (t * c0(t, mw) + u * c0(u, mw) + s * c0(s, mw)))
    ppmm = -12 + 24 * m2 * m2 * dsum
    return pppp, pppm, ppmm


def lbl_fermion(s, t, u, m):
    """GPR (A.f++++), (A.f+++-), (A.f++--): F^f / (alpha^2 Q^4) of one colourless
    fermion of unit charge and mass m > 0 (Glover-van der Bij)."""
    m2 = m * m
    pppp = (-8 + 8 * (1 + 2 * u / s) * b0_finite(u, m) + 8 * (1 + 2 * t / s) * b0_finite(t, m)
            - 8 * ((t * t + u * u) / (s * s) - 4 * m2 / s) * (t * c0(t, m) + u * c0(u, m))
            + 8 * m2 * (s - 2 * m2) * (d0(s, t, m) + d0(s, u, m))
            - 4 * (4 * m2 * m2 - (2 * s * m2 + t * u) * (t * t + u * u) / (s * s) + 4 * m2 * t * u / s)
            * d0(t, u, m))
    _, w_pppm, w_ppmm = lbl_w(s, t, u, m)
    return pppp, -mp.mpf(2) / 3 * w_pppm, -mp.mpf(2) / 3 * w_ppmm


def lbl_massless(s, t, u):
    """Bern et al. hep-ph/0109079 eq. (OneLoopFunctions): M^(1) of a massless
    fermion (F^f = 8 N Q^4 alpha^2 M^(1)), their t = (k1-k4)^2, u = (k1-k3)^2.
    Returns (M_{++++}, M_{-+++}, M_{--++}, M_{+--+}(s,t,u), M_{+--+}(s,u,t))."""
    lt = mp.log(-t / s)
    lu = mp.log(-u / s)

    def pmmp(t_, u_, l_):
        return (-(t_ ** 2 + s ** 2) / (2 * u_ ** 2) * l_ ** 2 - (t_ - s) / u_ * l_ - 1
                - 1j * mp.pi * ((t_ ** 2 + s ** 2) / u_ ** 2 * l_ + (t_ - s) / u_))

    pppp = -(t * t + u * u) / (2 * s * s) * (mp.log(t / u) ** 2 + mp.pi ** 2) - (t - u) / s * mp.log(t / u) - 1
    return pppp, 1, 1, pmmp(t, u, lt), pmmp(u, t, lu)


def lbl_helicity_sum(amplitudes):
    """sum over the 16 helicities of |F|^2 from {(s,t,u): (F++++, F+++-, F++--)}
    evaluated at the three crossings (GPR (++++1), (++++2), (+++-), (++--))."""
    (pppp, pppm, ppmm), crossed_ut, crossed_ts = amplitudes
    return (8 * abs(pppm) ** 2 + 2 * abs(ppmm) ** 2 + 2 * abs(pppp) ** 2
            + 2 * abs(crossed_ut) ** 2 + 2 * abs(crossed_ts) ** 2)


def _mandelstam(point):
    p = [[mp.mpf(x) for x in leg] for leg in point]

    def sq(a, b, sign):
        q = [a[i] + sign * b[i] for i in range(4)]
        return q[0] ** 2 - q[1] ** 2 - q[2] ** 2 - q[3] ** 2

    s = sq(p[0], p[1], 1)
    t = sq(p[0], p[2], -1)
    u = sq(p[0], p[3], -1)
    return s, t, u


def _box_sum(loops, s, t, u):
    """Coherent sum over loops ``[(weight, kind, mass)]`` of the three
    independent amplitudes at (s,t,u), (u,t,s) and (t,s,u); ``kind`` is
    "fermion" (weight multiplies F^f/(alpha^2 Q^4)) or "w" (F^W/alpha^2)."""
    out = []
    for args in ((s, t, u), (u, t, s), (t, s, u)):
        total = [mp.mpc(0), mp.mpc(0), mp.mpc(0)]
        for weight, kind, mass in loops:
            amps = lbl_w(*args, mass) if kind == "w" else lbl_fermion(*args, mass)
            for i in range(3):
                total[i] += weight * amps[i]
        out.append(total)
    return [out[0], out[1][0], out[2][0]]


def _massless_regulator(s):
    """Mass standing in for a massless loop fermion: the massive amplitudes at
    m^2 = s 10^-(dps/2) differ from the massless ones by O(m^2 log^4 m^2 / s)."""
    return mp.sqrt(abs(s)) * mp.mpf(10) ** (-(mp.mp.dps // 4))


def aa_aa(point, par, w_loop=True):
    """LI-A6: complete [QED] a a > a a (every charged fermion and the W loop):
    (1/4)(1/2) sum_hel |F|^2."""
    s, t, u = _mandelstam(point)
    loops = []
    for f, (q, nc, _) in FERMIONS.items():
        m = par.masses[f] or _massless_regulator(s)
        loops.append((nc * _mpf(q) ** 4 * par.alpha ** 2, "fermion", m))
    if w_loop:
        loops.append((par.alpha ** 2, "w", par.MW))
    return lbl_helicity_sum(_box_sum(loops, s, t, u)) / 8


def gg_aa(point, par, quarks=QUARKS):
    """LI-A5: g g > a a through the quark boxes: per quark of charge Q the
    photon-loop amplitude with alpha^2 Q^4 N -> alpha alpha_s Q^2 delta^ab / 2
    (no triple-gluon diagrams: the photons do not couple to gluons);
    sum_colour (delta^ab/2)^2 = 2, average 1/(4 * 64), identical photons 1/2."""
    s, t, u = _mandelstam(point)
    loops = []
    for f in quarks:
        q = _mpf(FERMIONS[f][0])
        m = par.masses[f] or _massless_regulator(s)
        loops.append((par.alpha * par.alpha_s * q * q, "fermion", m))
    return 2 * lbl_helicity_sum(_box_sum(loops, s, t, u)) / (4 * 64 * 2)


def gg_aa_massless(point, par, quarks=QUARKS[:5]):
    """LI-A5 massless quarks only, from the published massless functions
    (hep-ph/0109079 / hep-ph/0206194): F = 8 M^(1) alpha alpha_s Q^2 per quark."""
    s, t, u = _mandelstam(point)
    m = lbl_massless(s, t, u)
    weight = 8 * par.alpha * par.alpha_s * sum(_mpf(FERMIONS[f][0]) ** 2 for f in quarks)
    total = 8 * abs(m[1]) ** 2 + 2 * abs(m[2]) ** 2 + 2 * abs(m[0]) ** 2 + 2 * abs(m[3]) ** 2 + 2 * abs(m[4]) ** 2
    return 2 * weight ** 2 * total / (4 * 64 * 2)


# --------------------------------------------------------- Higgs form factors

def f_spira(tau):
    """Spira's f(tau), tau = 4 m^2 / M^2 (tau < 1: above threshold, complex)."""
    tau = mp.mpf(tau)
    if tau >= 1:
        return mp.asin(1 / mp.sqrt(tau)) ** 2
    r = mp.sqrt(1 - tau)
    return -(mp.log((1 + r) / (1 - r)) - 1j * mp.pi) ** 2 / 4


def g_spira(tau):
    tau = mp.mpf(tau)
    if tau >= 1:
        return mp.sqrt(tau - 1) * mp.asin(1 / mp.sqrt(tau))
    r = mp.sqrt(1 - tau)
    return r / 2 * (mp.log((1 + r) / (1 - r)) - 1j * mp.pi)


def a_q(tau):
    """Spira A_Q^H(tau) (-> 1 for a heavy quark)."""
    return mp.mpf(3) / 2 * tau * (1 + (1 - tau) * f_spira(tau))


def a_half(tau_d):
    """Djouadi A_1/2^H(tau), tau = M_H^2 / (4 m^2) (-> 4/3 for a heavy fermion)."""
    f = f_spira(1 / tau_d)
    return 2 * (tau_d + (tau_d - 1) * f) / tau_d ** 2


def a_one(tau_d):
    """Djouadi A_1^H(tau), tau = M_H^2 / (4 M_W^2) (-> -7 for a heavy W)."""
    f = f_spira(1 / tau_d)
    return -(2 * tau_d ** 2 + 3 * tau_d + 3 * (2 * tau_d - 1) * f) / tau_d ** 2


def _quarks_gg(par):
    return [f for f in QUARKS if par.yukawa[f]]


def gg_h(par):
    """LI-A1: |M|^2 of g g > h (averaged), every quark with a Yukawa coupling."""
    amp = sum(a_q(4 * par.masses[f] ** 2 / par.MH ** 2) for f in _quarks_gg(par))
    return par.alpha_s ** 2 * par.MH ** 4 / (576 * mp.pi ** 2 * par.v ** 2) * abs(amp) ** 2


def h_gg(par):
    """LI-A2: h > g g, MadLoop's convention (identical gluons 1/2): 256/2 x gg>h."""
    return 128 * gg_h(par)


def gamma_h_aa(par):
    total = sum(FERMIONS[f][1] * _mpf(FERMIONS[f][0]) ** 2 * a_half(par.MH ** 2 / (4 * par.masses[f] ** 2))
                for f in FERMIONS if par.yukawa[f])
    total += a_one(par.MH ** 2 / (4 * par.MW ** 2))
    return par.GF * par.alpha ** 2 * par.MH ** 3 / (128 * mp.sqrt(2) * mp.pi ** 3) * abs(total) ** 2


def h_aa(par):
    """LI-A3: h > a a, (1/2) sum |M|^2 = 16 pi M_H Gamma."""
    return 16 * mp.pi * par.MH * gamma_h_aa(par)


def aa_h(par):
    """LI-E2: a a > h, sum |M|^2 / 4 = 8 pi M_H Gamma(h > a a)."""
    return 8 * mp.pi * par.MH * gamma_h_aa(par)


def _i1(tau, lam):
    return (tau * lam / (2 * (tau - lam)) + tau ** 2 * lam ** 2 / (2 * (tau - lam) ** 2) * (f_spira(tau) - f_spira(lam))
            + tau ** 2 * lam / (tau - lam) ** 2 * (g_spira(tau) - g_spira(lam)))


def _i2(tau, lam):
    return -tau * lam / (2 * (tau - lam)) * (f_spira(tau) - f_spira(lam))


def gamma_h_za(par):
    cw = mp.sqrt(1 - par.sw2)
    tw2 = par.sw2 / cw ** 2
    total = mp.mpc(0)
    for f, (q, nc, i3) in FERMIONS.items():
        if not par.yukawa[f]:
            continue
        m = par.masses[f]
        tau, lam = 4 * m ** 2 / par.MH ** 2, 4 * m ** 2 / par.MZ ** 2
        vhat = 2 * _mpf(i3) - 4 * _mpf(q) * par.sw2
        total += nc * _mpf(q) * vhat / cw * (_i1(tau, lam) - _i2(tau, lam))
    tau, lam = 4 * par.MW ** 2 / par.MH ** 2, 4 * par.MW ** 2 / par.MZ ** 2
    total += cw * (4 * (3 - tw2) * _i2(tau, lam) + ((1 + 2 / tau) * tw2 - (5 + 2 / tau)) * _i1(tau, lam))
    return (par.GF ** 2 * par.MW ** 2 * par.alpha * par.MH ** 3 / (64 * mp.pi ** 4)
            * (1 - par.MZ ** 2 / par.MH ** 2) ** 3 * abs(total) ** 2)


def h_za(par):
    """LI-A4: h > z a, sum |M|^2 = 16 pi M_H Gamma / (1 - M_Z^2/M_H^2)."""
    return 16 * mp.pi * par.MH * gamma_h_za(par) / (1 - par.MZ ** 2 / par.MH ** 2)


# ----------------------------------------------------------------- LI-A7

HEFT_SHIPPED = (mp.mpf(1), mp.mpf(7) / 120, mp.mpf(1) / 168, mp.mpf(13) / 16800)  # built-in-sm-heft GH through r^3


def heft_ratio(par):
    """|A_t(tau)|^2 over the shipped HEFT coupling's |1 + 7/120 r + 1/168 r^2 +
    13/16800 r^3|^2 (r = M_H^2/m_t^2; top only): expected 1 + 2 (2/17325) r^4."""
    mt = par.masses["t"]
    r = par.MH ** 2 / mt ** 2
    heft = sum(c * r ** k for k, c in enumerate(HEFT_SHIPPED))
    exact = abs(a_q(4 * mt ** 2 / par.MH ** 2)) ** 2
    return exact / heft ** 2, 1 + 2 * mp.mpf(2) / 17325 * r ** 4


def gg_hh_let(point, par):
    """LI-A7: g g > h h in the m_t -> infinity limit (low-energy theorem),
    MadLoop's convention (identical Higgs bosons 1/2):
    alpha_s^2 s^2 / (1152 pi^2 v^4) (3 M_H^2/(s - M_H^2) - 1)^2."""
    s, _, _ = _mandelstam(point)
    return par.alpha_s ** 2 * s ** 2 / (1152 * mp.pi ** 2 * par.v ** 4) * (3 * par.MH ** 2 / (s - par.MH ** 2) - 1) ** 2


# ------------------------------------------------------------ zero rows

ZERO_ROWS = {
    "LI-Z1": {"processes": ["h > g a", "z > g a"], "kind": "exact",
              "reason": "every colour coefficient vanishes (Tr T^a = 0): exact 0 with the colour record"},
    "LI-Z1b": {"processes": ["g g > a a a", "g g > h a"], "kind": "numerical",
               "reason": "Furry cancellation between the two loop orientations, outside the closed-fermion "
                         "certificate: |A|^2 <= 10 E_abs (binary64 and DD), no theorem-based declaration (Q13)"},
    "LI-Z2": {"processes": ["g g > z", "z > g g", "e+ e- > g g"], "kind": "numerical",
              "reason": "integrated zeros (Landau-Yang, vector-current integrand zero, lepton-current "
                        "conservation): |A|^2 <= 10 E_abs (binary64 and DD), no theorem-based declaration (Q13)"},
}


# ------------------------------------------------------------ dispatcher

ROWS = {
    "gg_h": lambda point, par: gg_h(par),
    "h_gg": lambda point, par: h_gg(par),
    "h_aa": lambda point, par: h_aa(par),
    "aa_h": lambda point, par: aa_h(par),
    "h_za": lambda point, par: h_za(par),
    "gg_aa": gg_aa,
    "gg_aa_massless": gg_aa_massless,
    "aa_aa": aa_aa,
    "gg_hh_let": gg_hh_let,
}


def evaluate(oracle, scheme, points, dps=DEFAULT_DPS):
    """[|M|^2 as a decimal string] of ``oracle`` (a ``ROWS`` key) at ``points``."""
    with mp.workdps(dps):
        par = Parameters(scheme)
        return [mp.nstr(mp.re(ROWS[oracle](point, par)), dps - 10, strip_zeros=False) for point in points]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--process", required=True, help="process of required_processes.json with an \"analytic\" key")
    parser.add_argument("--points", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dps", type=int, default=DEFAULT_DPS)
    args = parser.parse_args()
    sys.path.insert(0, str(HERE))
    import required_spec

    spec = required_spec.load_process(args.spec or required_spec.DEFAULT_SPEC, args.process)
    points = json.loads(args.points.read_text())
    if points["pdgs"] != spec["pdgs"]:
        raise SystemExit("points JSON belongs to another process")
    out = {"process_name": spec["name"], "oracles": {}}
    for oracle in spec["analytic"]:
        out["oracles"][oracle] = evaluate(oracle, spec["scheme_data"], points["points"], args.dps)
    out["dps"] = args.dps
    out["source"] = "tools/loop_reference/li_analytic.py (mpmath)"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
