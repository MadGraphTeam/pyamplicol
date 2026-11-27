# SPDX-License-Identifier: 0BSD
"""Leading and next-to-leading colour of QED and QCD+QED one-loop
corrections are refused with their true reason (listed key
``lc-electroweak-corrections``): not implemented yet, because the
electroweak counterterms of the QCD+QED models (sums of an N_c-free part
and a closed-quark-loop part proportional to N_c) have no formal-N_c
declaration. Full colour serves them; the refusal offers no other remedy
(a user colour declaration does not make these requests work)."""

from __future__ import annotations

import pytest

KEY = "lc-electroweak-corrections"


@pytest.mark.loop_fast
@pytest.mark.parametrize(
    "corrections,model_corrections,uncovered,refused",
    [
        # QED or QCD+QED corrections at LC/NLC: refused whatever colour data
        # the model carries.
        (("QCD", "QED"), ("QCD", "QED"), False, True),
        (("QED",), ("QCD", "QED"), False, True),
        (("QED",), ("QCD", "QED"), True, True),
        # QCD corrections alone on a model declaring QED corrections: refused
        # only without a colour declaration (none ships for these models).
        (("QCD",), ("QCD", "QED"), True, True),
        (("QCD",), ("QCD", "QED"), False, False),
        # A QCD model: never this key (colour-declaration-coverage decides).
        (("QCD",), ("QCD",), True, False),
        (("QCD",), ("QCD",), False, False),
    ],
)
def test_the_guard_refuses_exactly_the_electroweak_cases(
    corrections, model_corrections, uncovered, refused
):
    from pyamplicol.api.errors import GenerationError
    from pyamplicol.generation.loop_service import _refuse_projected_electroweak
    from pyamplicol.loops.v2.refusals import LoopRequestUnsupported

    def call():
        _refuse_projected_electroweak(
            "lc", corrections, model_corrections, uncovered=uncovered
        )

    if not refused:
        call()
        return
    with pytest.raises(GenerationError) as error:
        call()
    assert isinstance(error.value, LoopRequestUnsupported)
    assert error.value.key == KEY
    text = str(error.value)
    assert text.startswith(f"{KEY}: LC one-loop generation ")
    assert "is not implemented yet" in text
    assert "no formal-N_c colour declaration" in text
    assert 'Instead: full colour (color.accuracy = "full"' in text
    # No remedy that does not work: no user declaration is offered.
    assert "with_loop_color_declaration" not in text
    assert "LoopColorDeclaration" not in text


def _card(output, expression: str, orders, accuracy: str) -> str:
    import json

    return f"""
action = "generate"
[model]
source = "loop_qcd_qed_sm"
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


@pytest.mark.loop_physics
@pytest.mark.parametrize(
    "orders,accuracy,phrase",
    [
        (("QCD", "QED"), "lc", "LC one-loop generation with QCD+QED corrections"),
        (("QED",), "nlc", "NLC one-loop generation with QED corrections"),
        (
            ("QCD",),
            "lc",
            "LC one-loop generation is not implemented yet on a model declaring "
            "QCD+QED corrections, also for its QCD corrections alone",
        ),
    ],
)
def test_the_refusal_says_why_in_the_dry_run_and_at_generation(
    tmp_path, orders, accuracy, phrase
):
    from pyamplicol.api import Generator, ProcessRequest, ProcessSet
    from pyamplicol.api.errors import GenerationError
    from pyamplicol.config import resolve_config
    from pyamplicol.loops.v2.refusals import LoopRequestUnsupported
    from pyamplicol.models.loading import compile_model_source

    # The dry run compiles no model: populate the model cache first.
    compile_model_source("loop_qcd_qed_sm", restriction="default")
    card = tmp_path / "card.toml"
    card.write_text(_card(tmp_path / "out", "u u~ > d d~", orders, accuracy))
    generator = Generator(resolve_config(card))
    processes = ProcessSet((ProcessRequest.parse("u u~ > d d~", name="p"),))
    plan = generator.plan(processes)
    (blocker,) = plan.unsupported_features
    assert blocker.startswith(f"{KEY}: "), blocker
    assert phrase in blocker
    assert "LoopColorDeclaration" not in blocker
    assert "with_loop_color_declaration" not in blocker
    with pytest.raises(GenerationError) as refused:
        generator.generate(processes, tmp_path / "out")
    assert isinstance(refused.value, LoopRequestUnsupported)
    assert refused.value.key == KEY
    assert str(refused.value) == str(blocker)
    assert not (tmp_path / "out").exists()
