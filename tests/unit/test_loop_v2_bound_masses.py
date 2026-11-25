# SPDX-License-Identifier: 0BSD
"""The external masses of a loop artifact's kinematics are the masses its
amplitude binds (``generation.validation.bound_external_masses``).

A card's ``[loop.preparation] fixed_parameters`` (here a top mass other than
the model's own) define the masses the amplitude binds: the stored
validation point, its record's ``"masses"``, the model parameter record
(``model/parameters.json``) and the flat phase-space points of
``evaluate`` / ``profile`` (``cli.flat_points``) are on those shells, and
the double pole of the virtual at those points is Catani's,
-(alpha_s / 2 pi) sum_i C_i Born over the massless coloured legs, with both
reduction backends. Before, the validation point (and so every flat point)
was on the model's own shells while the amplitude bound the fixed masses:
the double pole of u u~ > t t~ with MT fixed to 160 (the model's 173) missed
Catani's by 5e-3 and the two backends disagreed. A process whose fixed
parameters bind no external mass keeps its validation point bit for bit.

The cheapest processes that show the defect run in the default tier; the
campaign's g g > t t~ h card (MT = ymt = 173, MH = 125 on the restriction's
174.3 / 120) is the nightly control.
"""

from __future__ import annotations

import json
import math
import sys
from fractions import Fraction
from pathlib import Path

import pytest

ALPHA_S = 0.118
CA, CF = 3.0, 4.0 / 3.0
# Catani's double pole relative to the Born, at points on shell to binary64.
POLE_TOLERANCE = 1e-9


def _card(root: Path, model: str, restriction: str, expression: str, fixed: dict):
    from pyamplicol.api import Generator, ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config

    root.mkdir(parents=True, exist_ok=True)
    entries = ", ".join(
        f"{name} = {json.dumps(value)}" for name, value in fixed.items()
    )
    card = root / "card.toml"
    card.write_text(
        f"""action = "generate"
[model]
source = "{model}"
restriction = "{restriction}"
[process]
entries = [{{expression = {json.dumps(expression)}, name = "p"}}]
loop_coupling_orders = ["QCD"]
[loop]
external_widths = "zero"
[loop.preparation]
fixed_parameters = {{{entries}}}
[generation]
output = "artifact"
emit_api_bundle = false
"""
    )
    config = resolve_config(card)
    output = Path(config.effective.generation.output)
    Generator(config).generate(
        ProcessSet((ProcessRequest.parse(expression, name="p"),)), output
    )
    return output


def _record(artifact: Path) -> dict:
    return json.loads(
        (artifact / "processes" / "p" / "validation-momenta.json").read_text()
    )


def _shell_defect(momentum, mass: float) -> float:
    """|p^2 - m^2| relative to E^2, exactly (the stored binary64 digits)."""

    e, x, y, z = (Fraction(str(value)) for value in momentum)
    m = Fraction(str(mass))
    return float(abs(e * e - x * x - y * y - z * z - m * m) / (e * e))


def _assert_on_shell(point, masses) -> None:
    # A binary64 point on shell: its p^2 within a few roundings of E^2.
    for momentum, mass in zip(point, masses, strict=True):
        assert _shell_defect(momentum, mass) <= 16 * sys.float_info.epsilon, (
            momentum,
            mass,
        )


def _double_poles(
    artifact: Path,
    points: list,
    scales: list,
    backend: str,
    parameters: dict | None = None,
    process: str | None = None,
):
    """dp / Born per point on ``backend`` in binary64 (each point a success
    without a shell-consistency mark)."""

    from pyamplicol.api import Runtime
    from pyamplicol.kinematics import is_shell_reason

    runtime = Runtime.load(artifact, process=process, model_parameters=parameters)
    result = runtime.evaluate(
        points, mu_r2=scales, reduction=backend, arithmetic="double"
    )
    out = []
    for index in range(len(points)):
        assert str(result.statuses[index]) == "success", result.statuses[index]
        marks = result.diagnostics[index].uncertified
        assert not any(is_shell_reason(reason) for reason in marks), marks
        born = sum(complex(value).real for value in result.born_values[index])
        pole = sum(complex(v.double_pole).real for v in result.values[index])
        out.append(pole / born)
    return out


@pytest.fixture(scope="module")
def uux_ttx(tmp_path_factory):
    """u u~ > t t~ (QCD) on loop_sm with the top mass fixed to 160 (the
    model's 173)."""

    return _card(
        tmp_path_factory.mktemp("bound-masses"),
        "loop_sm",
        "no_b_mass",
        "u u~ > t t~",
        {"MT": "160", "ymt": "160"},
    )


