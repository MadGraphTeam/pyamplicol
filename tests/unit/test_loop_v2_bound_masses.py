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


def _card(
    root: Path,
    model: str,
    restriction: str,
    expression: str,
    fixed: dict,
    extra: str = "",
):
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
{extra}
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
    # The points the profile drew before the bound masses (on the
    # restriction's 174.3 / 120): every one is served marked uncertified.
    from pyamplicol.api import Runtime
    from pyamplicol.cli.flat_points import FlatBinding
    from pyamplicol.kinematics import is_shell_reason

    stale = draw_flat_points(
        artifact,
        process=None,
        points=4,
        seed=1,
        sqrt_s=None,
        binding=FlatBinding("p", (0.0, 0.0, 174.3, 174.3, 120.0)),
    )
    result = Runtime.load(artifact).evaluate(
        stale.as_inputs(exact=False), mu_r2=stale.mu_r2()
    )
    for lane in result.diagnostics:
        assert lane.has_value and any(is_shell_reason(r) for r in lane.uncertified)


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
def test_the_input_contract_sets_the_rounding_allowance_per_leg():
    """u comes from each component's input contract (a Python float is a
    binary64, every exact spelling is exact), per leg, never from a text's
    spelling."""

    from decimal import Decimal

    from pyamplicol.kinematics import input_roundoff

    point = [[1.5, 0, 0, 0.1], ["1.5", "0", "0", "0.1"], [Decimal("2"), 0, 0, 1]]
    assert input_roundoff([point]) == [(2.0**-53, 0.0, 0.0)]
    assert input_roundoff([[["0.123456789012", "1", "2", "3"]]]) == [(0.0,)]


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


# ------------------------------------------- one binding for every draw


@pytest.fixture(scope="module")
def uux_ttz(tmp_path_factory):
    """u u~ > t t~ z (QCD) on loop_sm with MT fixed to 160: two external
    masses on one side."""

    return _card(
        tmp_path_factory.mktemp("bound-masses-ttz"),
        "loop_sm",
        "no_b_mass",
        "u u~ > t t~ z",
        {"MT": "160", "ymt": "160"},
    )


@pytest.mark.loop_physics
def test_a_permuted_selector_loads_draws_and_evaluates_on_its_shells(uux_ttz):
    """The stored u u~ > t t~ z requested as u u~ > z t t~ (a permutation
    within the final state): it loads (the stored point is measured in the
    stored order), its flat points come in the requested order on each
    leg's shell, and their double pole is Catani's, unmarked."""

    from pyamplicol.api import Runtime
    from pyamplicol.cli.flat_points import draw_flat_points, runtime_binding

    selector = "u u~ > z t t~"
    runtime = Runtime.load(uux_ttz, process=selector)
    assert [leg.pdg_id for leg in runtime.physics.external_particles] == [
        2,
        -2,
        23,
        6,
        -6,
    ]
    binding = runtime_binding(runtime)
    flat = draw_flat_points(
        uux_ttz, process=None, points=2, seed=3, sqrt_s=None, binding=binding
    )
    assert flat.masses[2] == pytest.approx(91.188) and flat.masses[3:] == (160.0,) * 2
    for point in flat.points:
        _assert_on_shell(point, flat.masses)
    expected = -ALPHA_S / (2 * math.pi) * 2 * CF
    for ratio in _double_poles(
        uux_ttz, flat.as_inputs(exact=False), flat.mu_r2(), "ninjars", process=selector
    ):
        assert abs(ratio / expected - 1) <= POLE_TOLERANCE, ratio


@pytest.mark.loop_physics
def test_a_stale_permuted_record_is_refused(uux_ttz, tmp_path):
    import shutil

    from pyamplicol.api import Runtime
    from pyamplicol.api.errors import ArtifactError
    from pyamplicol.generation.phase_space import massive_rambo_final_state

    copy = tmp_path / "stale"
    shutil.copytree(uux_ttz, copy)
    path = copy / "processes" / "p" / "validation-momenta.json"
    record = json.loads(path.read_text())
    # The stored order's point drawn on the model's top mass (173).
    finals = massive_rambo_final_state(
        3, sqrt_s=1000.0, masses=(173.0, 173.0, 91.188), seed=1
    )
    legs = [(500.0, 0.0, 0.0, 500.0), (500.0, 0.0, 0.0, -500.0), *finals]
    record["points"] = [
        [
            {"pdg": entry["pdg"], "momentum": [repr(float(x)) for x in leg]}
            for entry, leg in zip(record["points"][0], legs, strict=True)
        ]
    ]
    del record["masses"]
    path.write_text(json.dumps(record))
    for selector in (None, "u u~ > z t t~"):
        with pytest.raises(ArtifactError, match="regenerate the artifact"):
            Runtime.load(copy, process=selector)


