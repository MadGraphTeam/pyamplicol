# SPDX-License-Identifier: 0BSD
"""One meaning of the colour accuracies for trees and loops
(``docs/correlator-conventions.md``, "One loop: the same keywords").

``strict-lc``/``strict-nlc`` are the formal 1/N_c expansion of the virtual;
the inherited ``lc``/``nlc`` keep the tree currents' U(1)-subtraction pieces
at N_c = 3 as the tree engine does, grade the counterterm and field couplings
by the colour declaration, and (``nlc`` with open quark lines) keep or drop
each Born-metric entry whole. Oracles:

* the closed-form colour sums of the Born (Ellis-Stirling-Webber Table 7.1
  with N_c symbolic; the inherited columns are the tree engine's, as tabled in
  ``docs/correlator-conventions.md``), as ratios to the full-colour Born of
  the same slice at the same point, so normalisation and couplings cancel:

  ========== ============== ============ ============== ============ ======
  process    exact          ``lc``       ``nlc``        strict LC    strict NLC
  ========== ============== ============ ============== ============ ======
  u u~>d d~  (N^2-1)/4      (N^2+1)/4    exact          N^2/4        exact
  u u~>g g   N^3X-N(X+1)+1/N N^3 X       exact          N^3 X        (N^3-N)X-N
  g g>g g    N^4-N^2        N^4          exact          N^4          exact
  ========== ============== ============ ============== ============ ======

  with X = (t^2 + u^2)/s^2;
* where the tree currents carry no U(1)-subtraction piece (pure gluons; one
  quark line without an internal gluon between lines, Drell-Yan) the
  inherited and the strict accuracies are the same projection, so the whole
  virtual agrees exactly;
* a sector whose leading exact degree differs from the reference degree is
  refused (``colour-reference-degree``).
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "loop" / "legacy"
PARAMETERS = {"aS": "0.118", "MT": "173"}
TOLERANCE = 1e-12


@pytest.fixture(scope="module")
def loop_sm(loop_sm_compiled_model):
    from pyamplicol.models.loading import load_compiled_model

    return load_compiled_model(loop_sm_compiled_model)


@pytest.fixture(scope="module")
def built(loop_sm, loop_native):
    """``(process, born QCD, accuracy) -> LoopSlice`` with the shipped
    loop_sm colour declaration (QCD Born, QCD correction)."""

    from pyamplicol.loops.v2.assemble import LoopSlice, SliceRequest
    from pyamplicol.models.loop_color_declaration import (
        resolve_loop_color_declaration,
    )
    from tools.loop_reference import legacy_capture

    declaration = resolve_loop_color_declaration(loop_sm.raw_loop_model)
    cache = {}

    def build(process: str, qcd: int, accuracy: str):
        key = (process, qcd, accuracy)
        if key not in cache:
            cache[key] = LoopSlice.generate(
                loop_sm,
                SliceRequest(
                    process,
                    {"QCD": qcd, "QED": 0},
                    {"QCD": qcd + 2, "QED": 0},
                    fixed_parameters=legacy_capture.FIXED_PARAMETERS,
                    accuracy=accuracy,
                    colour_declaration=None if accuracy == "full" else declaration,
                    colour_contraction="direct",
                ),
                loop_native,
            )
        return cache[key]

    return build


def _point(name: str):
    fixture = json.loads((FIXTURES / f"{name}.json").read_text())
    return fixture["points"][0], fixture["scales_squared"][0]


def _mandelstam_x(point) -> float:
    p1, p2, p3 = (tuple(map(float, p)) for p in point[:3])

    def square(p):
        return p[0] ** 2 - p[1] ** 2 - p[2] ** 2 - p[3] ** 2

    s = square(tuple(a + b for a, b in zip(p1, p2, strict=True)))
    t = square(tuple(a - b for a, b in zip(p1, p3, strict=True)))
    u = -s - t
    return (t * t + u * u) / (s * s)


def _born(slice_, point, scale) -> float:
    from pyamplicol.loops.v2.assemble import Precision

    result = slice_.evaluate(
        point, scale, parameters=PARAMETERS, precision=Precision.double()
    )
    (value,) = result.born.values()
    return float(value)


def _expected(process: str, accuracy: str, x: float) -> float:
    """Truncated over full colour sum at N_c = 3 (module docstring)."""

    n = 3.0
    if process == "u u~ > d d~":
        full = n * n - 1.0
        return {
            "lc": (n * n + 1.0) / full,
            "nlc": 1.0,
            "strict-lc": n * n / full,
            "strict-nlc": 1.0,
        }[accuracy]
    if process == "u u~ > g g":
        full = n**3 * x - n * (x + 1.0) + 1.0 / n
        return {
            "lc": n**3 * x / full,
            "nlc": 1.0,
            "strict-lc": n**3 * x / full,
            "strict-nlc": ((n**3 - n) * x - n) / full,
        }[accuracy]
    if process == "g g > g g":
        full = n**4 - n**2
        return {
            "lc": n**4 / full,
            "nlc": 1.0,
            "strict-lc": n**4 / full,
            "strict-nlc": 1.0,
        }[accuracy]
    raise AssertionError(process)


# (process, Born QCD order, fixture whose point 0 is a 2 -> 2 point)
BORNS = (
    ("u u~ > d d~", 2, "uux_uux"),
    ("u u~ > g g", 2, "gg_gg"),
    ("g g > g g", 2, "gg_gg"),
)


@pytest.mark.loop_physics
@pytest.mark.parametrize("accuracy", ("lc", "nlc", "strict-lc", "strict-nlc"))
@pytest.mark.parametrize(("process", "qcd", "fixture"), BORNS)
def test_born_of_every_accuracy_is_the_closed_form_colour_sum(
    built, process, qcd, fixture, accuracy
):
    """The Born of a loop artifact at each accuracy over its full-colour
    Born: the inherited columns are the tree engine's (``lc`` keeps the
    U(1)-subtraction piece of u u~ > d d~ at N_c = 3; ``nlc`` keeps the
    open-line entries whole), the strict ones the formal expansion."""

    point, scale = _point(fixture)
    full = _born(built(process, qcd, "full"), point, scale)
    mine = _born(built(process, qcd, accuracy), point, scale)
    expected = _expected(process, accuracy, _mandelstam_x(point))
    assert abs(mine / full - expected) <= TOLERANCE * abs(expected), (
        mine / full,
        expected,
    )


@pytest.mark.loop_physics
@pytest.mark.parametrize(
    ("process", "qcd", "fixture", "depth"),
    [
        ("g g > g g", 2, "gg_gg", "lc"),
        ("g g > g g", 2, "gg_gg", "nlc"),
        ("u u~ > g g g", 3, "uux_ggg", "lc"),
    ],
)
def test_inherited_equals_strict_without_u1_pieces(built, process, qcd, fixture, depth):
    """No tree current of these processes holds a U(1)-subtraction piece, so
    the inherited and strict projections are the same where no open-line
    Born-metric entry is kept whole (pure gluons; LC of one quark line): the
    Born and every component of the virtual agree to binary64 rounding (the
    counterterms are graded by the declaration in both). The inherited NLC
    of u u~ > g g g keeps whole entries and differs (its Born is the tree
    engine's, 0.9963 of full colour at the fixture point against the strict
    expansion's)."""

    from pyamplicol.loops.v2.assemble import Precision

    point, scale = _point(fixture)
    values = {}
    for accuracy in (depth, f"strict-{depth}"):
        result = built(process, qcd, accuracy).evaluate(
            point, scale, parameters=PARAMETERS, precision=Precision.double()
        )
        values[accuracy] = [float(v) for v in result.born.values()] + [
            float(c)
            for component in result.components.values()
            for laurent in component.values()
            for c in laurent.coefficients
        ]
    inherited, strict = values[depth], values[f"strict-{depth}"]
    scale_ = max(map(abs, strict))
    assert len(inherited) == len(strict)
    for a, b in zip(inherited, strict, strict=True):
        assert abs(a - b) <= TOLERANCE * scale_, (a, b)


@pytest.mark.loop_physics
def test_inherited_lc_keeps_the_counterterms(built):
    """Inherited LC grades the counterterm couplings by the declaration: at
    N_c = 3 they would sit one power below the loops (the structural degrees
    of u u~ > d d~ g: Born 3, virtual 4, counterterm and field cells 3) and
    the projection would drop every UV and R2 counterterm. Their components
    are kept, at the size of the strict LC ones."""

    from pyamplicol.loops.v2.assemble import Precision

    point, scale = _point("uux_ddxg")
    sizes = {}
    for accuracy in ("lc", "strict-lc"):
        slice_ = built("u u~ > d d~ g", 3, accuracy)
        assert slice_.reference_degrees()["virtual"] == {
            sector: 4 for sector, _pairs in slice_.sectors
        }
        result = slice_.evaluate(
            point, scale, parameters=PARAMETERS, precision=Precision.double()
        )
        sizes[accuracy] = {
            component: max(
                abs(float(c))
                for laurent in result.components[component].values()
                for c in laurent.coefficients
            )
            for component in ("uv", "r2")
        }
    for component, strict in sizes["strict-lc"].items():
        assert strict > 0
        assert 0.5 * strict < sizes["lc"][component] < 2 * strict, (component, sizes)


@pytest.mark.loop_fast
def test_a_degree_off_the_reference_is_refused(monkeypatch):
    """``LoopSlice.require_reference_degrees`` refuses a sector whose
    leading exact degree differs from the reference degree, naming the
    listed rule, instead of truncating at the sector's own leading term."""

    from pyamplicol.loops.v2.assemble import LoopSlice
    from pyamplicol.loops.v2.refusals import (
        LOOP_ADMISSION_REFUSALS,
        LoopRequestUnsupported,
    )

    class Stub:
        request = type("R", (), {"process": "u u~ > d d~"})()
        require_reference_degrees = LoopSlice.require_reference_degrees

        def degrees(self):
            return {"born": {"b": 2}, "virtual": {"s": 2}}

        def reference_degrees(self):
            return {"born": {"b": 2}, "virtual": {"s": 3}}

    with pytest.raises(LoopRequestUnsupported) as refused:
        Stub().require_reference_degrees()
    assert refused.value.key == "colour-reference-degree"
    assert "colour-reference-degree" in {rule.key for rule in LOOP_ADMISSION_REFUSALS}


def test_whole_born_entries_follow_the_tree_rule():
    """``colour.whole_entry``: an entry whose top power reaches P - 2 keeps
    its exact value at N_c = 3 at that power; a lower entry is left to the
    projection. u u~ > g g (P = 3): the diagonal N^3 - 2N + 1/N keeps 64/3,
    the off-diagonal -N + 1/N (top power P - 2) keeps -8/3 whole."""

    from pyamplicol.color.connections import ExactColorCoefficient as C
    from pyamplicol.loops.v2.colour import kept, whole_entry

    def at_three(cell, degree, accuracy):
        return sum(
            (
                value.real * Fraction(3) ** power
                for power, value in cell.items()
                if kept(power, degree, accuracy)
            ),
            Fraction(0),
        )

    diagonal = {3: C(1), 1: C(-2), -1: C(1)}
    off = {1: C(-1), -1: C(1)}
    assert at_three(diagonal, 3, "nlc") == 21
    assert at_three(whole_entry(diagonal, 3), 3, "nlc") == Fraction(64, 3)
    assert at_three(whole_entry(off, 3), 3, "nlc") == Fraction(-8, 3)
    low = {0: C(1), -2: C(1)}
    assert whole_entry(low, 3) is low


# (loop control, tree process, its QCD order): quark lines with gluons,
# distinct and identical flavours.
TREE_CONTROLS = (
    ("uux_ddxg", "u u~ > d d~ g", 3),
    ("uux_uux", "u u~ > u u~", 2),
    ("uux_uuxg", "u u~ > u u~ g", 3),
    ("uux_ggg", "u u~ > g g g", 3),
)


@pytest.fixture(scope="module")
def tree_ratios(tmp_path_factory):
    """``(control, accuracy) ->`` the tree engine's inherited |M|^2 over its
    full colour at the control's point 0 (built-in SM, QCD trees)."""

    from pyamplicol import Generator, ModelSource, Runtime
    from pyamplicol.config import (
        ColorConfig,
        GenerationConfig,
        GenerationValidationConfig,
        ProcessConfig,
        RunConfig,
    )

    root = tmp_path_factory.mktemp("inherited-trees")
    out = {}
    for name, process, qcd in TREE_CONTROLS:
        point, _scale = _point(name)
        momenta = (tuple(tuple(map(float, p)) for p in point),)
        values = {}
        for accuracy in ("full", "lc", "nlc"):
            config = RunConfig(
                action="generate",
                process=ProcessConfig(
                    coupling_order_policy="explicit",
                    max_coupling_orders={"QCD": qcd, "QED": 0},
                ),
                color=ColorConfig(accuracy=accuracy),
                generation=GenerationConfig(
                    workers=1,
                    emit_api_bundle=False,
                    validation=GenerationValidationConfig(
                        enabled=False, post_build_validation=False
                    ),
                ),
            )
            path = root / f"{name}-{accuracy}"
            Generator(config).generate(process, path, model=ModelSource.built_in_sm())
            values[accuracy] = complex(Runtime.load(path).evaluate(momenta)[0]).real
        for accuracy in ("lc", "nlc"):
            out[name, accuracy] = values[accuracy] / values["full"]
    return out


@pytest.mark.loop_physics
@pytest.mark.parametrize("accuracy", ("lc", "nlc"))
@pytest.mark.parametrize(("name", "process", "qcd"), TREE_CONTROLS)
def test_inherited_born_is_the_tree_engines(
    built, tree_ratios, name, process, qcd, accuracy
):
    """The Born of an inherited-accuracy loop artifact over its full colour
    equals the tree engine's |M|^2 at that accuracy over its full colour
    (the loop's tree-level closures and blocks keep the U(1)-subtraction
    pieces at N_c = 3; inherited NLC keeps open-line Born-metric entries
    whole), to binary64 rounding."""

    point, scale = _point(name)
    full = _born(built(process, qcd, "full"), point, scale)
    mine = _born(built(process, qcd, accuracy), point, scale) / full
    expected = tree_ratios[name, accuracy]
    assert abs(mine - expected) <= TOLERANCE * abs(expected), (mine, expected)