@pytest.mark.loop_physics
def test_the_validation_point_is_on_the_bound_shells(uux_ttx):
    record = _record(uux_ttx)
    assert record["masses"] == ["0", "0", "160", "160"]
    (point,) = record["points"]
    _assert_on_shell([entry["momentum"] for entry in point], [0.0, 0.0, 160.0, 160.0])
    parameters = json.loads((uux_ttx / "model" / "parameters.json").read_text())
    values = parameters["parameters"]
    assert values["MT"] == [160.0, 0.0] and values["ymt"] == [160.0, 0.0]
    # The stable top of loop.external_widths = "zero", bound as well.
    assert values["WT"] == [0.0, 0.0]


@pytest.mark.loop_physics
def test_the_flat_points_are_on_the_bound_shells(uux_ttx):
    from pyamplicol.cli.flat_points import draw_flat_points

    flat = draw_flat_points(uux_ttx, process=None, points=4, seed=3, sqrt_s=None)
    assert flat.masses == (0.0, 0.0, 160.0, 160.0)
    for point in flat.points:
        _assert_on_shell(point, flat.masses)


@pytest.mark.loop_physics
@pytest.mark.parametrize("backend", ("ninjars", "tirust"))
def test_the_double_pole_at_flat_points_is_catani(uux_ttx, backend):
    from pyamplicol.cli.flat_points import draw_flat_points

    flat = draw_flat_points(uux_ttx, process=None, points=3, seed=5, sqrt_s=None)
    expected = -ALPHA_S / (2 * math.pi) * 2 * CF
    for ratio in _double_poles(
        uux_ttx, flat.as_inputs(exact=False), flat.mu_r2(), backend
    ):
        assert abs(ratio / expected - 1) <= POLE_TOLERANCE, ratio


# The validation point of u u~ > t t~ on loop_sm (no_b_mass, MT = 173) at
# the generation's default seed, as the generation stored it before the bound
# masses (69f7f95e3): fixed parameters that bind no external mass keep it bit
# for bit.
_UNCHANGED_POINT = [
    ["500", "0", "0", "500"],
    ["500", "0", "0", "-500"],
    [
        "500.00000000000159",
        "255.87591557407896",
        "-275.22870728816946",
        "-280.79828082381761",
    ],
    [
        "499.99999999999852",
        "-255.8759155740764",
        "275.2287072881652",
        "280.79828082381869",
    ],
]


@pytest.mark.loop_physics
def test_fixed_parameters_of_no_external_mass_keep_the_point(tmp_path):
    artifact = _card(tmp_path, "loop_sm", "no_b_mass", "u u~ > t t~", {"MH": "130"})
    record = _record(artifact)
    assert record["seed"] == 12345
    assert record["masses"] == ["0", "0", "173", "173"]
    (point,) = record["points"]
    assert [entry["momentum"] for entry in point] == _UNCHANGED_POINT
    values = json.loads((artifact / "model" / "parameters.json").read_text())
    assert values["parameters"]["MT"] == [173.0, 0.0]
    # The fixed Higgs mass is bound, and so recorded.
    assert values["parameters"]["MH"] == [130.0, 0.0]


@pytest.mark.loop_nightly
def test_the_campaign_gg_ttxh_card_is_on_its_bound_shells(tmp_path):
    """The campaign's g g > t t~ h card (QCD corrections): MT = ymt = 173 and
    MH = 125 on with_b_mass_no_width, whose own values are 174.3 and 120."""

    from pyamplicol.cli.flat_points import draw_flat_points

    artifact = _card(
        tmp_path,
        "loop_qcd_qed_sm_Gmu",
        "with_b_mass_no_width",
        "g g > t t~ h",
        {"MT": "173", "ymt": "173", "MH": "125"},
    )
    record = _record(artifact)
    assert record["masses"] == ["0", "0", "173", "173", "125"]
    (point,) = record["points"]
    _assert_on_shell(
        [entry["momentum"] for entry in point], [0.0, 0.0, 173.0, 173.0, 125.0]
    )
    values = json.loads((artifact / "model" / "parameters.json").read_text())
    assert values["parameters"]["MT"] == [173.0, 0.0]
    assert values["parameters"]["MH"] == [125.0, 0.0]
    flat = draw_flat_points(artifact, process=None, points=3, seed=1, sqrt_s=None)
    for momenta in flat.points:
        _assert_on_shell(momenta, flat.masses)
    alpha_s = values["parameters"]["aS"][0]
    expected = -alpha_s / (2 * math.pi) * 2 * CA
    for backend in ("ninjars", "tirust"):
        for ratio in _double_poles(
            artifact, flat.as_inputs(exact=False), flat.mu_r2(), backend
        ):
            assert abs(ratio / expected - 1) <= POLE_TOLERANCE, (backend, ratio)