@pytest.fixture(scope="module")
def uux_ttx_free(tmp_path_factory):
    """u u~ > t t~ (QCD) on loop_sm with the top mass adjustable (173)."""

    return _card(
        tmp_path_factory.mktemp("bound-masses-free"),
        "loop_sm",
        "no_b_mass",
        "u u~ > t t~",
        {},
    )


@pytest.mark.loop_physics
def test_an_evaluation_time_mass_override_drives_the_flat_points(
    uux_ttx_free, tmp_path, monkeypatch
):
    """MT adjustable at generation (173) and set to 160 at evaluation: the
    CLI's flat points are on the 160 shell, their double pole is Catani's;
    an override of no external mass leaves the points bit for bit."""

    from pyamplicol.cli import flat_points, parse_cli
    from pyamplicol.cli.handlers import DefaultCliServices
    from pyamplicol.reporting import CallbackProgressSink

    drawn = []
    original = flat_points.draw_flat_points

    def spy(*args, **kwargs):
        found = original(*args, **kwargs)
        drawn.append(found)
        return found

    monkeypatch.setattr(flat_points, "draw_flat_points", spy)

    def evaluate(parameters):
        path = tmp_path / "parameters.json"
        path.write_text(json.dumps(parameters))
        config = (
            parse_cli(("evaluate", str(uux_ttx_free), "--model-parameters", str(path)))
            .resolve()
            .effective
        )
        return DefaultCliServices().evaluate(
            config, CallbackProgressSink(lambda _: None)
        )

    result = evaluate({"MT": "160"})
    flat = drawn[-1]
    assert flat.masses == (0.0, 0.0, 160.0, 160.0)
    for point in flat.points:
        _assert_on_shell(point, flat.masses)
    expected = -ALPHA_S / (2 * math.pi) * 2 * CF
    for index in range(len(flat.points)):
        assert str(result.statuses[index]) == "success"
        assert not result.diagnostics[index].uncertified
        born = sum(complex(value).real for value in result.born_values[index])
        pole = sum(complex(v.double_pole).real for v in result.values[index])
        assert abs(pole / born / expected - 1) <= POLE_TOLERANCE
    evaluate({"aS": "0.118"})
    plain = original(
        uux_ttx_free, process=None, points=len(flat.points), seed=1, sqrt_s=None
    )
    assert drawn[-1].points == plain.points and drawn[-1].masses == plain.masses


@pytest.mark.loop_physics
def test_an_override_moves_the_thresholds_and_profile_refuses_overrides(
    uux_ttx_free, tmp_path
):
    from pyamplicol.api import Runtime
    from pyamplicol.cli import parse_cli
    from pyamplicol.cli.flat_points import draw_flat_points, runtime_binding
    from pyamplicol.cli.handlers import DefaultCliServices
    from pyamplicol.config import ConfigurationError
    from pyamplicol.reporting import CallbackProgressSink

    heavy = runtime_binding(Runtime.load(uux_ttx_free, model_parameters={"MT": "600"}))
    assert heavy.masses[2:] == (600.0, 600.0)
    with pytest.raises(ConfigurationError, match="below the threshold"):
        draw_flat_points(
            uux_ttx_free, process=None, points=1, seed=1, sqrt_s=None, binding=heavy
        )
    from dataclasses import replace

    parameters = tmp_path / "parameters.json"
    parameters.write_text('{"MT": "160"}')
    config = parse_cli(("profile", str(uux_ttx_free))).resolve().effective
    config = replace(
        config, evaluation=replace(config.evaluation, model_parameters=parameters)
    )
    with pytest.raises(ConfigurationError, match="own model parameters"):
        DefaultCliServices().benchmark(config, CallbackProgressSink(lambda _: None))


