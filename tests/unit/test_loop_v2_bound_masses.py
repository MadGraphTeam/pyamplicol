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


def _double_poles(artifact: Path, points: list, scales: list, backend: str):
    """dp / Born per point on ``backend`` in binary64."""

    from pyamplicol.api import Runtime

    runtime = Runtime.load(artifact)
    result = runtime.evaluate(
        points, mu_r2=scales, reduction=backend, arithmetic="double"
    )
    out = []
    for index in range(len(points)):
        assert str(result.statuses[index]) == "success", result.statuses[index]
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


# ------------------------------------------------------------- the shell guard


@pytest.mark.loop_fast
def test_the_shell_measure_is_exact_and_its_bound_the_binary64_rounding():
    from pyamplicol.kinematics import shell_bound, shell_defects, shell_refusals

    point = [list(map(float, leg)) for leg in _UNCHANGED_POINT]
    masses = [Fraction(0), Fraction(0), Fraction(29929), Fraction(29929)]
    (fast,) = shell_defects([point], [masses], binary64=True)
    binary = [[Fraction(x) for x in leg] for leg in point]
    (exact,) = shell_defects([binary], [masses], binary64=False)
    # The binary64 path measures the binary64 values exactly (double-double).
    assert fast == pytest.approx(exact, rel=1e-12, abs=1e-30)
    assert max(exact) <= shell_bound(4) == 13 * 2.0**-53
    other = [Fraction(0), Fraction(0), Fraction(25600), Fraction(25600)]
    (defects,) = shell_defects([point], [other], binary64=True)
    refused = shell_refusals([point], [other], [defects])
    assert set(refused) == {0}
    (reason,) = refused[0]
    assert reason.startswith("external-mass-shell: external leg ")
    assert "bound m^2 = 25600.0" in reason
    # A leg without a bound mass takes its own p^2; a non-finite component is
    # left to the evaluation.
    unknown = [None, None, None, None]
    assert shell_defects([point], [unknown], binary64=True) == [(0.0,) * 4]
    broken = [list(leg) for leg in point]
    broken[2][0] = math.nan
    for binary64 in (True, False):
        (nan,) = shell_defects([broken], [masses], binary64=binary64)
        assert all(math.isnan(value) for value in nan)
        assert shell_refusals([broken], [masses], [nan]) == {}


def _flat_point(artifact: Path, seed: int = 7):
    from pyamplicol.cli.flat_points import draw_flat_points

    flat = draw_flat_points(artifact, process=None, points=1, seed=seed, sqrt_s=None)
    return [list(leg) for leg in flat.points[0]], flat.mu_r2()[0]


@pytest.mark.loop_physics
def test_an_off_shell_point_is_refused(uux_ttx):
    from pyamplicol.api import Runtime
    from pyamplicol.api.errors import EvaluationError
    from pyamplicol.kinematics import SHELL_STAGE, shell_bound

    runtime = Runtime.load(uux_ttx)
    good, scale = _flat_point(uux_ttx)
    # The point the generation drew before the bound masses: tops at the
    # model's 173, the amplitude binds 160.
    stale = [list(map(float, leg)) for leg in _UNCHANGED_POINT]
    for arithmetic in ("double", "double-double"):
        result = runtime.evaluate(
            [good, stale], mu_r2=[scale, "1000000"], arithmetic=arithmetic
        )
        assert [str(status) for status in result.statuses] == ["success", "failed"]
        assert result.values[1] is None
        lane = result.diagnostics[1]
        (failure,) = lane.failures
        assert failure.stage == SHELL_STAGE and failure.external_leg in (2, 3)
        assert "bound m^2 = 25600.0" in lane.detail
        assert max(lane.mass_shell) > shell_bound(4)
        assert max(result.diagnostics[0].mass_shell) <= shell_bound(4)
    with pytest.raises(EvaluationError, match=SHELL_STAGE):
        runtime.evaluate([stale], mu_r2="1000000", on_failure="raise")
    # The resolved outputs take the same guard.
    resolved = runtime.evaluate_resolved([good, stale], mu_r2=[scale, "1000000"])
    assert resolved.diagnostics[0].status == "success"
    assert resolved.diagnostics[1].failures[0].stage == SHELL_STAGE


@pytest.mark.loop_physics
def test_a_point_off_shell_by_its_inputs_digits_is_refused_unless_improved(uux_ttx):
    from pyamplicol.api import Runtime
    from pyamplicol.kinematics import SHELL_STAGE

    runtime = Runtime.load(uux_ttx)
    point, scale = _flat_point(uux_ttx)
    # A top momentum component to ten digits: off its shell by about 1e-10
    # of E^2, far beyond binary64's rounding, well within the improvement's
    # input test.
    point[2][1] = float(f"{point[2][1]:.10g}")
    plain = runtime.evaluate([point], mu_r2=scale, arithmetic="double")
    assert plain.diagnostics[0].failures[0].stage == SHELL_STAGE
    improved = runtime.evaluate(
        [point], mu_r2=scale, arithmetic="double", kinematics_improvement_binary64=True
    )
    assert str(improved.statuses[0]) == "success"
    assert improved.diagnostics[0].kinematics.status == "improved"
    extended = runtime.evaluate([point], mu_r2=scale, arithmetic="double-double")
    assert str(extended.statuses[0]) == "success"


@pytest.mark.loop_physics
def test_an_artifact_with_a_stale_validation_point_is_refused(uux_ttx, tmp_path):
    import shutil

    from pyamplicol.api import Runtime
    from pyamplicol.api.errors import ArtifactError

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
    # The artifact as generated loads.
    Runtime.load(uux_ttx)
