# SPDX-License-Identifier: 0BSD
"""Leading and next-to-leading colour of corrections other than the model's
strong one (QED and QCD+QED) are refused with their true reason (listed key
``lc-electroweak-corrections``): not implemented yet, because the
electroweak counterterms of the QCD+QED models (sums of an N_c-free part
and a closed-quark-loop part proportional to N_c) have no formal-N_c
declaration. Full colour serves them; the refusal offers no other remedy
(a user colour declaration does not make these requests work).

The rule (``ew_policy.require_projectable_corrections``) classifies the
corrections by the model's structure (``ew_policy.correction_orders``: the
order of the gluon's minimal vertices), never by an order's name, and every
entry point applies it: the service's early check and the shared request
preparation (``assemble.resolve_request``) of direct slices and artifacts.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

KEY = "lc-electroweak-corrections"
ROOT = Path(__file__).resolve().parents[2]
UFO = ROOT / "src/pyamplicol/assets/models/ufo"
ZERO_WIDTHS = {"WT": "0", "WZ": "0", "WW": "0", "WH": "0"}
POINTS = (
    ((500, 0, 0, 500), (500, 0, 0, -500), (500, 300, 0, 400), (500, -300, 0, -400)),
    ((500, 0, 0, 500), (500, 0, 0, -500), (500, 0, 400, 300), (500, 0, -400, -300)),
)


def _assert_refusal_text(text: str, accuracy: str = "LC") -> None:
    assert text.startswith(f"{KEY}: {accuracy} one-loop generation "), text
    assert "is not implemented yet" in text
    assert "no formal-N_c colour declaration" in text
    assert 'Instead: full colour (color.accuracy = "full"' in text
    # No remedy that does not work: no user declaration is offered.
    assert "with_loop_color_declaration" not in text
    assert "LoopColorDeclaration" not in text


# --------------------------------------------------------------- the rule


@pytest.mark.loop_fast
@pytest.mark.parametrize(
    "corrections,declared,colour_declared,refused",
    [
        # The model's strong order is "QS", its abelian one "QCD" (names
        # mean nothing): the abelian correction is refused, whatever colour
        # data the model carries.
        (("QCD",), (), True, True),
        (("QS", "QCD"), (), True, True),
        (("QS",), ("QS", "QCD"), True, False),
        # Strong corrections alone on a model declaring others: refused only
        # without a colour declaration (none ships for the QCD+QED models).
        (("QS",), ("QS", "QCD"), False, True),
        (("QS",), ("QS",), False, False),
    ],
)
def test_the_rule_reads_the_models_strong_order_not_its_name(
    monkeypatch, corrections, declared, colour_declared, refused
):
    from pyamplicol.api.errors import GenerationError
    from pyamplicol.loops.v2 import ew_policy
    from pyamplicol.loops.v2.refusals import LoopRequestUnsupported

    monkeypatch.setattr(
        ew_policy,
        "correction_orders",
        lambda _compiled, _fixed: ew_policy.CorrectionOrders("QS", "QCD"),
    )

    def call(accuracy: str = "lc") -> None:
        ew_policy.require_projectable_corrections(
            object(),
            accuracy,
            corrections,
            {},
            declared=declared,
            colour_declared=colour_declared,
        )

    call("full")  # full colour serves everything
    if not refused:
        call()
        call("nlc")
        return
    for accuracy in ("lc", "nlc"):
        with pytest.raises(GenerationError) as error:
            call(accuracy)
        assert isinstance(error.value, LoopRequestUnsupported)
        assert error.value.key == KEY
        _assert_refusal_text(str(error.value), accuracy.upper())


@pytest.mark.loop_fast
def test_a_model_without_a_strong_order_is_refused_at_lc(monkeypatch):
    from pyamplicol.loops.v2 import ew_policy
    from pyamplicol.loops.v2.refusals import LoopRequestUnsupported

    monkeypatch.setattr(
        ew_policy,
        "correction_orders",
        lambda _compiled, _fixed: ew_policy.CorrectionOrders(None, "QED"),
    )
    with pytest.raises(LoopRequestUnsupported) as error:
        ew_policy.require_projectable_corrections(object(), "lc", ("QED",), {})
    assert error.value.key == KEY


# ------------------------------------------------------- the shipped models


def _card(output, expression: str, orders, accuracy: str, model: str) -> str:
    return f"""