@pytest.mark.loop_fast
def test_a_scale_dependent_external_mass_is_not_drawn_automatically():
    from types import SimpleNamespace

    from pyamplicol.loops.v2.assemble import (
        RunningExternalMass,
        bound_leg_masses,
        effective_fixed_parameters,
        scale_dependent_legs,
    )

    model = SimpleNamespace(
        name="toy",
        parameter_defaults={"MU_R": (91.188, 0.0)},
        ir=SimpleNamespace(
            particles=(SimpleNamespace(pdg_code=24, mass="MW"),),
            parameters=(
                SimpleNamespace(
                    name="MW",
                    nature="internal",
                    resolved_expression="10+model_toy::{}::MU_R/10",
                    parameter_type="real",
                ),
            ),
        ),
    )
    assert scale_dependent_legs(model, [24], "MU_R")
    with pytest.raises(RunningExternalMass, match="give the points' momenta"):
        bound_leg_masses(model, [24], {}, 16, scale_parameter="MU_R")
    # The effective binding: the request's texts first, the preparation's
    # external constants besides, real.
    assert effective_fixed_parameters(
        {"MT": "160"}, {"MT": "1", "CA": ("3", "0"), "X": "1"}, {"MT", "CA"}
    ) == {"MT": "160", "CA": "3"}
    with pytest.raises(ValueError, match="complex"):
        effective_fixed_parameters({}, {"CA": ("3", "1")}, {"CA"})


@pytest.mark.loop_physics
@pytest.mark.parametrize(
    ("model", "restriction", "fixed"),
    (
        (
            "loop_sm",
            "no_b_mass",
            {
                "MZ": "91",
                "aEWM1": "132",
                "Gf": (
                    "0.0000081290192191662013368412952866239325828"
                    "46681333890791203855282746298838"
                ),
            },
        ),
        ("loop_qcd_qed_sm_Gmu", "default", {"MZ": "91"}),
    ),
    ids=("loop_sm", "Gmu"),
)
def test_a_derived_external_mass_is_bound_once(tmp_path, model, restriction, fixed):
    """A W mass derived from fixed inputs: the validation record's mass is
    the runtime's binding (one evaluator, the exact texts), the point is on
    that shell and the artifact loads; its flat points are unmarked."""

    from pyamplicol.api import Runtime
    from pyamplicol.cli.flat_points import draw_flat_points, runtime_binding
    from pyamplicol.kinematics import is_shell_reason

    artifact = _card(tmp_path, model, restriction, "u u~ > w+ w-", fixed)
    record = _record(artifact)
    recorded = float(record["masses"][2])
    runtime = Runtime.load(artifact)
    binding = runtime_binding(runtime)
    assert binding.masses[2] == binding.masses[3] == recorded
    if model == "loop_sm":
        assert recorded == 64.34672030531159
    (point,) = record["points"]
    _assert_on_shell([entry["momentum"] for entry in point], binding.masses)
    flat = draw_flat_points(artifact, process=None, points=2, seed=3, sqrt_s=None)
    result = runtime.evaluate(flat.as_inputs(exact=False), mu_r2=flat.mu_r2())
    for lane in result.diagnostics:
        assert not any(is_shell_reason(r) for r in lane.uncertified)


@pytest.mark.loop_physics
def test_a_complex_mass_scheme_leg_takes_its_real_mass(tmp_path):
    """Under the complex-mass scheme an external state is stable: its shell
    is its real mass parameter squared (the top's complex pole mass is a
    propagator's only). The stable W of u d~ > w+ b b~ (its own width fixed
    to zero by external_widths) is drawn and screened on MW^2."""

    from pyamplicol.api import Runtime
    from pyamplicol.cli.flat_points import draw_flat_points, runtime_binding
    from pyamplicol.kinematics import is_shell_reason

    artifact = _card(
        tmp_path,
        "loop_sm",
        "no_b_mass",
        "u d~ > w+ b b~",
        {"WZ": "0", "WH": "0"},
        extra='[loop.model.scheme]\nmass_scheme = "complex-mass"',
    )
    runtime = Runtime.load(artifact)
    binding = runtime_binding(runtime)
    record = _record(artifact)
    assert float(record["masses"][2]) == binding.masses[2] > 0
    assert binding.masses[3:] == (0.0, 0.0)
    flat = draw_flat_points(artifact, process=None, points=2, seed=3, sqrt_s=None)
    for point in flat.points:
        _assert_on_shell(point, binding.masses)
    result = runtime.evaluate(flat.as_inputs(exact=False), mu_r2=flat.mu_r2())
    for lane in result.diagnostics:
        assert not any(is_shell_reason(r) for r in lane.uncertified)


