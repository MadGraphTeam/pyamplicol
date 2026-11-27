# SPDX-License-Identifier: 0BSD
"""The minimal coupling-order policy works within the UFO expansion orders.

A user SM UFO tags the down-quark and neutrino Z couplings ``NP:1`` and
declares ``NP`` with ``expansion_order = 1``, so ``d d~ > vm vm~`` needs
``NP^2``: at the default (minimal) policy it has no Born, in the tree, the
correlated and the loop-Born paths alike (tree generation refuses it with the
typed ``NoTreeDiagramError``); a named limit still decides.

A copy of ``loop_sm`` with ``QED`` of expansion order 1 does the same for a
loop-induced request: the default ``g g > a a`` (``QED^2``) has no loop
amplitude, an explicit ``QED <= 2`` has one, and the plan records the loop
orders the artifact is generated with.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest

from pyamplicol import (
    ColorCorrelator,
    CorrelatorConfig,
    Generator,
    ModelSource,
    NoTreeDiagramError,
    Runtime,
)
from pyamplicol.config import (
    ColorConfig,
    EvaluatorConfig,
    EvaluatorOptimizationConfig,
    GenerationConfig,
    GenerationRelationDiscoveryConfig,
    GenerationValidationConfig,
    ModelConfig,
    ProcessConfig,
    RunConfig,
)
from pyamplicol.generation import loop_service

_SM_UFO = Path(__file__).resolve().parents[2] / "src/pyamplicol/assets/models/ufo/sm"
_POINTS = [[(100, 0, 0, 100), (100, 0, 0, -100), (100, 60, 80, 0), (100, -60, -80, 0)]]


@pytest.fixture(scope="module")
def np_model(tmp_path_factory: pytest.TempPathFactory) -> ModelSource:
    if importlib.util.find_spec("pyamplicol._rusticol") is None:
        pytest.skip("the Rusticol extension has not been built")
    source = tmp_path_factory.mktemp("np-ufo") / "NP"
    shutil.copytree(
        _SM_UFO, source, ignore=shutil.ignore_patterns("*.pkl", "__pycache__")
    )
    with (source / "coupling_orders.py").open("a", encoding="utf-8") as handle:
        handle.write(
            "\nNP = CouplingOrder(name='NP', expansion_order=1, hierarchy=1)\n"
        )
    couplings = source / "couplings.py"
    text, count = re.subn(
        r"(GC_(?:50|58|62) = Coupling\([^)]*?(?:.|\n)*?order = )\{'QED':1\}",
        r"\1{'QED':1,'NP':1}",
        couplings.read_text(encoding="utf-8"),
    )
    assert count == 3
    couplings.write_text(text, encoding="utf-8")
    return ModelSource.from_path(source, restriction="default")


def _config(orders: dict[str, int] | None) -> RunConfig:
    return RunConfig(
        action="generate",
        model=ModelConfig(cache=False),
        color=ColorConfig(accuracy="full"),
        process=(
            ProcessConfig()
            if orders is None
            else ProcessConfig(
                coupling_order_policy="explicit", max_coupling_orders=orders
            )
        ),
        generation=GenerationConfig(
            workers=1,
            emit_api_bundle=False,
            relation_discovery=GenerationRelationDiscoveryConfig(mode="off"),
            validation=GenerationValidationConfig(
                enabled=False, post_build_validation=False
            ),
        ),
        evaluator=EvaluatorConfig(
            execution_mode="compiled",
            optimization=EvaluatorOptimizationConfig(cores=1),
        ),
    )


_DIPOLE = CorrelatorConfig(color_correlations=(ColorCorrelator.dipole("T12", 1, 2),))


@pytest.mark.parametrize("correlated", (False, True))
def test_the_default_policy_stays_within_the_expansion_order(
    np_model: ModelSource, tmp_path: Path, correlated: bool
) -> None:
    extra = {"correlators": _DIPOLE} if correlated else {}
    with pytest.raises(NoTreeDiagramError) as caught:
        Generator(_config(None)).generate(
            "d d~ > vm vm~", tmp_path / "default", model=np_model, **extra
        )
    message = str(caught.value)
    assert "within the model's expansion orders (NP<=1)" in message
    assert "a diagram exists above the expansion order of NP" in message
    assert "loop-induced" not in message


@pytest.mark.parametrize("correlated", (False, True))
def test_a_named_limit_decides(
    np_model: ModelSource, tmp_path: Path, correlated: bool
) -> None:
    extra = {"correlators": _DIPOLE} if correlated else {}
    with pytest.raises(NoTreeDiagramError, match=r"coupling orders \(NP<=1\)"):
        Generator(_config({"NP": 1})).generate(
            "d d~ > vm vm~", tmp_path / "np1", model=np_model, **extra
        )
    Generator(_config({"NP": 2})).generate(
        "d d~ > vm vm~", tmp_path / "np2", model=np_model, **extra
    )
    value = complex(Runtime.load(tmp_path / "np2").evaluate(_POINTS)[0])
    assert value.real > 0.0


def test_the_loop_limits_keep_the_cap_when_nothing_is_inferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The loop service's limits: an empty minimal inference (no Born within
    the expansion orders) keeps the capped limits, not the uncapped explicit
    ones; the loop-induced bounds are the capped limits; an explicit limit
    stays as requested."""

    class _Model:
        def coupling_order_expansion_orders(self) -> dict[str, int]:
            return {"NP": 1}

    class _Names:
        def mapping(self, values):
            return dict(sorted(values.items()))

        def declared_name(self, name):
            return name

    monkeypatch.setattr(
        loop_service,
        "infer_minimal_coupling_order_limits",
        lambda process, *, model, max_coupling_orders: {},
    )
    limits = loop_service._request_limits
    for born in (True, False):
        assert limits(object(), _Model(), {}, _Names(), "minimal", born=born) == {
            "NP": 1
        }
        assert limits(
            object(), _Model(), {"NP": 2}, _Names(), "minimal", born=born
        ) == {"NP": 2}
        assert limits(object(), _Model(), {}, _Names(), "explicit", born=born) == {}