# ------------------------------------------- the shell-consistency screen


def _point(*legs):
    return [list(map(float, leg)) for leg in legs]


def _screen(points, masses2, *, target=1e-5, roundoff=None, arithmetic="double"):
    from pyamplicol.kinematics import shell_check
    from pyamplicol.loops.v2.assemble import Precision

    precision = {
        "double": Precision.double,
        "double-double": Precision.double_double,
    }[arithmetic]()
    return shell_check(
        points,
        ["1"] * len(points),
        precision,
        lambda *_: masses2,
        target,
        [2.0**-53] * len(points) if roundoff is None else roundoff,
    )


@pytest.mark.loop_fast
def test_the_screen_measures_every_leg_on_its_own_scale():
    """A soft massive leg off its shell at order one beside a hard spectator
    is marked (a per-leg normalisation, not the point's energy sum), so is a
    massless leg off its shell; a point drawn on its shells in binary64 is
    not; a measurement that cannot be made marks the point."""

    from pyamplicol.kinematics import SHELL_REASON, is_shell_reason

    hard = 1.0e6
    # A massive leg at rest with E = 2 m (p^2 = 4 m^2) beside two hard
    # massless legs.
    soft = _point(
        (hard, 0, 0, hard), (hard, 0, 0, -hard), (2.0, 0, 0, 0), (hard, hard, 0, 0)
    )
    masses = [Fraction(0), Fraction(0), Fraction(1), Fraction(0)]
    found = _screen([soft], masses)
    (reason,) = found.reasons.values()
    assert reason.startswith(SHELL_REASON) and is_shell_reason(reason)
    assert "external leg 3" in reason and "bound m^2 = 1.0" in reason
    assert found.defects[0][2] == 3.0
    # A massless leg with p^2 = E^2 / 10.
    light = _point((10.0, 0, 0, 3.0))
    assert set(_screen([light], [Fraction(0)]).reasons) == {0}
    # On its shells (the unchanged validation point of u u~ > t t~ at 173):
    on_shell = [list(map(float, leg)) for leg in _UNCHANGED_POINT]
    masses = [Fraction(0), Fraction(0), Fraction(29929), Fraction(29929)]
    clean = _screen([on_shell], masses)
    assert clean.reasons == {} and max(clean.defects[0]) < 1e-14
    # The same point against tops of 160 GeV, below and above the target.
    stale = [Fraction(0), Fraction(0), Fraction(25600), Fraction(25600)]
    assert set(_screen([on_shell], stale).reasons) == {0}
    assert _screen([on_shell], stale, target=0.5).reasons == {}
    # A tighter target than binary64's rounding: the rounding allowance
    # (8 u (E^2 + |p|^2 + m^2) of the supplied carrier) keeps a binary64
    # point on its shells unmarked.
    assert _screen([on_shell], masses, target=1e-30).reasons == {}
    # Supplied exactly and evaluated in double-double: the binary64 rounding
    # of the point is no longer within the allowance.
    exact = _screen(
        [on_shell], masses, target=1e-30, roundoff=[0.0], arithmetic="double-double"
    )
    assert set(exact.reasons) == {0}
    # Not measurable: a non-finite component, a mass nothing binds.
    broken = [list(leg) for leg in on_shell]
    broken[2][0] = math.nan
    (unmeasured,) = _screen([broken], masses).reasons.values()
    assert "cannot be measured" in unmeasured
    unbound = [Fraction(0), Fraction(0), None, Fraction(29929)]
    assert set(_screen([on_shell], unbound).reasons) == {0}


@pytest.mark.loop_fast
def test_the_supplied_carrier_sets_the_rounding_allowance():
    from decimal import Decimal

    from pyamplicol.kinematics import input_roundoff

    floats = [[[1.5, 0.0, 0.0, 0.1]]]
    texts = [[["1.5", "0", "0", "0.123456789012"]]]
    exact = [[[Fraction(3, 2), 0, 0, 1]]]
    assert input_roundoff(floats) == [2.0**-53]
    assert input_roundoff(texts) == [0.5 * 10.0**-11]
    assert input_roundoff(exact) == [0.0]
    assert input_roundoff([[[Decimal("NaN"), 0, 0, 0]]]) == [math.inf]