action = "generate"
[model]
source = {json.dumps(model)}
[process]
entries = [{{expression = {json.dumps(expression)}, name = "p"}}]
loop_coupling_orders = {json.dumps(list(orders))}
coupling_order_policy = "minimal"
[color]
accuracy = "{accuracy}"
[loop]
r2_strategy = "model"
[loop.preparation]
fixed_parameters = {{WT = "0", WZ = "0", WW = "0", WH = "0"}}
[generation]
output = {json.dumps(str(output))}
emit_api_bundle = false
[generation.validation]
post_build_validation = false
"""


def _generator(tmp_path, expression, orders, accuracy, model="loop_qcd_qed_sm"):
    from pyamplicol.api import Generator
    from pyamplicol.config import resolve_config

    card = tmp_path / "card.toml"
    card.write_text(_card(tmp_path / "out", expression, orders, accuracy, model))
    return Generator(resolve_config(card))


def _processes(expression: str):
    from pyamplicol.api import ProcessRequest, ProcessSet

    return ProcessSet((ProcessRequest.parse(expression, name="p"),))


def _assert_refused(generator, processes, output, accuracy="LC", model=None):
    from pyamplicol.api.errors import GenerationError
    from pyamplicol.loops.v2.refusals import LoopRequestUnsupported

    plan = generator.plan(processes, model=model)
    (blocker,) = plan.unsupported_features
    _assert_refusal_text(blocker, accuracy)
    with pytest.raises(GenerationError) as refused:
        generator.generate(processes, output, model=model)
    assert isinstance(refused.value, LoopRequestUnsupported)
    assert refused.value.key == KEY
    assert str(refused.value) == str(blocker)
    assert not output.exists()
    return blocker


@pytest.mark.loop_physics
@pytest.mark.parametrize(
    "orders,accuracy,phrase",
    [
        (("QCD", "QED"), "lc", "corrections other than the model's strong one (QED)"),
        (("QED",), "nlc", "corrections other than the model's strong one (QED)"),
        (
            ("QCD",),
            "lc",
            "declaring corrections other than its strong one (QED) without a "
            "colour declaration, also for its strong corrections alone",
        ),
    ],
)
def test_the_service_refusal_says_why_in_the_dry_run_and_at_generation(
    tmp_path, orders, accuracy, phrase
):
    from pyamplicol.models.loading import compile_model_source

    # The dry run compiles no model: populate the model cache first.
    compile_model_source("loop_qcd_qed_sm", restriction="default")
    generator = _generator(tmp_path, "u u~ > d d~", orders, accuracy)
    blocker = _assert_refused(
        generator, _processes("u u~ > d d~"), tmp_path / "out", accuracy.upper()
    )
    assert phrase in blocker


@pytest.mark.loop_physics
def test_the_cli_refuses_with_the_key_and_writes_nothing(tmp_path):
    """The CLI route (the same service rule): exit 2, the listed text on
    stderr, no output."""

    import io

    from pyamplicol.cli import run_cli
    from pyamplicol.models.loading import compile_model_source

    compile_model_source("loop_qcd_qed_sm", restriction="default")
    card = tmp_path / "card.toml"
    card.write_text(
        _card(tmp_path / "out", "u u~ > d d~", ("QCD", "QED"), "lc", "loop_qcd_qed_sm")
    )
    stderr = io.StringIO()
    code = run_cli(
        ("generate", "--card", str(card), "--progress", "off"),
        stdout=io.StringIO(),
        stderr=stderr,
    )
    assert code == 2, stderr.getvalue()
    assert f"{KEY}: LC one-loop generation with corrections other than" in (
        stderr.getvalue()
    )
    assert "LoopColorDeclaration" not in stderr.getvalue()
    assert not (tmp_path / "out").exists()


def _identity_colour_declaration(raw, scheme):
    """A source-colour declaration of every counterterm vertex but the
    four-gluon R2 and of every field factor, by the source's own colour
    symbols (what a user could attach)."""

    from pyamplicol.models import loop_color_declarations as data
    from pyamplicol.models.loop_color_declaration import LoopColorDeclaration

    keys = []
    for vertex in raw.collections["counterterm_vertices"]:
        names = [str(p.get("name")) for p in vertex["fields"]["particles"]]
        if len(names) == 4 and all(name == "G" for name in names):
            continue
        for key, _reference in data._entries(vertex["fields"]["couplings"]):
            colour, lorentz, group = data._key_items(key)
            keys.append(
                ("counterterm_vertices", int(vertex["id"]), colour, lorentz, group)
            )
    return LoopColorDeclaration(
        scheme=scheme,
        formal_symbol="Nc",
        parameter_identities={
            "CA": "Nc",
            "CF": "(Nc**2-1)/(2*Nc)",
            "TF": "1/2",
            "Ncol": "Nc",
        },
        kernel_keys=tuple(keys),
        field_keys=tuple(sorted(f.key for f in data.field_factors(raw))),
        scheme_parameter_values={"lhv": "1"},
        whole_rules=(),
    )


@pytest.mark.loop_physics
@pytest.mark.parametrize(
    "process,born,loop",
    [
        ("u u~ > e+ e-", {"QCD": 0, "QED": 2}, {"QCD": 0, "QED": 4}),
        ("u u~ > d d~", {"QCD": 2, "QED": 0}, {"QCD": 2, "QED": 2}),
    ],
)
@pytest.mark.parametrize("accuracy", ["lc", "nlc"])
def test_direct_slices_refuse_alike_with_a_user_colour_declaration(
    loop_native, tmp_path, process, born, loop, accuracy
):
    """``LoopSlice.generate`` on loop_qcd_qed_sm with explicit source colour
    data and QED corrections: the typed refusal, never a served LC value
    or a raw ``NotImplementedError``."""

    from pyamplicol.loops.v2.assemble import LoopSlice, SliceRequest
    from pyamplicol.loops.v2.refusals import LoopRequestUnsupported
    from pyamplicol.models.loading import compile_model_source
    from pyamplicol.models.loop_color_declaration import with_loop_color_declaration
    from pyamplicol.models.loop_declaration import (
        resolve_loop_model_declaration,
        with_loop_model_declaration,
    )

    model = compile_model_source(
        "loop_qcd_qed_sm", restriction="no_widths", cache_dir=tmp_path / "cache"
    )
    declaration = resolve_loop_model_declaration(
        model.raw_loop_model, None, selected_corrections=("QED",)
    )
    model = with_loop_model_declaration(model, declaration)
    colour = _identity_colour_declaration(model.raw_loop_model, declaration.scheme)
    model = with_loop_color_declaration(model, colour)
    request = SliceRequest(
        process,
        born,
        loop,
        corrections=("QED",),
        accuracy=accuracy,
        colour_declaration=colour,
        compatibility="gmu_particle_anti",
        scale_parameter="MU_R",
    )
    with pytest.raises(LoopRequestUnsupported) as refused:
        LoopSlice.generate(model, request, loop_native)
    assert refused.value.key == KEY
    _assert_refusal_text(str(refused.value), accuracy.upper())


# --------------------------------------------------------- renamed orders


def _evaluate(output):
    from pyamplicol.api import Runtime

    runtime = Runtime.load(output, process="p")
    result = runtime.evaluate([list(map(list, p)) for p in POINTS], mu_r2=[8315.0] * 2)
    return result.born_values, result.values


@pytest.mark.loop_physics
@pytest.mark.parametrize("accuracy", ["lc", "nlc"])
def test_a_renamed_strong_order_is_served_as_the_original(tmp_path, accuracy):
    """loop_sm with its strong order spelt ``QS`` (and QED ``Qe``), with
    loop_sm's own declarations attached, generates u u~ > g g at LC and NLC
    with the original's values, bit for bit."""

    import sys

    from pyamplicol.api.models import _compiled_model_from_payload
    from pyamplicol.models.loading import compile_model_source
    from pyamplicol.models.loop_color_declaration import (
        resolve_loop_color_declaration,
        with_loop_color_declaration,
    )
    from pyamplicol.models.loop_declaration import (
        resolve_loop_model_declaration,
        with_loop_model_declaration,
    )

    sys.path.insert(0, str(ROOT / "tests/unit"))
    from loop_renamed_models import write_variant

    rename = write_variant(UFO / "loop_sm", tmp_path / "loop_qs", "orders")
    assert rename.order("QCD") == "QS"
    cache = tmp_path / "cache"
    original = compile_model_source("loop_sm", restriction="default", cache_dir=cache)
    colour = resolve_loop_color_declaration(original.raw_loop_model)
    declaration = resolve_loop_model_declaration(
        original.raw_loop_model, None, selected_corrections=("QCD",)
    )
    variant = compile_model_source(
        tmp_path / "loop_qs",
        restriction="default",
        cache_dir=cache,
        require_supported=False,
    )
    variant = with_loop_model_declaration(
        variant, replace(declaration, loop_coupling_orders=("QS",))
    )
    # The same declaration in the variant's order names (field keys and
    # whole-rule orders name the correction).
    renamed = replace(
        colour,
        field_keys=tuple(
            (index, rename.order(order), group)
            for index, order, group in colour.field_keys
        ),
        whole_rules=tuple(
            replace(
                rule,
                order=tuple((rename.order(name), power) for name, power in rule.order),
            )
            for rule in colour.whole_rules
        ),
    )
    variant = with_loop_color_declaration(variant, renamed)
    values = {}
    for name, model, order in (
        ("original", original, "QCD"),
        ("variant", variant, "QS"),
    ):
        directory = tmp_path / name
        directory.mkdir()
        generator = _generator(directory, "u u~ > g g", (order,), accuracy, "loop_sm")
        handle = _compiled_model_from_payload(model)
        plan = generator.plan(_processes("u u~ > g g"), model=handle)
        assert plan.unsupported_features == (), plan.unsupported_features
        generator.generate(_processes("u u~ > g g"), directory / "out", model=handle)
        values[name] = _evaluate(directory / "out")
    assert values["variant"] == values["original"]