def _reviewer_point(artifact: Path, spelling):
    """The reviewer's point (review of b9ae740d9): a flat point of uux_ttx
    with the outgoing top energies shifted by +1 / -1 GeV and the incoming
    px set to +0.1 / -0.1, the first incoming px spelled by ``spelling``."""

    point, scale = _flat_point(artifact)
    point[0][1], point[1][1] = spelling(0.1), -0.1
    point[2][0] += 1.0
    point[3][0] -= 1.0
    return point, scale


@pytest.mark.loop_physics
@pytest.mark.parametrize("arithmetic", ("double", "double-double"))
def test_the_mark_does_not_depend_on_the_spelling(uux_ttx, arithmetic):
    """The same values in other spellings (a float, its text, a Decimal, a
    longer exact text, an integer for an integral component): identical
    measured defects and marks; the allowance's u is at most the coarsest
    carrier supplied for each leg (``input_roundoff``)."""

    from decimal import Decimal

    from pyamplicol.api import Runtime
    from pyamplicol.kinematics import input_roundoff, is_shell_reason

    runtime = Runtime.load(uux_ttx)
    spellings = (
        float,
        repr,
        lambda x: Decimal(repr(x)),
        lambda x: repr(x) + "0000000000000000",
    )
    found = []
    for spelling in spellings:
        point, scale = _reviewer_point(uux_ttx, spelling)
        if spelling is not float:
            # Every component in the same spelling, an integral one also
            # as an integer.
            point = [
                [
                    int(x)
                    if float(x).is_integer() and spelling is repr
                    else spelling(float(x))
                    for x in leg
                ]
                for leg in point
            ]
        result = runtime.evaluate([point], mu_r2=scale, arithmetic=arithmetic)
        (lane,) = result.diagnostics
        found.append(
            (
                lane.mass_shell,
                [r.split(", ")[:3] for r in lane.uncertified if is_shell_reason(r)],
            )
        )
        ((leg_units),) = input_roundoff([point])
        for leg, unit in zip(point, leg_units, strict=True):
            assert unit == (2.0**-53 if any(isinstance(x, float) for x in leg) else 0.0)
    assert all(item == found[0] for item in found), found
    defects, marks = found[0]
    assert 0.0390 < defects[2] < 0.0392 and 0.0389 < defects[3] < 0.0391
    assert marks, "the reviewer's point is marked in every spelling"


# ----------------------------------------------- profile stability workers


def _legacy(artifact: Path, root: Path) -> Path:
    """A copy of ``artifact`` whose validation record is as the generation
    wrote it before the bound masses (no ``"masses"``): the record of an
    artifact generated by 1.0.3 whose point is consistent with its
    binding."""

    import shutil

    copy = root / "legacy"
    shutil.copytree(artifact, copy)
    path = copy / "processes" / "p" / "validation-momenta.json"
    record = json.loads(path.read_text())
    del record["masses"]
    path.write_text(json.dumps(record))
    return copy


def _profile_points(
    artifact: Path, out: Path, workers: int, selector=None, completion=None
) -> list:
    """The stability sample of ``pyamplicol profile --stability`` (4 points,
    or with ``completion`` the points of that wall time, on ``workers``
    worker processes: the parent releases its runtime), as its samples file
    records it."""

    from pyamplicol.cli import parse_cli
    from pyamplicol.cli.handlers import DefaultCliServices
    from pyamplicol.reporting import CallbackProgressSink

    arguments = [
        "profile",
        str(artifact),
        "--stability",
        *(("--stability-points", "4") if completion is None else ()),
        *(() if completion is None else ("--completion-time", completion)),
        "--n_core",
        str(workers),
        "--ground-truth",
        "none",
        "--samples-output",
        str(out),
    ]
    if selector is not None:
        arguments += ["--process", selector]
    config = parse_cli(tuple(arguments)).resolve().effective
    DefaultCliServices().benchmark(config, CallbackProgressSink(lambda _: None))
    rows = json.loads(out.read_text())["inputs"]["rows"]
    return [row[1] for row in rows]