def _flat_point(artifact: Path, seed: int = 7):
    from pyamplicol.cli.flat_points import draw_flat_points

    flat = draw_flat_points(artifact, process=None, points=1, seed=seed, sqrt_s=None)
    return [list(leg) for leg in flat.points[0]], flat.mu_r2()[0]


def _stale_point():
    """The point the generation drew before the bound masses: tops at the
    model's 173 GeV while the uux_ttx amplitude binds 160."""

    return [list(map(float, leg)) for leg in _UNCHANGED_POINT], "1000000"


@pytest.mark.loop_physics
@pytest.mark.parametrize("arithmetic", ("double", "double-double"))
def test_an_off_shell_point_is_served_marked_uncertified(uux_ttx, arithmetic):
    from pyamplicol.api import Runtime
    from pyamplicol.kinematics import is_shell_reason

    runtime = Runtime.load(uux_ttx)
    good, scale = _flat_point(uux_ttx)
    stale, stale_scale = _stale_point()
    result = runtime.evaluate(
        [good, stale], mu_r2=[scale, stale_scale], arithmetic=arithmetic
    )
    assert [str(status) for status in result.statuses] == ["success", "success"]
    assert result.values[1] is not None
    clean, marked = result.diagnostics
    assert not clean.uncertified and max(clean.mass_shell) < 1e-14
    (reason,) = [r for r in marked.uncertified if is_shell_reason(r)]
    assert "bound m^2 = 25600.0" in reason and "p^2 = 29929" in reason
    assert not marked.accuracy_established and not marked.failures
    assert "accuracy not established" in marked.detail
    resolved = runtime.evaluate_resolved(
        [good, stale], mu_r2=[scale, stale_scale], arithmetic=arithmetic
    )
    assert [lane.status for lane in resolved.diagnostics] == ["success", "success"]
    assert not resolved.diagnostics[0].uncertified
    assert any(is_shell_reason(r) for r in resolved.diagnostics[1].uncertified)


@pytest.mark.loop_physics
def test_a_point_within_the_target_is_evaluated_as_before(uux_ttx, monkeypatch):
    """A point off its shells by 1e-10 (a momentum component to ten digits)
    is served at binary64 cost, unmarked, its value the evaluation's without
    the screen, bit for bit."""

    from pyamplicol import kinematics
    from pyamplicol.api import Runtime

    runtime = Runtime.load(uux_ttx)
    point, scale = _flat_point(uux_ttx)
    point[2][1] = float(f"{point[2][1]:.10g}")
    screened = runtime.evaluate([point], mu_r2=scale, arithmetic="double")
    lane = screened.diagnostics[0]
    assert str(screened.statuses[0]) == "success" and not lane.uncertified
    assert lane.kinematics is None and 1e-13 < max(lane.mass_shell) < 1e-5
    monkeypatch.setattr(
        kinematics,
        "shell_check",
        lambda points, *_: kinematics.ShellCheck(tuple(() for _ in points), {}),
    )
    plain = runtime.evaluate([point], mu_r2=scale, arithmetic="double")
    assert plain.values == screened.values
    assert plain.born_values == screened.born_values


@pytest.mark.loop_physics
def test_the_unchecked_mode_measures_nothing(uux_ttx, monkeypatch):
    from pyamplicol import kinematics
    from pyamplicol.api import Runtime

    runtime = Runtime.load(uux_ttx, reduction_unchecked=True)
    stale, stale_scale = _stale_point()

    def never(*_args, **_kwargs):
        raise AssertionError("the unchecked mode ran the shell screen")

    monkeypatch.setattr(kinematics, "shell_check", never)
    for call in (runtime.evaluate, runtime.evaluate_resolved):
        result = call([stale], mu_r2=stale_scale)
        (lane,) = result.diagnostics
        assert lane.mass_shell is None and not lane.uncertified