@pytest.mark.loop_physics
def test_an_electromagnetic_order_spelt_qcd_is_refused(tmp_path):
    """loop_qcd_qed_sm with QCD spelt ``QS`` and QED spelt ``QCD``: its
    electromagnetic correction, named ``QCD``, is refused at LC although a
    colour declaration is attached."""

    from pyamplicol.api.models import _compiled_model_from_payload
    from pyamplicol.loops.v2 import ew_policy
    from pyamplicol.models.loading import compile_model_source
    from pyamplicol.models.loop_color_declaration import (
        LoopColorDeclaration,
        with_loop_color_declaration,
    )
    from pyamplicol.models.loop_declaration import (
        resolve_loop_model_declaration,
        with_loop_model_declaration,
    )

    source = tmp_path / "swapped"
    shutil.copytree(UFO / "loop_qcd_qed_sm", source)
    names = {"QCD": "QS", "QED": "QCD"}
    for path in source.glob("*.py"):
        text = path.read_text(encoding="latin-1")
        path.write_text(
            re.sub(r"\b(QCD|QED)\b", lambda m: names[m.group(0)], text),
            encoding="latin-1",
        )
    cache = tmp_path / "cache"
    original = compile_model_source("loop_qcd_qed_sm", cache_dir=cache)
    declaration = resolve_loop_model_declaration(
        original.raw_loop_model, None, selected_corrections=("QCD",)
    )
    model = compile_model_source(source, cache_dir=cache, require_supported=False)
    orders = ew_policy.correction_orders(model, ZERO_WIDTHS)
    assert (orders.strong, orders.abelian) == ("QS", "QCD")
    model = with_loop_model_declaration(
        model, replace(declaration, loop_coupling_orders=("QS", "QCD"))
    )
    model = with_loop_color_declaration(
        model, LoopColorDeclaration(declaration.scheme, "Nc", {}, (), ())
    )
    handle = _compiled_model_from_payload(model)
    for expression in ("u u~ > d d~", "e+ e- > mu+ mu-"):
        directory = tmp_path / expression.replace(" ", "")
        directory.mkdir()
        generator = _generator(directory, expression, ("QCD",), "lc", "loop_qcd_qed_sm")
        blocker = _assert_refused(
            generator, _processes(expression), directory / "out", model=handle
        )
        assert "corrections other than the model's strong one (QCD)" in blocker