@pytest.mark.loop_physics
@pytest.mark.parametrize("massive", (False, True), ids=("gg_gg", "uux_ttx"))
def test_profile_workers_draw_a_legacy_artifact_on_its_binding(
    massive, uux_ttx, tmp_path_factory
):
    """A consistent record without bound masses (an artifact of 1.0.3) is
    profiled with one and with several stability workers: the parent's
    binding is taken before its runtime is released; the samples agree
    between the worker counts and with a draw on the bound masses
    (a massless process: also with the record's own masses, bit for bit)."""

    from pyamplicol.cli.flat_points import draw_flat_points

    root = tmp_path_factory.mktemp("legacy-profile")
    fresh = (
        uux_ttx
        if massive
        else _card(root / "gg", "loop_sm", "no_b_mass", "g g > g g", {})
    )
    legacy = _legacy(fresh, root)
    one = _profile_points(legacy, root / "one.json", 1)
    # Two workers on a time budget: the parent releases its runtime first.
    several = _profile_points(legacy, root / "two.json", 2, completion="20")
    assert len(several) >= len(one) and several[: len(one)] == one
    expected = draw_flat_points(
        fresh, process=None, points=len(several), seed=1, sqrt_s=None
    )
    assert [[[float(x) for x in leg] for leg in point] for point in several] == [
        [list(leg) for leg in point] for point in expected.points
    ]
    for point in several:
        _assert_on_shell(point, expected.masses)


@pytest.mark.loop_physics
def test_profile_workers_keep_a_permuted_selector(uux_ttz, tmp_path):
    """u u~ > z t t~ of the stored u u~ > t t~ z, two stability workers:
    every sampled point is on the requested order's shells."""

    points = _profile_points(
        uux_ttz, tmp_path / "ttz.json", 2, "u u~ > z t t~", completion="20"
    )
    assert points
    for point in points:
        _assert_on_shell(point, (0.0, 0.0, 91.188, 160.0, 160.0))


@pytest.mark.loop_physics
def test_the_public_benchmark_runner_refuses_ignored_parameters(uux_ttx_free, tmp_path):
    """BenchmarkRunner.run (the public entry point the CLI's profile uses)
    refuses evaluation.model_parameters, which it would not apply."""

    from dataclasses import replace

    from pyamplicol.api.services import BenchmarkRunner
    from pyamplicol.cli import parse_cli
    from pyamplicol.config import ConfigurationError

    parameters = tmp_path / "parameters.json"
    parameters.write_text('{"MT": "160"}')
    config = parse_cli(("profile", str(uux_ttx_free))).resolve().effective
    config = replace(
        config, evaluation=replace(config.evaluation, model_parameters=parameters)
    )
    with pytest.raises(ConfigurationError, match="own model parameters"):
        BenchmarkRunner(config=config).run(uux_ttx_free)


@pytest.mark.loop_physics
@pytest.mark.parametrize("higgs", (None, "130"))
def test_a_two_to_one_draw_takes_the_bound_final_mass(higgs, tmp_path, monkeypatch):
    """The shipped g g > h example through `pyamplicol evaluate`: the Higgs
    at rest at the bound mass (125, or an override 130) and mu_R^2 = MH^2,
    never the stored point's energy; the point is unmarked."""

    from pyamplicol._internal import selftest_virtual_li as li
    from pyamplicol.cli import flat_points, parse_cli
    from pyamplicol.cli.handlers import DefaultCliServices
    from pyamplicol.reporting import CallbackProgressSink

    drawn = []
    original = flat_points.draw_flat_points

    def spy(*args, **kwargs):
        found = original(*args, **kwargs)
        drawn.append(found)
        return found

    monkeypatch.setattr(flat_points, "draw_flat_points", spy)
    arguments = ["evaluate", str(li.fixture_root() / "artifact")]
    if higgs is not None:
        path = tmp_path / "parameters.json"
        path.write_text(json.dumps({"MH": higgs}))
        arguments += ["--model-parameters", str(path)]
    config = parse_cli(tuple(arguments)).resolve().effective
    result = DefaultCliServices().evaluate(config, CallbackProgressSink(lambda _: None))
    mass = 125.0 if higgs is None else 130.0
    (flat,) = drawn
    for point in flat.points:
        assert point[-1] == (mass, 0.0, 0.0, 0.0)
        assert point[0][0] + point[1][0] == mass
    assert flat.mu_r2() == [repr(mass * mass)] * len(flat.points)
    for lane in result.diagnostics:
        assert not lane.uncertified, lane.uncertified