@pytest.mark.loop_physics
def test_a_point_improved_onto_its_shells_is_not_marked(uux_ttx):
    """A top three-momentum scaled by 1 + 3e-6: 5e-5 off its shell (above
    the target) and within MadLoop's input test: marked as given, unmarked
    once the requested improvement moved it onto the shells."""

    from pyamplicol.api import Runtime
    from pyamplicol.kinematics import is_shell_reason

    runtime = Runtime.load(uux_ttx)
    point, scale = _flat_point(uux_ttx)
    point[2] = [point[2][0], *(x * (1 + 3e-6) for x in point[2][1:])]
    given = runtime.evaluate([point], mu_r2=scale, arithmetic="double")
    assert any(is_shell_reason(r) for r in given.diagnostics[0].uncertified)
    improved = runtime.evaluate(
        [point], mu_r2=scale, arithmetic="double", kinematics_improvement_binary64=True
    )
    lane = improved.diagnostics[0]
    assert lane.kinematics.status == "improved"
    assert not any(is_shell_reason(r) for r in lane.uncertified)


@pytest.mark.loop_physics
def test_the_mark_accumulates_and_never_hides_a_failure(uux_ttx, monkeypatch):
    from pyamplicol.api import Runtime
    from pyamplicol.api.virtual_results import VirtualRescuePolicy
    from pyamplicol.kinematics import is_shell_reason
    from pyamplicol.loops.v2 import artifact as stored

    runtime = Runtime.load(uux_ttx)
    stale, stale_scale = _stale_point()
    # Another reason of the same lane (as the reduction records them).
    monkeypatch.setattr(
        stored, "uncertified_reasons", lambda _counts: ("a lane below resolution",)
    )
    (lane,) = runtime.evaluate([stale], mu_r2=stale_scale).diagnostics
    assert lane.uncertified[0] == "a lane below resolution"
    assert is_shell_reason(lane.uncertified[1])
    monkeypatch.undo()
    # The mark alone escalates no rescue level (an on-shell point, marked).
    from pyamplicol import kinematics

    good, scale = _flat_point(uux_ttx)
    screen = kinematics.shell_check

    def marking(points, *args):
        found = screen(points, *args)
        return kinematics.ShellCheck(
            found.defects,
            {i: f"{kinematics.SHELL_REASON}: forced" for i in range(len(points))},
        )

    monkeypatch.setattr(kinematics, "shell_check", marking)
    rescued = runtime.evaluate([good], mu_r2=scale, stability=VirtualRescuePolicy())
    assert rescued.rescue[0].level == 0 and rescued.rescue[0].met
    assert any(is_shell_reason(r) for r in rescued.diagnostics[0].uncertified)
    assert not rescued.diagnostics[0].accuracy_established
    monkeypatch.undo()
    # An independent failure of the evaluation stays a failure.
    backend = runtime._backend
    original = backend._run

    def failing(points, scales, *args):
        original(points, scales, *args)
        return [None] * len(points), {i: ["a refused lane"] for i in range(len(points))}

    monkeypatch.setattr(backend, "_run", failing)
    failed = runtime.evaluate([stale], mu_r2=stale_scale, on_failure="return")
    (lane,) = failed.diagnostics
    assert lane.status == "failed" and failed.values[0] is None
    assert lane.failures[0].stage == "v2-evaluation"
    assert "a refused lane" in lane.detail


@pytest.mark.loop_physics
def test_an_artifact_with_a_stale_validation_point_is_refused(uux_ttx, tmp_path):
    import shutil

    from pyamplicol.api import Runtime
    from pyamplicol.api.errors import ArtifactError
    from pyamplicol.cli.flat_points import draw_flat_points
    from pyamplicol.config import ConfigurationError

    copy = tmp_path / "stale"
    shutil.copytree(uux_ttx, copy)
    path = copy / "processes" / "p" / "validation-momenta.json"
    record = json.loads(path.read_text())
    # As the generation wrote it before the bound masses: the point on the
    # model's shells (173), no recorded masses.
    record["points"] = [
        [
            {"pdg": entry["pdg"], "momentum": momentum}
            for entry, momentum in zip(
                record["points"][0], _UNCHANGED_POINT, strict=True
            )
        ]
    ]
    del record["masses"]
    path.write_text(json.dumps(record))
    with pytest.raises(ArtifactError, match="regenerate the artifact"):
        Runtime.load(copy)
    # The standalone drawer cannot tell the masses of a loop record without
    # them: it refuses too.
    with pytest.raises(ConfigurationError, match="regenerate the artifact"):
        draw_flat_points(copy, process=None, points=1, seed=1, sqrt_s=None)
    # The artifact as generated loads.
    Runtime.load(uux_ttx)
