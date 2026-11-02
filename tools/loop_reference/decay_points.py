#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Deterministic exact on-shell 1->n decay points in the decaying particle's rest frame.

The decaying particle (mass M, the first leg) is at rest, ``(M, 0, 0, 0)``.
Every component is an exact rational; every mass shell and momentum
conservation hold exactly in rational arithmetic and are asserted.

Construction (any masses, any n >= 2). The final state is split by sequential
two-body decays, each in the rest frame of its parent system: the first
particle of the current system recoils against the rest, whose invariant mass
is a seeded rational between its threshold and the parent's mass minus the
first mass (the last two particles have no freedom). In the parent's rest
frame the first particle takes ``E = (M^2 + m^2 - M_rest^2) / (2 M)`` and a
momentum ``p`` with ``p.p = E^2 - m^2`` exactly: a rational point on that
sphere (a rational radius along z, or a three-square representation, below),
turned by a seeded rational rotation (an integer quaternion's matrix). The rest system is
boosted back with ``gamma = E_rest / M_rest`` (rational, since every system
mass is rational). Massless particles are split off first, so a sphere of
irrational radius occurs only where two massive particles share the last
two-body decay (``h > b b~`` with massive b).

A sphere of squared radius ``q = N / D`` (lowest terms) holds a rational point
exactly when the integer ``N D`` is a sum of three squares, i.e. not of the
form ``4^a (8 b + 7)`` (Legendre); such a configuration is refused, naming
it. Candidates are kept if every pair of massless final particles satisfies
``2 p_i.p_j >= cut M^2`` and, from 1 -> 3 on, every final particle-antiparticle
pair stays away from the resonance masses (``|s_ij - R^2| >= R^2/10``, as
exact_points.py).

``decimal_point`` prints a point for a Fortran reader: every component rounded
to a common quantum of ``PRINTED_DIGITS`` significant digits of M, the last
final particle absorbing the residual so momentum conservation stays exact
in the printed decimals (mass shells hold to ~1e-30 relative), as
supplied_points.py does.
"""

import argparse
import itertools
import json
import math
import random
import sys
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from fractions import Fraction as F
from pathlib import Path

SEED = 20261101
PRINTED_DIGITS = 32
# The seeded system masses: rationals with this denominator between the bounds.
_MASS_GRID = 10**4


def dot(p, q):
    return p[0] * q[0] - p[1] * q[1] - p[2] * q[2] - p[3] * q[3]


def _square_root(value):
    """The exact rational square root of ``value``, or None."""
    if value < 0:
        return None
    num, den = math.isqrt(value.numerator), math.isqrt(value.denominator)
    if num * num == value.numerator and den * den == value.denominator:
        return F(num, den)
    return None


_SMALL_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47)


def _probable_prime(n):
    """Miller-Rabin with the first 15 prime bases (deterministic below 3e23;
    a false positive is caught by the caller's exact check)."""
    if n < 2:
        return False
    for prime in _SMALL_PRIMES:
        if n % prime == 0:
            return n == prime
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for base in _SMALL_PRIMES:
        x = pow(base, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime_two_squares(p):
    """(a, b) with a^2 + b^2 = p for a prime p = 1 (mod 4) (Cornacchia,
    Hermite-Serret), or None if p is no such prime after all."""
    for base in range(2, p):
        if pow(base, (p - 1) // 2, p) == p - 1:
            root = pow(base, (p - 1) // 4, p)
            break
    else:
        return None
    a, b = p, root
    limit = math.isqrt(p)
    while b > limit:
        a, b = b, a % b
    rest = p - b * b
    c = math.isqrt(rest)
    return (b, c) if c * c == rest else None


def _two_squares(m):
    """(a, b) with a^2 + b^2 = m when m = 2^e p with p = 1 or a prime
    p = 1 (mod 4); None otherwise (the caller draws another m)."""
    if m == 0:
        return 0, 0
    e = 0
    while m % 2 == 0:
        m //= 2
        e += 1
    if m == 1:
        a, b = 1, 0
    elif m % 4 == 1 and _probable_prime(m):
        pair = _prime_two_squares(m)
        if pair is None:
            return None
        a, b = pair
    else:
        return None
    for _ in range(e):  # times (1 + i)
        a, b = a - b, a + b
    return abs(a), abs(b)


def three_squares(n, chooser):
    """Integers (a, b, c) with a^2 + b^2 + c^2 = n (n >= 0), drawing c until
    n - c^2 is 2^e times 1 or a prime = 1 (mod 4) (Rabin-Shallit style; about
    log n draws); None if n = 4^a (8b + 7) (Legendre)."""
    m = n
    while m and m % 4 == 0:
        m //= 4
    if m % 8 == 7:
        return None
    top = math.isqrt(n)
    small = [] if top > 64 else list(range(top + 1))
    for draw in itertools.count():
        if small:
            if draw >= len(small):
                break
            c = small[draw]
        else:
            c = chooser.randrange(top + 1)
        pair = _two_squares(n - c * c)
        if pair is not None and pair[0] ** 2 + pair[1] ** 2 == n - c * c:
            return (*pair, c)
    # Small n: every c tried; fall back to the exhaustive two-square search.
    for c in range(top + 1):
        rest = n - c * c
        for a in range(math.isqrt(rest // 2) + 1):
            b = math.isqrt(rest - a * a)
            if a * a + b * b == rest:
                return a, b, c
    raise AssertionError(f"Legendre: {n} is a sum of three squares")


def _rotation(chooser):
    """A seeded rational rotation: the matrix of an integer quaternion over its norm."""
    while True:
        a, b, c, d = (chooser.randint(-9, 9) for _ in range(4))
        norm = a * a + b * b + c * c + d * d
        if norm:
            break
    n = F(norm)
    return (
        ((a * a + b * b - c * c - d * d) / n, 2 * (b * c - a * d) / n, 2 * (b * d + a * c) / n),
        (2 * (b * c + a * d) / n, (a * a - b * b + c * c - d * d) / n, 2 * (c * d - a * b) / n),
        (2 * (b * d - a * c) / n, 2 * (c * d + a * b) / n, (a * a - b * b - c * c + d * d) / n),
    )


def sphere_point(q, chooser):
    """A rational vector of squared length ``q`` (a seeded rotation of one
    rational point of that sphere), or None if the sphere has none."""
    radius = _square_root(q)
    if radius is not None:
        base = (F(0), F(0), radius)
    else:
        integer = q.numerator * q.denominator  # q = integer / denominator^2
        solution = three_squares(integer, chooser)
        if solution is None:
            return None
        base = tuple(F(x, q.denominator) for x in solution)
    matrix = _rotation(chooser)
    point = tuple(sum(matrix[i][k] * base[k] for k in range(3)) for i in range(3))
    assert sum(x * x for x in point) == q
    return point


def _boost(k, system, mass):
    """``k`` from the rest frame of ``system`` (mass ``mass``) to the frame of ``system``."""
    energy = (system[0] * k[0] + sum(system[i] * k[i] for i in (1, 2, 3))) / mass
    shift = (k[0] + energy) / (system[0] + mass)
    return [energy, *(k[i] + system[i] * shift for i in (1, 2, 3))]


def _split(mass, indices, masses, chooser):
    """Momenta of ``indices`` (masses ``masses``) in the rest frame of their
    system of mass ``mass``, or None (a sphere without rational points)."""
    first, rest = indices[0], indices[1:]
    m1 = masses[first]
    if len(rest) == 1:
        rest_mass = masses[rest[0]]
    else:
        low, high = sum(masses[i] for i in rest), mass - m1
        rest_mass = low + (high - low) * F(chooser.randrange(1, _MASS_GRID), _MASS_GRID)
    energy = (mass * mass + m1 * m1 - rest_mass * rest_mass) / (2 * mass)
    q = energy * energy - m1 * m1
    if q <= 0:
        return None
    space = sphere_point(q, chooser)
    if space is None:
        return None
    system = [mass - energy, *(-x for x in space)]
    out = {first: [energy, *space]}
    if len(rest) == 1:
        out[rest[0]] = system  # massless or not: no rest frame needed
        return out
    inner = _split(rest_mass, rest, masses, chooser)
    if inner is None:
        return None
    for index, momentum in inner.items():
        out[index] = _boost(momentum, system, rest_mass)
    return out


def check(point, masses):
    """Exact mass shells, positive energies and momentum conservation of a
    1 -> n point (the first leg decays)."""
    for p, m in zip(point, masses, strict=True):
        if dot(p, p) != m * m or p[0] <= 0:
            raise AssertionError("mass shell violated")
    for mu in range(4):
        if point[0][mu] != sum(p[mu] for p in point[1:]):
            raise AssertionError("momentum conservation violated")


def _passes(point, masses, cut, resonances, pdgs):
    s = masses[0] ** 2
    final = list(zip(point[1:], masses[1:], strict=True))
    for (p, m), (q, n) in itertools.combinations(final, 2):
        if not m and not n and 2 * dot(p, q) < cut * s:
            return False
    # A pair that is the whole final state (1 -> 2) has the decaying mass: no
    # propagator of it can be resonant.
    if pdgs is not None and len(point) > 3:
        for (i, p), (j, q) in itertools.combinations(enumerate(point[1:], 1), 2):
            if pdgs[i] != -pdgs[j]:
                continue
            pair = [x + y for x, y in zip(p, q, strict=True)]
            pair_s = dot(pair, pair)
            if any(abs(pair_s - F(r) ** 2) < F(r) ** 2 / 10 for r in resonances):
                return False
    return True


def generate(masses, count=3, cut=F(1, 1000), resonances=(), pdgs=None, seed=SEED):
    """``count`` distinct exact rest-frame points ``[[E, px, py, pz], ...]`` of
    the decay of a particle of mass ``masses[0]`` into ``masses[1:]``."""
    masses = [F(m) for m in masses]
    if len(masses) < 3 or masses[0] <= sum(masses[1:]):
        raise ValueError(f"no decay of mass {masses[0]} into masses {[str(m) for m in masses[1:]]}")
    # Massless particles first: their sphere radius is rational.
    order = sorted(range(1, len(masses)), key=lambda i: (masses[i] != 0, i))
    chooser = random.Random(seed)
    accepted, seen = [], set()
    for trial in itertools.count(1):
        if trial % 10000 == 0:
            print(f"decay_points: {trial} candidates, {len(accepted)} accepted", file=sys.stderr)
        momenta = _split(masses[0], order, masses, chooser)
        if momenta is None:
            if len(masses) == 3:
                raise ValueError(
                    f"the two-body decay of mass {masses[0]} into {masses[1]} and {masses[2]} has no "
                    "rational momentum (|p|^2 N D of the form 4^a (8b+7)); supply decimal points")
            continue
        point = [[masses[0], F(0), F(0), F(0)], *(momenta[i] for i in range(1, len(masses)))]
        key = tuple(x for p in point for x in p)
        if key in seen or not _passes(point, masses, cut, resonances, pdgs):
            continue
        check(point, masses)
        accepted.append(point)
        seen.add(key)
        if len(accepted) == count:
            return accepted
    raise AssertionError("unreachable")


def decimal_point(point, digits=PRINTED_DIGITS):
    """``point`` as decimal strings: a common quantum of ``digits`` significant
    digits of the decaying mass; the last final particle takes the residual."""
    with localcontext() as context:
        context.prec = 2 * digits + 20
        mass = Decimal(point[0][0].numerator) / Decimal(point[0][0].denominator)
        quantum = Decimal(1).scaleb(mass.adjusted() - digits + 1)
        rounded = [[(Decimal(x.numerator) / Decimal(x.denominator)).quantize(quantum, rounding=ROUND_HALF_EVEN)
                    for x in p] for p in point]
        rounded[-1] = [rounded[0][mu] - sum(p[mu] for p in rounded[1:-1]) for mu in range(4)]
    return [[_text(x) for x in p] for p in rounded]


def _text(x):
    t = format(x, "f")
    if "." in t:
        t = t.rstrip("0").rstrip(".")
    return "0" if t in ("", "-0") else t


def exact_text(x):
    """An exact rational as text: a terminating decimal or 'numerator/denominator'."""
    d = x.denominator
    for prime in (2, 5):
        while d % prime == 0:
            d //= prime
    if d == 1:
        with localcontext() as context:
            context.prec = 400
            return _text(Decimal(x.numerator) / Decimal(x.denominator))
    return f"{x.numerator}/{x.denominator}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--process", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--cut", default="1/1000", help="minimal 2 p_i.p_j / M^2 of massless final pairs")
    parser.add_argument("--half-scale-point", action="store_true",
                        help="append a copy of point 1 at half its scale (mu_R = mu_0/2)")
    args = parser.parse_args()
    import required_spec

    spec = required_spec.load_process(args.spec or required_spec.DEFAULT_SPEC, args.process)
    if spec.get("initial", 2) != 1:
        raise SystemExit(f"{args.process} is not a decay (\"initial\": 1)")
    masses = required_spec.masses(spec)
    values = {**spec["scheme_data"]["parameters"], **spec["scheme_data"]["fixed_parameters"]}
    resonances = [values[name] for name in ("MZ", "MW", "MH", "MT") if name in values and F(values[name])]
    exact = generate(masses, args.count, F(args.cut), resonances, pdgs=spec["pdgs"])
    points = [decimal_point(p) for p in exact]
    # mu_R = the decaying particle's mass (the decay's only scale).
    mu_r = [exact_text(masses[0])] * args.count
    if args.half_scale_point:
        points.append(points[0])
        mu_r.append(exact_text(masses[0] / 2))
    report = {
        "process_name": spec["name"],
        "pdgs": spec["pdgs"],
        "masses": [exact_text(m) for m in masses],
        "construction": f"tools/loop_reference/decay_points.py (seed {SEED}): exact rational rest-frame "
                        f"sequential two-body construction, printed to {PRINTED_DIGITS} digits with exact "
                        "momentum conservation in the printed decimals",
        "cuts": {"min_2pipj_over_M2": args.cut,
                 "resonance_exclusion": "|s_ij-M^2| >= M^2/10 for final particle-antiparticle pairs",
                 "resonances": resonances},
        "sqrt_s": [exact_text(masses[0])] * len(points),
        "points": points,
        "exact_points": [[[exact_text(x) for x in leg] for leg in point] for point in exact],
        "mu_r": mu_r,
    }
    if args.half_scale_point:
        report["scale_variation"] = {"point": len(points), "copy_of_point": 1, "mu_r_factor": "1/2"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