_LOOP_SCHEME = """
[loop]
r2_strategy = "model"
[loop.model]
loop_coupling_orders = ["QCD"]
uv_complete = true
model_r2_complete = true
[loop.model.scheme]
dimensional_regularization = "HV"
external_states = "physical-four-dimensional"
gamma5 = "source-UFO-four-dimensional-prescription"
renormalization = "source-UFO mass-dependent decoupling"
mass_scheme = "real-on-shell"
finite_restoration = "source-UFO-local-rules"
model_convention = "loop_sm lhv=1 supplied QCD rules"
[loop.preparation]
fixed_parameters = {WT = "0", WZ = "0", WW = "0", WH = "0"}
"""


def _loop_generator(model: Path, output: Path, limits: str):
    from pyamplicol.config import resolve_config

    output.mkdir(parents=True, exist_ok=True)
    card = output / "card.toml"
    card.write_text(
        f"""
action = "generate"
[model]
source = {json.dumps(str(model))}
restriction = "no_b_mass"
[process]
entries = [{{expression = "g g > a a", name = "gg_aa"}}]
loop_coupling_orders = ["QCD"]
{limits}
{_LOOP_SCHEME}
[generation]
output = {json.dumps(str(output / "artifact"))}
emit_api_bundle = false
[generation.validation]
post_build_validation = false
""",
        encoding="utf-8",
    )
    return Generator(resolve_config(card))


@pytest.mark.loop_physics
def test_a_loop_induced_request_stays_within_the_expansion_order(
    loop_native, tmp_path: Path
) -> None:
    from pyamplicol import ProcessRequest, ProcessSet
    from pyamplicol.loops.v2.refusals import LoopRequestUnsupported
    from pyamplicol.models.loading import compile_model_source

    model = tmp_path / "loop_sm_qed1"
    shutil.copytree(
        _SM_UFO.parent / "loop_sm",
        model,
        ignore=shutil.ignore_patterns("*.pkl", "__pycache__"),
    )
    orders = model / "coupling_orders.py"
    text, count = re.subn(
        r"(name = 'QED',\s*hierarchy = 2,\s*expansion_order = )-1",
        r"\g<1>1",
        orders.read_text(encoding="utf-8"),
    )
    assert count == 1
    orders.write_text(text, encoding="utf-8")
    # A dry run compiles no model source: compile the copy into the model
    # cache first, as generation would.
    compile_model_source(str(model), restriction="no_b_mass")
    processes = ProcessSet((ProcessRequest.parse("g g > a a", name="gg_aa"),))

    default = _loop_generator(model, tmp_path / "default", "")
    plan = default.plan(processes)
    assert [f.split(":")[0] for f in plan.unsupported_features] == ["no-loop-amplitude"]
    with pytest.raises(LoopRequestUnsupported, match="no-loop-amplitude"):
        default.generate(processes, tmp_path / "default" / "artifact")

    explicit = _loop_generator(
        model, tmp_path / "qed2", "max_coupling_orders = {QED = 2}"
    )
    plan = explicit.plan(processes)
    assert plan.unsupported_features == ()
    ((record),) = plan.estimated_coverage["processes"]
    assert record["contribution"] == "loop-induced"
    assert dict(record["coupling_order_limits"]) == {"QED": 2}
    assert dict(record["loop_orders"]) == {"QCD": 2, "QED": 2}
    artifact = tmp_path / "qed2" / "artifact"
    explicit.generate(processes, artifact)
    manifest = json.loads((artifact / "artifact.json").read_text(encoding="utf-8"))
    ((generated),) = manifest["extensions"]["generation"]["concrete_processes"]
    assert generated["filters"]["loop_orders"] == dict(record["loop_orders"])
    execution = json.loads(
        (artifact / "processes" / "gg_aa" / "execution.json").read_text(
            encoding="utf-8"
        )
    )
    assert execution["request"]["loop_orders"] == dict(record["loop_orders"])
    momenta = [
        [(500, 0, 0, 500), (500, 0, 0, -500), (500, 0, 300, 400), (500, 0, -300, -400)]
    ]
    value = Runtime.load(artifact, process="gg_aa").evaluate(momenta, mu_r2=[8315.0])
    assert value.values[0][0].finite > 0.0
