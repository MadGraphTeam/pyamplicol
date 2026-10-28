#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Deterministic on-shell phase-space points for any masses, built at 60 digits.

``exact_points.py`` builds exact terminating decimals, which exist only for
some mass patterns (one massive subsystem, massless beams). This generator
covers every other pattern: several massive subsystems with different masses
(t t~ h, t t~ b b~, t w-, z h), massive beams (b b~ > h), irrational masses (a
W mass derived at tree level) and the limit families of MASTER_PLAN §5.4.

Construction. Every momentum is computed in ``decimal`` arithmetic at
``CONSTRUCTION_DIGITS`` (60) significant digits: beams along +-z in the
centre-of-mass frame (massive beams allowed), then sequential two-body decays
of the final state, each in the rest frame of its parent with a direction
given by a rational polar cosine and a Pythagorean azimuth, boosted back.
Every component is then rounded to a common absolute quantum of
``PRINTED_DIGITS`` (30) significant digits of sqrt(s), and the last final-state
particle absorbs the rounding residual, so momentum conservation holds exactly
in the printed decimals and every mass shell holds to about 1e-29 relative
(recorded per point). Parameters come from a fixed pseudo-random sequence
(``random.Random(SEED)``), so the points depend only on the masses, the family
and its options.

Families (``--family``):

* ``regular``: generic points, sqrt(s) from a fixed list above threshold, cut
  ``2|p_i.p_j| >= cut*s`` on massless pairs and resonance exclusion on final
  particle-antiparticle pairs (as exact_points.py);
* ``threshold``: a 2->2 final pair of equal masses at velocity beta (one point
  per ``--values`` entry, e.g. 1e-1 1e-2 1e-3), fixed scattering direction;
* ``soft``: the last final-state particle (massless) with energy fraction
  E/sqrt(s) = value, the rest generic;
* ``collinear``: the last two final-state particles (massless) at opening
  angle theta = value, the rest generic;
* ``radiation-zero``: a 2->2 process with one massless final particle (the
  photon) at the polar cosine ``--zero-cosine`` relative to beam 1 (e.g. -1/3 for
  u d~ > w+ a), plus one regular neighbour at ``--neighbour-cosine``;
* ``rest``: a 2->1 process at sqrt(s) = the final mass, the beam axis turned
  by a different rational rotation per point.

``--rotate x`` turns the whole event (beams included) about the x axis by the
rational angle cos = 3/5, sin = 4/5 (beams off the z axis). ``--half-scale-point``
appends a copy of point 1 at half its scale.
"""

import argparse
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from fractions import Fraction as F
import itertools
import json
import random
import sys
from pathlib import Path

CONSTRUCTION_DIGITS = 60
PRINTED_DIGITS = 30
SEED = 20261028
_PYTHAGOREAN = [(F(3, 5), F(4, 5)), (F(7, 25), F(24, 25)), (F(117, 125), F(44, 125)),
                (F(4, 5), F(3, 5)), (F(527, 625), F(336, 625)), (F(-3, 5), F(4, 5)),
                (F(-7, 25), F(-24, 25)), (F(4, 5), F(-3, 5))]
_COSINES = [F(n, 20) for n in range(-17, 18) if n]
_SQRT_S = [F(x) for x in (800, 1000, 1200, 1500, 1750, 2000, 2500, 3000, 3500, 4000)]


def D(x):
    """Exact Decimal of a Fraction or decimal string at the construction precision."""
    if isinstance(x, F):
        return Decimal(x.numerator) / Decimal(x.denominator)
    return Decimal(x)


def dot(p, q):
    return p[0] * q[0] - p[1] * q[1] - p[2] * q[2] - p[3] * q[3]


def direction(cos_theta, azimuth):
    """Unit vector from a rational polar cosine and a Pythagorean (cos, sin) azimuth."""
    c = D(cos_theta)
    s = (1 - c * c).sqrt()
    return [s * D(azimuth[0]), s * D(azimuth[1]), c]


def two_body(mass, m1, m2, n):
    """Momenta of a two-body decay at rest: particle 1 along n, particle 2 opposite."""
    m, a, b = D(mass), D(m1), D(m2)
    lam = (m * m - (a + b) ** 2) * (m * m - (a - b) ** 2)
    if lam < 0:
        raise ValueError("below threshold")
    p = lam.sqrt() / (2 * m)
    e1, e2 = (a * a + p * p).sqrt(), (b * b + p * p).sqrt()
    return [e1, *(p * x for x in n)], [e2, *(-p * x for x in n)]


def boost(q, frame):
    """Boost q from the rest frame of ``frame`` (a timelike momentum) to its frame."""
    mass = dot(frame, frame).sqrt()
    gamma = frame[0] / mass
    beta = [x / frame[0] for x in frame[1:]]
    b2 = sum(x * x for x in beta)
    bq = sum(b * x for b, x in zip(beta, q[1:]))
    factor = ((gamma - 1) * bq / b2 if b2 else 0) + gamma * q[0]
    return [gamma * (q[0] + bq), *(x + factor * b for x, b in zip(q[1:], beta))]


def beams(sqrt_s, m1, m2):
    s, a, b = D(sqrt_s) ** 2, D(m1), D(m2)
    lam = (s - (a + b) ** 2) * (s - (a - b) ** 2)
    p = lam.sqrt() / (2 * D(sqrt_s))
    e1, e2 = (s + a * a - b * b) / (2 * D(sqrt_s)), (s + b * b - a * a) / (2 * D(sqrt_s))
    return [e1, Decimal(0), Decimal(0), p], [e2, Decimal(0), Decimal(0), -p]


def sequential(sqrt_s, masses, chooser, remainder_masses=None, directions=None):
    """Final-state momenta in the centre-of-mass frame: particle k is emitted
    from the remaining system, whose mass is drawn between threshold and the
    parent mass (or taken from ``remainder_masses``)."""
    masses = [D(m) for m in masses]
    parent = [D(sqrt_s), Decimal(0), Decimal(0), Decimal(0)]
    out = []
    for k in range(len(masses) - 1):
        rest = masses[k + 1:]
        parent_mass = dot(parent, parent).sqrt()
        if remainder_masses is not None and remainder_masses[k] is not None:
            m_rest = D(remainder_masses[k])
        elif len(rest) == 1:
            m_rest = rest[0]
        else:
            low, high = sum(rest), parent_mass - masses[k]
            m_rest = low + D(chooser.choice([F(n, 10) for n in range(2, 9)])) * (high - low)
        n = (directions[k] if directions is not None and directions[k] is not None
             else direction(chooser.choice(_COSINES), chooser.choice(_PYTHAGOREAN)))
        emitted, system = two_body(parent_mass, masses[k], m_rest, n)
        out.append(boost(emitted, parent))
        parent = boost(system, parent)
    out.append(parent)
    return out


def sin_cos(theta):
    """sin and cos of a Decimal angle by their Taylor series (small angles)."""
    sin, cos, term, k = Decimal(0), Decimal(0), Decimal(1), 0
    while True:
        if k % 2 == 0:
            cos += term if k % 4 == 0 else -term
        else:
            sin += term if k % 4 == 1 else -term
        k += 1
        term = term * theta / k
        if abs(term) < Decimal(10) ** (-2 * CONSTRUCTION_DIGITS):
            return sin, cos


def collinear_pair(sqrt_s, final, theta, chooser, z=F(2, 5)):
    """The last two (massless) particles at opening angle ``theta`` in the
    centre-of-mass frame, with energies z E and (1 - z) E of their pair: the
    pair system (mass^2 = 2 z (1 - z) E^2 (1 - cos theta)) recoils against the
    other particles, which decay sequentially."""
    rest = final[:-2]
    sin_t, cos_t = sin_cos(theta)
    c = 2 * D(z) * (1 - D(z)) * (1 - cos_t)
    root_s = D(sqrt_s)
    s = root_s * root_s
    if len(rest) == 1:
        r = D(rest[0])
    else:
        low = sum(D(m) for m in rest)
        r = low + D(chooser.choice([F(n, 10) for n in range(2, 9)])) * (root_s - low)
    energy = (s - r * r) / (root_s + (s - c * (s - r * r)).sqrt())
    mass = (c * energy * energy).sqrt()
    n = direction(chooser.choice(_COSINES), chooser.choice(_PYTHAGOREAN))
    pair, system = two_body(root_s, mass, r, n)
    momentum = (pair[0] ** 2 - mass * mass).sqrt()
    e4, e5 = D(z) * pair[0], (1 - D(z)) * pair[0]
    sin_a, sin_b = e5 * sin_t / momentum, e4 * sin_t / momentum
    cos_a, cos_b = (1 - sin_a ** 2).sqrt(), (1 - sin_b ** 2).sqrt()
    # A unit vector orthogonal to n.
    helper = [Decimal(1), Decimal(0), Decimal(0)] if abs(n[0]) < Decimal("0.9") else [Decimal(0), Decimal(1), Decimal(0)]
    e = [helper[1] * n[2] - helper[2] * n[1], helper[2] * n[0] - helper[0] * n[2], helper[0] * n[1] - helper[1] * n[0]]
    norm = sum(x * x for x in e).sqrt()
    e = [x / norm for x in e]
    p4 = [e4, *(e4 * (cos_a * a + sin_a * b) for a, b in zip(n, e))]
    p5 = [e5, *(e5 * (cos_b * a - sin_b * b) for a, b in zip(n, e))]
    if len(rest) == 1:
        others = [system]
    else:
        others = [boost(q, system) for q in sequential(r, rest, chooser)]
    return [*others, p4, p5]


def rotate_x(point):
    c, s = D(F(3, 5)), D(F(4, 5))
    return [[p[0], p[1], c * p[2] - s * p[3], s * p[2] + c * p[3]] for p in point]


def rotation(index):
    """A deterministic rational rotation (product of two Pythagorean rotations)."""
    (c1, s1), (c2, s2) = _PYTHAGOREAN[index % len(_PYTHAGOREAN)], _PYTHAGOREAN[(3 * index + 1) % len(_PYTHAGOREAN)]
    c1, s1, c2, s2 = map(D, (c1, s1, c2, s2))
    rx = ((1, 0, 0), (0, c1, -s1), (0, s1, c1))
    ry = ((c2, 0, s2), (0, 1, 0), (-s2, 0, c2))
    m = [[sum(D(rx[i][k]) * D(ry[k][j]) for k in range(3)) for j in range(3)] for i in range(3)]
    return lambda p: [p[0], *(sum(m[i][k] * p[1 + k] for k in range(3)) for i in range(3))]


def quantise(point, sqrt_s, incoming=2):
    """Round every component to the common quantum; the last final particle
    takes the residual so momentum conservation is exact in the printed decimals."""
    exponent = D(sqrt_s).adjusted() - PRINTED_DIGITS + 1
    quantum = Decimal(1).scaleb(exponent)
    rounded = [[x.quantize(quantum, rounding=ROUND_HALF_EVEN) for x in p] for p in point]
    total_in = [sum(p[mu] for p in rounded[:incoming]) for mu in range(4)]
    others = [sum(p[mu] for p in rounded[incoming:-1]) for mu in range(4)]
    rounded[-1] = [total_in[mu] - others[mu] for mu in range(4)]
    return rounded


def text(x):
    t = format(x.normalize(), "f")
    if "." in t:
        t = t.rstrip("0").rstrip(".")
    return "0" if t in ("", "-0") else t


def passes_cuts(point, masses, cut, resonances, pdgs, incoming=2):
    s = dot([a + b for a, b in zip(point[0], point[1])], [a + b for a, b in zip(point[0], point[1])])
    for (i, p), (j, q) in itertools.combinations(enumerate(point), 2):
        if not masses[i] and not masses[j] and 2 * abs(dot(p, q)) < D(cut) * s:
            return False
    final = point[incoming:]
    for (i, p), (j, q) in itertools.combinations(enumerate(final), 2):
        if pdgs is not None and pdgs[incoming + i] != -pdgs[incoming + j]:
            continue
        pair = [x + y for x, y in zip(p, q)]
        pair_s = dot(pair, pair)
        if any(abs(pair_s - D(r) ** 2) < D(r) ** 2 / 10 for r in resonances):
            return False
    return True


def generate(masses, family="regular", count=3, values=(), cut=F(1, 1000), resonances=(), pdgs=None,
             rotate=None, zero_cosine=None, neighbour_cosine=None, incoming=2):
    """Return (points, sqrt_s list, labels) as Decimal momenta [[E, px, py, pz], ...]."""
    if incoming != 2:
        raise ValueError("only 2->n scattering is implemented")
    chooser = random.Random(SEED)
    initial, final = masses[:incoming], masses[incoming:]
    threshold = max(sum(D(m) for m in initial), sum(D(m) for m in final))
    points, scales, labels = [], [], []

    def finish(final_momenta, sqrt_s, label, turn=None):
        b1, b2 = beams(sqrt_s, *initial)
        point = [b1, b2, *final_momenta]
        if turn is not None:
            point = [turn(p) for p in point]
        if rotate == "x":
            point = rotate_x(point)
        points.append(point)
        scales.append(sqrt_s)
        labels.append(label)

    if family == "rest":
        if len(final) != 1:
            raise ValueError("family 'rest' is a 2->1 process")
        sqrt_s = F(final[0])
        for index in range(count):
            finish([[D(sqrt_s), Decimal(0), Decimal(0), Decimal(0)]], sqrt_s, f"rest frame, beam rotation {index}",
                   rotation(index))
        return points, scales, labels
    if family == "threshold":
        if len(final) != 2 or final[0] != final[1] or not final[0]:
            raise ValueError("family 'threshold' needs a final pair of equal nonzero masses")
        n = direction(F(3, 5), _PYTHAGOREAN[1])
        for beta in values:
            with localcontext() as context:
                context.prec = CONSTRUCTION_DIGITS
                sqrt_s_d = 2 * D(final[0]) / (1 - D(beta) ** 2).sqrt()
            # sqrt(s) is irrational: the quantisation below rounds it with the momenta.
            pair = two_body(sqrt_s_d, final[0], final[1], n)
            finish(list(pair), F(sqrt_s_d), f"threshold beta={beta}")
        return points, scales, labels
    if family == "radiation-zero":
        if len(final) != 2 or (final[0] and final[1]):
            raise ValueError("family 'radiation-zero' needs a 2->2 process with one massless final particle")
        photon = 0 if not final[0] else 1
        sqrt_s_list = [s for s in _SQRT_S if D(s) > 2 * threshold][:count]
        cosines = [(zero_cosine, "radiation zero")] * len(sqrt_s_list) + [(neighbour_cosine, "regular neighbour")]
        for index, (cosine, label) in enumerate(cosines):
            sqrt_s = sqrt_s_list[min(index, len(sqrt_s_list) - 1)]
            n = direction(cosine, _PYTHAGOREAN[index % len(_PYTHAGOREAN)])
            other = [-x for x in n]
            first, second = (n, other) if photon == 0 else (other, n)
            pair = two_body(sqrt_s, final[0], final[1], first)
            finish(list(pair), sqrt_s, f"{label} cos(beam1, massless)={cosine}")
        return points, scales, labels

    scales_ok = [s for s in _SQRT_S if D(s) > threshold * D(F(13, 10)) and D(s) > threshold + 50]
    if not scales_ok:
        raise ValueError("threshold above the sqrt(s) list")
    targets = list(values) if family in ("soft", "collinear") else [None] * count
    for target in targets:
        for trial in itertools.count(1):
            if trial % 10000 == 0:
                print(f"supplied_points: {trial} candidates tried", file=sys.stderr)
            sqrt_s = chooser.choice(scales_ok)
            try:
                if family == "soft":
                    if final[-1]:
                        raise ValueError("soft family needs a massless last particle")
                    order = [len(final) - 1, *range(len(final) - 1)]
                    reordered = [final[i] for i in order]
                    energy = D(target) * D(sqrt_s)
                    m_rest = (D(sqrt_s) ** 2 - 2 * D(sqrt_s) * energy).sqrt()
                    momenta = sequential(sqrt_s, reordered, chooser, [m_rest] + [None] * (len(final) - 2))
                    final_momenta = [None] * len(final)
                    for slot, p in zip(order, momenta):
                        final_momenta[slot] = p
                elif family == "collinear":
                    if final[-1] or final[-2]:
                        raise ValueError("collinear family needs two massless last particles")
                    final_momenta = collinear_pair(sqrt_s, final, D(target), chooser)
                else:
                    final_momenta = sequential(sqrt_s, final, chooser)
            except ValueError:
                continue
            b1, b2 = beams(sqrt_s, *initial)
            if family == "regular" and not passes_cuts([b1, b2, *final_momenta], masses, cut, resonances, pdgs):
                continue
            if sqrt_s in scales and family == "regular":
                continue
            finish(final_momenta, sqrt_s, family if target is None else f"{family} {target}")
            break
    return points, scales, labels


def measure(point, masses, incoming=2):
    """Largest |p^2 - m^2| / E^2 and largest momentum-conservation defect / E."""
    shell = max(abs(dot(p, p) - D(m) ** 2) / p[0] ** 2 for p, m in zip(point, masses))
    scale = max(p[0] for p in point)
    conservation = max(abs(sum(p[mu] for p in point[:incoming]) - sum(p[mu] for p in point[incoming:]))
                       for mu in range(4)) / scale
    return shell, conservation


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--process", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--family", default="regular",
                        choices=("regular", "threshold", "soft", "collinear", "radiation-zero", "rest"))
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--values", nargs="*", default=[], help="beta / energy fractions / angles of a limit family")
    parser.add_argument("--zero-cosine", default="-1/3")
    parser.add_argument("--neighbour-cosine", default="-1/5")
    parser.add_argument("--rotate", choices=("x",))
    parser.add_argument("--mu-r", nargs="+", default=["1000", "700", "1400"])
    parser.add_argument("--cut", default="1/1000", help="minimal 2|p_i.p_j|/s of massless pairs (regular family)")
    parser.add_argument("--half-scale-point", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import required_spec
    from exact_points import decimal_string

    spec = required_spec.load_process(args.spec or required_spec.DEFAULT_SPEC, args.process)
    masses = required_spec.masses(spec)
    values = {**spec["scheme_data"]["parameters"], **spec["scheme_data"]["fixed_parameters"]}
    resonances = [values[n] for n in ("MZ", "MW", "MH", "MT") if n in values and F(values[n])]
    if "MW" not in values:
        resonances.append(required_spec.derived_mw(spec["scheme_data"]))
    with localcontext() as context:
        context.prec = CONSTRUCTION_DIGITS
        points, scales, labels = generate(
            masses, args.family, args.count, [F(v) for v in args.values], F(args.cut),
            [F(r) for r in resonances], spec["pdgs"], args.rotate, F(args.zero_cosine), F(args.neighbour_cosine))
        printed = [quantise(p, s) for p, s in zip(points, scales)]
        defects = [measure(p, masses) for p in printed]
    if args.half_scale_point:
        printed.append(printed[0])
        labels.append(labels[0] + " (mu_R = mu_0/2)")
        defects.append(defects[0])
    mu_r = list(itertools.islice(itertools.cycle(args.mu_r), len(points)))
    if args.half_scale_point:
        mu_r.append(decimal_string(F(mu_r[0]) / 2))
    report = {
        "process_name": spec["name"],
        "pdgs": spec["pdgs"],
        "masses": [decimal_string(m) for m in masses],
        "construction": (
            f"tools/loop_reference/supplied_points.py: deterministic sequential construction at "
            f"{CONSTRUCTION_DIGITS} digits, printed on a common quantum of {PRINTED_DIGITS} significant digits "
            "of sqrt(s); momentum conservation exact in the printed decimals (the last final particle takes "
            "the rounding residual), mass shells to the recorded defects"),
        "family": args.family,
        "family_values": args.values,
        "rotation": "about x by cos=3/5, sin=4/5 (beams off the z axis)" if args.rotate == "x" else None,
        "point_labels": labels,
        "cuts": {"min_2pipj_over_s": args.cut, "resonance_exclusion":
                 "|s_ij-M^2| >= M^2/10 for final particle-antiparticle pairs (regular family)",
                 "resonances": [str(r) for r in resonances]},
        "sqrt_s": [text(D(s)) for s in scales] + ([text(D(scales[0]))] if args.half_scale_point else []),
        "points": [[[text(x) for x in leg] for leg in point] for point in printed],
        "mu_r": mu_r,
        "precision": {
            "construction_digits": CONSTRUCTION_DIGITS, "printed_digits": PRINTED_DIGITS,
            "max_relative_mass_shell_defect": [f"{d[0]:.3e}" for d in defects],
            "max_relative_momentum_conservation_defect": [f"{d[1]:.3e}" for d in defects]},
    }
    if args.half_scale_point:
        report["scale_variation"] = {"point": len(printed), "copy_of_point": 1, "mu_r_factor": "1/2"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
