# SPDX-License-Identifier: 0BSD
"""A one-loop process named in another leg order than the stored one, and a
process-group member, served as its own process: selections in the Python
API and access through the native SDK.

With multiparticle labels the stored leg order is the expansion's canonical
one, so the order a user writes is often a permutation of it. The stored
artifact (loop_sm, QCD, ``process.flavor_blind``) holds ``u g > u g``,
``d u > d u``, ``u u~ > u u~`` and ``d d~ > g g``, and serves ``s~ s > g g``
as an exact process-group member of ``d d~ > g g``. Each spelling below
(both sides swapped in a gluon-quark process, the final or the initial
state alone, distinct- and identical-flavour quark lines, the member) is
served by its stored process at the permuted momenta, and at full and at
leading colour:

* its helicity rows and leading-colour flows are those of a single-process
  artifact generated for that spelling (IDs, values and order), each
  helicity selection and each colour-flow selection equals that artifact's
  (binary64, 1e-12 of the largest inclusive coefficient: the arithmetic
  runs in another leg order), and the selections sum to the inclusive value;
* a resolved selection lists that artifact's rows, and an explicit
  reduction backend serves the selection as well;
* the native SDK opens the spelling (C ABI) with the Python API's values
  bit for bit: the ordinary value, a helicity selection, the resolved rows
  and, on the mapping artifact of ``test_loop_v2_mapping``, the colour- and
  spin-correlated outputs of a permutation alias and a member;
* a spelling that is not served is refused with a typed error carrying a
  ``key`` (Python) and a selector error (C ABI).
"""

from __future__ import annotations

import ctypes
from decimal import Decimal

import pytest

from tests.unit.test_loop_v2_mapping import (
    PARAMETERS,
    POINTS,
    POINTS_5,
    SCALES,
    _generate,
    mapped,  # noqa: F401  (the mapping artifact fixture)
    open_,  # noqa: F401  (the mapping artifact with open declarations)
)

pytestmark = pytest.mark.loop_physics

STORED = (
    ("ug", "u g > u g"),
    ("du", "d u > d u"),
    ("uux", "u u~ > u u~"),
    ("ddx", "d d~ > g g"),
    ("ssx", "s s~ > g g"),
    ("sxs", "s~ s > g g"),
)
SINGLES = (
    ("gu", "g u > g u"),
    ("ugf", "u g > g u"),
    ("gui", "g u > u g"),
    ("ud", "u d > u d"),
    ("uxu", "u~ u > u~ u"),
    ("ssx", "s s~ > g g"),
    ("sxs", "s~ s > g g"),
)
# spelling -> (the stored process serving it, the single-process artifact's
# process of that spelling, representative leg -> public leg)
CASES = {
    "g u > g u": ("ug", "gu", (1, 0, 3, 2)),
    "u g > g u": ("ug", "ugf", (0, 1, 3, 2)),
    "g u > u g": ("ug", "gui", (1, 0, 2, 3)),
    "u d > u d": ("du", "ud", (1, 0, 3, 2)),
    "u~ u > u~ u": ("uux", "uxu", (1, 0, 3, 2)),
    # Process-group members of d d~ > g g at full colour: a species
    # substitution, and one composed with the initial-state swap. At leading
    # colour the generation proves no species substitution: it stores
    # s s~ > g g and serves s~ s > g g as its permuted member.
    "s s~ > g g": ("ddx", "ssx", (0, 1, 2, 3)),
    "s~ s > g g": ("ddx", "sxs", (1, 0, 2, 3)),
}
LEADING_STORED = {
    "s s~ > g g": ("ssx", (0, 1, 2, 3)),
    "s~ s > g g": ("ssx", (1, 0, 2, 3)),
}
NOT_SERVED = ("u u > d d", "u g > d g", "u u~ > g")


@pytest.fixture(scope="module", params=["full", "lc"])
def accuracy(request):
    return request.param


@pytest.fixture(scope="module")
def stored(loop_sm_compiled_model, loop_native, tmp_path_factory, accuracy):
    del loop_native
    return _generate(
        loop_sm_compiled_model,
        tmp_path_factory.mktemp(f"stored-{accuracy}"),
        STORED,
        process="flavor_blind = true",
        histories=[],
        spin=[],
        accuracy=accuracy,
    )


@pytest.fixture(scope="module")
def singles(loop_sm_compiled_model, loop_native, tmp_path_factory, accuracy):
    del loop_native
    return _generate(
        loop_sm_compiled_model,
        tmp_path_factory.mktemp(f"singles-{accuracy}"),
        SINGLES,
        histories=[],
        spin=[],
        accuracy=accuracy,
    )


def _load(artifact, process, **options):
    from pyamplicol import Runtime

    return Runtime.load(
        artifact, process=process, model_parameters=PARAMETERS, **options
    )


def _numbers(result) -> list[complex]:
    """Every value of an ordinary or resolved evaluation, flattened."""

    out: list[complex] = []

    def walk(value):
        if isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        elif hasattr(value, "finite"):
            out.extend(_coefficients(value))
        elif value is not None:
            out.append(complex(value))

    walk(result.born_values)
    walk(result.values)
    return out


def _coefficients(value) -> list[complex]:
    """A Laurent value's coefficients (finite, single and double pole)."""

    return [
        complex(c)
        for c in (value.finite, value.single_pole, value.double_pole)
        if c is not None
    ]


def _scale(result) -> float:
    return max(abs(x) for x in _numbers(result)) or 1.0


def _close(left, right, scale, label) -> None:
    a, b = _numbers(left), _numbers(right)
    assert len(a) == len(b), label
    worst = max((abs(x - y) for x, y in zip(a, b, strict=True)), default=0.0)
    assert worst <= 1e-12 * scale, (label, worst / scale)


def _add(results) -> list[complex]:
    total = None
    for result in results:
        values = _numbers(result)
        total = (
            values
            if total is None
            else [x + y for x, y in zip(total, values, strict=True)]
        )
    return total or []


def test_the_mapping_is_the_stored_process_at_the_permuted_legs(stored, accuracy):
    """Each spelling is served by the stored process it names, through the
    representative-to-public permutation of the case."""

    for spelling, (representative, _single, permutation) in CASES.items():
        if accuracy == "lc" and spelling in LEADING_STORED:
            representative, permutation = LEADING_STORED[spelling]
        runtime = _load(stored, spelling)
        backend = runtime._backend
        assert backend.representative_process_key == representative, spelling
        assert backend.external_permutation == permutation, spelling


def test_selections_of_a_permuted_spelling_are_its_own_generations(
    stored, singles, accuracy
):
    """F3: helicity rows and colour flows of each spelling are those of its
    own single-process artifact (IDs, values, order), each selection equals
    that artifact's selection, and the selections sum to the inclusive."""

    for spelling, (_representative, single, _permutation) in CASES.items():
        mapped_, own = _load(stored, spelling), _load(singles, single)
        physics, expected = mapped_.physics, own.physics
        assert [(h.id, h.values) for h in physics.helicities] == [
            (h.id, h.values) for h in expected.helicities
        ], spelling
        assert physics.selector_capabilities == expected.selector_capabilities
        flows = [a.id for a in physics.born_anchored_color_components]
        assert flows == [a.id for a in expected.born_anchored_color_components]
        assert bool(flows) == (accuracy == "lc"), spelling
        inclusive = mapped_.evaluate(POINTS, mu_r2=SCALES)
        _close(
            inclusive, own.evaluate(POINTS, mu_r2=SCALES), _scale(inclusive), spelling
        )
        scale = _scale(inclusive)
        selections = []
        for helicity in physics.helicities:
            left = mapped_.evaluate(POINTS, mu_r2=SCALES, helicities=[helicity.id])
            right = own.evaluate(POINTS, mu_r2=SCALES, helicities=[helicity.id])
            _close(left, right, scale, (spelling, helicity.id))
            selections.append(left)
        total = _numbers(inclusive)
        for x, y in zip(_add(selections), total, strict=True):
            assert abs(x - y) <= 1e-12 * scale, spelling
        if accuracy != "lc":
            continue
        selections = []
        for ordinal, flow in enumerate(flows, start=1):
            left = mapped_.evaluate(POINTS, mu_r2=SCALES, color_flows=[flow])
            right = own.evaluate(POINTS, mu_r2=SCALES, color_flows=[flow])
            _close(left, right, scale, (spelling, flow))
            by_ordinal = mapped_.evaluate(
                POINTS, mu_r2=SCALES, color_flows=[str(ordinal)]
            )
            assert _numbers(by_ordinal) == _numbers(left), (spelling, ordinal)
            selections.append(left)
        for x, y in zip(_add(selections), total, strict=True):
            assert abs(x - y) <= 1e-12 * scale, spelling


def test_resolved_selections_of_a_permuted_spelling(stored, singles, accuracy):
    """A resolved helicity selection lists the selected rows of the spelling
    (its own IDs and order) with its own generation's values, per helicity
    row and, at leading colour, per flow through the Born basis element each
    flow is anchored to; the complete resolved output too."""

    for spelling, (_representative, single, _permutation) in CASES.items():
        mapped_, own = _load(stored, spelling), _load(singles, single)
        ids = [h.id for h in mapped_.physics.helicities][1::3]
        scale = _scale(mapped_.evaluate(POINTS, mu_r2=SCALES))
        for selection in ({"helicities": ids}, {}):
            left = mapped_.evaluate_resolved(POINTS, mu_r2=SCALES, **selection)
            right = own.evaluate_resolved(POINTS, mu_r2=SCALES, **selection)
            assert left.helicity_ids == right.helicity_ids, spelling
            if accuracy != "lc":
                _close(left, right, scale, spelling)
                continue
            anchors = {
                a.id: a.born_term_indices
                for a in mapped_.physics.born_anchored_color_components
            }
            theirs = {
                a.id: a.born_term_indices
                for a in own.physics.born_anchored_color_components
            }
            for flow, (basis,) in anchors.items():
                (other,) = theirs[flow]
                a = list(left.virtual_color_ids).index(f"basis-{basis}")
                b = list(right.virtual_color_ids).index(f"basis-{other}")
                for x, y in zip(left.values, right.values, strict=True):
                    for sector_x, sector_y in zip(x, y, strict=True):
                        for row_x, row_y in zip(sector_x, sector_y, strict=True):
                            for c, d in zip(
                                _coefficients(row_x[a]),
                                _coefficients(row_y[b]),
                                strict=True,
                            ):
                                assert abs(complex(c) - complex(d)) <= 1e-12 * scale


def test_every_reduction_backend_serves_the_selection(stored, singles, accuracy):
    """The selection of a permuted spelling on an explicit reduction backend
    (NinjaRS and TIRust, where built) equals its own generation's."""

    from pyamplicol.api.errors import ReductionUnavailable

    spelling = "u d > u d"
    _representative, single, _permutation = CASES[spelling]
    mapped_, own = _load(stored, spelling), _load(singles, single)
    scale = _scale(mapped_.evaluate(POINTS, mu_r2=SCALES))
    selection = {"helicities": [mapped_.physics.helicities[5].id]}
    if accuracy == "lc":
        selection["color_flows"] = ["1"]
    for reduction in ("ninjars", "tirust"):
        try:
            left = mapped_.evaluate(
                POINTS, mu_r2=SCALES, reduction=reduction, **selection
            )
        except ReductionUnavailable:
            continue
        right = own.evaluate(POINTS, mu_r2=SCALES, reduction=reduction, **selection)
        _close(left, right, scale, reduction)
        orders = mapped_.evaluate_orders(
            POINTS, mu_r2=SCALES, reduction=reduction, **selection
        )
        assert _numbers(orders) == _numbers(left)


def test_a_spelling_that_is_not_served_is_refused_with_a_key(stored):
    """A process the artifact neither stores nor serves through a mapping
    (another flavour content, a missing particle) is refused at load with a
    typed error that carries a key."""

    from pyamplicol.api.errors import EvaluationError, ProcessSelectionError

    for spelling in NOT_SERVED:
        with pytest.raises(ProcessSelectionError) as error:
            _load(stored, spelling)
        assert isinstance(error.value, EvaluationError)
        assert error.value.key == "process-not-served", spelling
        assert repr(spelling) in str(error.value)


# -- the native SDK ------------------------------------------------------------


def _exact(points):
    return [[[str(Decimal(c)) for c in p] for p in point] for point in points]


def _python_layout(result, resolved: bool) -> tuple[list[float], list[float]]:
    """The Python API's Born and virtual values in the C ABI's layouts."""

    from tests.unit.test_loop_v2_sdk_extras import _flat, _laurent

    if resolved:
        born = [x for b in result.born_values for o in b for row in o for x in row]
        virtual = [
            x
            for v in result.values
            for sector in v
            for row in sector
            for value in row
            for x in _laurent(value)
        ]
    else:
        born = [v for b in result.born_values for v in b]
        virtual = [x for v in result.values for value in v for x in _laurent(value)]
    return _flat(born), _flat(virtual)


def _capabilities(sdk, handle) -> dict:
    from tests.unit.test_loop_v2_sdk_selection import _json

    return _json(sdk.rusticol_virtual_capabilities_json, handle)


def test_the_native_sdk_opens_each_spelling_with_the_python_values(stored):
    """F4: the C ABI opens every spelling (momenta in the order the caller
    names), lists its helicity rows as the Python API does, and returns the
    Python API's values bit for bit: the ordinary value, the resolved rows
    and a helicity selection (by runtime ID, by tree ID and per point). A
    spelling that is not served is refused with a selector error."""

    from tests.unit.test_loop_v2_sdk_extras import (
        _error,
        _open,
        _request,
        _ResultShape,
        _sdk,
    )
    from tests.unit.test_loop_v2_sdk_selection import _bitwise, _call, _python_values

    sdk = _sdk()
    points = [[[float(c) for c in p] for p in point] for point in POINTS]
    scales = [float(s) for s in SCALES]
    exact, mu = _exact(points), [str(Decimal(s)) for s in scales]
    for spelling in CASES:
        runtime = _load(stored, spelling)
        handle = _open(sdk, stored, spelling)
        try:
            capabilities = _capabilities(sdk, handle)
            assert (
                capabilities["process"].lower().split()
                == runtime.physics.process.lower().split()
            ), spelling
            assert capabilities["process_id"] == runtime.physics.process_id
            rows = [
                tuple(v for _leg, v in row) for row in capabilities["helicity_rows"]
            ]
            assert rows == [tuple(h.values) for h in runtime.physics.helicities]
            for resolved in (False, True):
                request, _keep = _request(points, scales, resolved)
                result = ctypes.c_void_p()
                status = sdk.rusticol_virtual_evaluate(
                    handle, ctypes.byref(request), ctypes.byref(result)
                )
                assert status == 0, _error(sdk)
                try:
                    shape = _ResultShape()
                    assert (
                        sdk.rusticol_virtual_result_shape(result, ctypes.byref(shape))
                        == 0
                    )
                    born = (ctypes.c_double * shape.born_values)()
                    loop = (ctypes.c_double * shape.virtual_values)()
                    sdk.rusticol_virtual_result_copy_born(result, born, len(born))
                    sdk.rusticol_virtual_result_copy_virtual(result, loop, len(loop))
                finally:
                    sdk.rusticol_virtual_result_free(result)
                call = runtime.evaluate_resolved if resolved else runtime.evaluate
                want_born, want_virtual = _python_layout(
                    call(exact, mu_r2=mu), resolved
                )
                assert _bitwise(list(born), want_born), (spelling, resolved)
                assert _bitwise(list(loop), want_virtual), (spelling, resolved)
            helicity = runtime.physics.helicities[5]
            tree_id = "h:" + ",".join(f"{v:+d}" for v in helicity.values)
            for selectors, resolved in (
                ({"ids": [helicity.id]}, False),
                ({"ids": [tree_id]}, False),
                ({"by_point": [5, 10]}, False),
                ({"resolved": True, "ids": ["h1", helicity.id]}, True),
            ):
                found = _call(sdk, handle, points, scales, **selectors)
                assert found["status"] == 0, (spelling, selectors, found.get("error"))
                if "by_point" in selectors:
                    expected = [
                        runtime.evaluate(
                            exact[k : k + 1],
                            mu_r2=mu[k : k + 1],
                            helicities=[f"h{row}"],
                        )
                        for k, row in enumerate(selectors["by_point"])
                    ]
                    want = [x for e in expected for x in _python_values(e, False)]
                else:
                    ids = [helicity.id if i == tree_id else i for i in selectors["ids"]]
                    call = runtime.evaluate_resolved if resolved else runtime.evaluate
                    want = _python_values(
                        call(exact, mu_r2=mu, helicities=ids), resolved
                    )
                assert _bitwise(found["virtual"], want), (spelling, selectors)
        finally:
            sdk.rusticol_virtual_free(handle)
    for spelling in NOT_SERVED:
        handle = ctypes.c_void_p()
        status = sdk.rusticol_virtual_open(
            str(stored).encode(), spelling.encode(), None, None, ctypes.byref(handle)
        )
        assert status != 0, spelling
        assert spelling in _error(sdk), spelling


def test_the_native_sdk_serves_mapped_correlations(mapped):  # noqa: F811
    """F4 on the mapping artifact (declared colour histories and spin
    classes): the C ABI lists the histories and spin classes the Python API
    serves a permutation alias and a process-group member, and returns their
    correlated outputs (a spin source on a relabelled leg) bit for bit."""

    from pyamplicol.correlators import CorrelatedRequest
    from tests.unit.test_loop_v2_sdk_extras import (
        _error,
        _laurent,
        _open,
        _request,
        _sdk,
        _Sources,
    )
    from tests.unit.test_loop_v2_sdk_selection import _bitwise

    class _Shape(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_size_t)
            for name in (
                "requested_points",
                "successful_points",
                "born_values",
                "virtual_values",
                "histories",
                "born_orders",
                "virtual_orders",
                "epsilon_count",
            )
        ]

    sdk = _sdk()
    points = [[[float(c) for c in p] for p in point] for point in POINTS[:1]]
    scales = [float(SCALES[0])]
    exact, mu = _exact(points), [str(Decimal(scales[0]))]
    vector = [(0.5, 0.25), (0.75, -0.125), (0.375, 1.0), (-0.625, 0.5)]
    spin = {4: tuple((Decimal(re), Decimal(im)) for re, im in vector)}
    for name in ("ddx_swap", "sxs"):
        runtime = _load(mapped, name)
        histories = [h.id for h in runtime.available_color_correlations()]
        handle = _open(sdk, mapped, name)
        try:
            capabilities = _capabilities(sdk, handle)
            assert capabilities["correlation_histories"] == histories, name
            observables = runtime._backend._observable_runtime()._observables
            served = [list(c) for c in observables.spin_classes]
            assert capabilities["spin_correlation_classes"] == served, name
            expected = runtime.evaluate_correlated_many(
                exact, {h: CorrelatedRequest(h, spin) for h in histories}, mu_r2=mu
            )
            flat = [x for pair in vector for x in pair]
            values = (ctypes.c_double * len(flat))(*flat)
            sources = _Sources((ctypes.c_size_t * 1)(4), 1, values, len(vector))
            request, _keep = _request(points, scales, False)
            result = ctypes.c_void_p()
            status = sdk.rusticol_virtual_evaluate_correlated_with_sources(
                handle,
                ctypes.byref(request),
                ctypes.byref(sources),
                ctypes.byref(result),
            )
            assert status == 0, _error(sdk)
            try:
                shape = _Shape()
                assert (
                    sdk.rusticol_virtual_correlated_result_shape(
                        result, ctypes.byref(shape)
                    )
                    == 0
                )
                assert shape.histories == len(histories), name
                loop = (ctypes.c_double * (2 * shape.virtual_values))()
                assert (
                    sdk.rusticol_virtual_correlated_result_copy_virtual(
                        result, loop, shape.virtual_values
                    )
                    == 0
                )
            finally:
                sdk.rusticol_virtual_correlated_result_free(result)
            want: list[float] = []
            for history in histories:
                for sector in expected[history].values[0]:
                    for coefficient in _laurent(sector):
                        value = complex(coefficient)
                        want += [value.real, value.imag]
            assert _bitwise(list(loop), want), name
        finally:
            sdk.rusticol_virtual_free(handle)


# -- a reference colour order -----------------------------------------------

# (stored process, its spelling, the colour selectors of the card)
REFERENCED = {
    "gluon": (
        ("ug", "u g > u g"),
        ("gu", "g u > g u"),
        "reference_color_order = [3, 4, 2, 1]",
    ),
    "quarks": (
        ("du", "d u > d u"),
        ("ud", "u d > u d"),
        "reference_color_order = [3, 1, 4, 2]",
    ),
    "fixed": (
        ("ug", "u g > u g"),
        ("gu", "g u > g u"),
        "reference_color_order = [4, 1, 3, 2]\nselected_color_sector_ids = [0]",
    ),
    "reference-cap": (
        ("ug", "u g > u g"),
        ("gu", "g u > g u"),
        "reference_color_order = [3, 4, 2, 1]\nmax_color_sectors = 1",
    ),
    "two-sectors": (
        ("uuxggg", "u u~ > g g g"),
        ("uxuggg", "u~ u > g g g"),
        "selected_color_sector_ids = [1, 3]",
    ),
}


@pytest.fixture(scope="module", params=sorted(REFERENCED))
def referenced(request, loop_sm_compiled_model, loop_native, tmp_path_factory):
    """At leading colour, a card with colour selectors (a reference colour
    order, fixed sector ids): the stored process, and the spelling generated
    on its own with the same card."""

    del loop_native
    stored_entry, single_entry, option = REFERENCED[request.param]
    artifacts = [
        _generate(
            loop_sm_compiled_model,
            tmp_path_factory.mktemp(f"referenced-{request.param}-{which}"),
            (entry,),
            process=option,
            histories=[],
            spin=[],
            accuracy="lc",
        )
        for which, entry in (("stored", stored_entry), ("single", single_entry))
    ]
    return (*artifacts, single_entry, stored_entry[0])


def test_colour_selectors_keep_the_fresh_spellings_ordinals(referenced):
    """A reference colour order names the legs of the spelling it is written
    for and a sector id a position in that spelling's plan. One rule: where
    the spelling generated on its own with the same card publishes the same
    flows as the mapped process, the mapped process lists them in its order
    and every ordinal selects what the fresh ordinal selects, none beyond
    its length; where they differ, every ordinal is refused typed. Every ID
    the two share selects the same value; the stored spelling keeps its
    ordinals."""

    from pyamplicol.api.errors import CompatibilityError, EvaluationError

    stored, single, (name, spelling), stored_name = referenced
    mapped_, own = _load(stored, spelling), _load(single, name)
    points, scales = (
        (POINTS_5, SCALES[:1]) if len(spelling.split()) == 6 else (POINTS, SCALES)
    )
    flows = [a.id for a in mapped_.physics.born_anchored_color_components]
    fresh = [a.id for a in own.physics.born_anchored_color_components]
    scale = _scale(own.evaluate(points, mu_r2=scales))
    for flow in set(flows) & set(fresh):
        left = mapped_.evaluate(points, mu_r2=scales, color_flows=[flow])
        right = own.evaluate(points, mu_r2=scales, color_flows=[flow])
        _close(left, right, scale, flow)
    if sorted(flows) == sorted(fresh):
        assert flows == fresh
        for ordinal, flow in enumerate(flows, start=1):
            left = mapped_.evaluate(points, mu_r2=scales, color_flows=[str(ordinal)])
            right = own.evaluate(points, mu_r2=scales, color_flows=[str(ordinal)])
            _close(left, right, scale, ordinal)
            by_id = mapped_.evaluate(points, mu_r2=scales, color_flows=[flow])
            assert _numbers(by_id) == _numbers(left)
    else:
        for ordinal in range(1, len(flows) + 1):
            with pytest.raises(CompatibilityError) as error:
                mapped_.evaluate(points, mu_r2=scales, color_flows=[str(ordinal)])
            assert "select the flow by its ID" in str(error.value)
    # No ordinal beyond the fresh list (out of range, or refused typed).
    with pytest.raises((EvaluationError, CompatibilityError)):
        mapped_.evaluate(points, mu_r2=scales, color_flows=[str(len(fresh) + 1)])
    stored_runtime = _load(stored, stored_name)
    first = stored_runtime.physics.born_anchored_color_components[0].id
    assert _numbers(
        stored_runtime.evaluate(points, mu_r2=scales, color_flows=["1"])
    ) == _numbers(stored_runtime.evaluate(points, mu_r2=scales, color_flows=[first]))


SUBSETS = {"cap": "max_color_sectors = 1", "fixed": "selected_color_sector_ids = [0]"}
SWAP = ("uugg_swap", "uugg", (0, 1, 3, 2))


@pytest.fixture(scope="module")
def complete_uugg(loop_sm_compiled_model, loop_native, tmp_path_factory):
    del loop_native
    return _generate(
        loop_sm_compiled_model,
        tmp_path_factory.mktemp("complete-uugg"),
        (("uugg", "u u~ > g g"),),
        histories=[],
        spin=[],
        accuracy="lc",
    )


@pytest.fixture(scope="module", params=sorted(SUBSETS))
def subset(request, loop_sm_compiled_model, loop_native, tmp_path_factory):
    """u u~ > g g at leading colour with one sector kept (a cap of 1, or the
    fixed sector 0), and its alias exchanging the outgoing gluons."""

    del loop_native
    return _generate(
        loop_sm_compiled_model,
        tmp_path_factory.mktemp(f"subset-{request.param}"),
        (("uugg", "u u~ > g g"),),
        (SWAP,),
        process=SUBSETS[request.param],
        histories=[],
        spin=[],
        accuracy="lc",
    )


def test_a_subset_that_keeps_other_flows_on_the_mapped_legs_refuses_ordinals(
    subset, complete_uugg
):
    """With one sector kept and no reference, the alias exchanging the
    outgoing gluons is served flow:2,4,3,1 (the stored flow:2,3,4,1 on its
    legs), while a fresh artifact of its spelling with the same card keeps
    flow:2,3,4,1: its ordinal is refused typed (never the fresh ordinal's
    other flow), and its ID keeps its meaning (the complete artifact's
    flow:2,4,3,1)."""

    from pyamplicol.api.errors import CompatibilityError

    alias, stored = _load(subset, "uugg_swap"), _load(subset, "uugg")
    assert [a.id for a in stored.physics.born_anchored_color_components] == [
        "flow:2,3,4,1"
    ]
    assert [a.id for a in alias.physics.born_anchored_color_components] == [
        "flow:2,4,3,1"
    ]
    with pytest.raises(CompatibilityError) as error:
        alias.evaluate(POINTS, mu_r2=SCALES, color_flows=["1"])
    assert "select the flow by its ID" in str(error.value)
    complete = _load(complete_uugg, "uugg")
    left = alias.evaluate(POINTS, mu_r2=SCALES, color_flows=["flow:2,4,3,1"])
    right = complete.evaluate(POINTS, mu_r2=SCALES, color_flows=["flow:2,4,3,1"])
    _close(left, right, _scale(complete.evaluate(POINTS, mu_r2=SCALES)), "swap")
    # The stored spelling keeps its ordinal.
    assert _numbers(stored.evaluate(POINTS, mu_r2=SCALES, color_flows=["1"])) == (
        _numbers(stored.evaluate(POINTS, mu_r2=SCALES, color_flows=["flow:2,3,4,1"]))
    )


def test_ordinals_no_listing_reproduces_are_refused():
    """Where the plan of the mapped spelling with the card's reference lists
    other flows than the stored process's, its ordinals are refused typed,
    naming the selection by ID (never another flow under a valid ordinal)."""

    from pyamplicol.api.errors import CompatibilityError
    from pyamplicol.loops.v2.selection import Catalogue, Flow

    flow = Flow("flow:3,1,4,2", (3, 1, 4, 2), 0, 0)
    catalogue = Catalogue((), (flow,), ordinals=False)
    assert catalogue.resolve(None, ["flow:3,1,4,2"]) == (None, frozenset({0}))
    with pytest.raises(CompatibilityError) as error:
        catalogue.resolve(None, ["1"])
    assert "select the flow by its ID" in str(error.value)


def test_the_native_sdk_refuses_a_spin_source_the_mapped_process_is_not_served(
    open_,  # noqa: F811
):
    """The alias d~ d > g g of d d~ > g g with the spin class (4,) declared
    is served no spin class (its leg 3 is the stored leg 4): the C ABI
    lists none and refuses a source on public leg 3 as on public leg 4,
    before anything is evaluated, as the Python API refuses them."""

    from pyamplicol.api.errors import EvaluationError
    from pyamplicol.correlators import CorrelatedRequest
    from tests.unit.test_loop_v2_sdk_extras import (
        _error,
        _open,
        _request,
        _sdk,
        _Sources,
    )

    sdk = _sdk()
    runtime = _load(open_, "ddx_swap")
    points = [[[float(c) for c in p] for p in point] for point in POINTS[:1]]
    exact, mu = _exact(points), [str(Decimal(SCALES[0]))]
    vector = [(0.5, 0.25), (0.75, -0.125), (0.375, 1.0), (-0.625, 0.5)]
    handle = _open(sdk, open_, "ddx_swap")
    try:
        assert _capabilities(sdk, handle)["spin_correlation_classes"] == []
        for leg in (3, 4):
            spin = {leg: tuple((Decimal(re), Decimal(im)) for re, im in vector)}
            with pytest.raises(EvaluationError):
                runtime.evaluate_correlated_many(
                    exact, {"born": CorrelatedRequest("born", spin)}, mu_r2=mu
                )
            flat = [x for pair in vector for x in pair]
            values = (ctypes.c_double * len(flat))(*flat)
            sources = _Sources((ctypes.c_size_t * 1)(leg), 1, values, len(vector))
            request, _keep = _request(points, [float(SCALES[0])], False)
            result = ctypes.c_void_p()
            status = sdk.rusticol_virtual_evaluate_correlated_with_sources(
                handle,
                ctypes.byref(request),
                ctypes.byref(sources),
                ctypes.byref(result),
            )
            assert status != 0, leg
            assert not result.value
            assert f"spin legs [{leg}] are not a declared spin class" in _error(sdk)
    finally:
        sdk.rusticol_virtual_free(handle)


def _tampered(artifact, tmp_path, edit):
    """A copy of ``artifact`` whose ``config/effective.toml`` is edited
    (``edit(text)``, None deletes it); its manifest is left untouched."""

    import shutil

    copy = tmp_path / f"copy-{len(list(tmp_path.iterdir()))}"
    shutil.copytree(artifact, copy)
    path = copy / "config" / "effective.toml"
    text = edit(path.read_text())
    if text is None:
        path.unlink()
    else:
        path.write_text(text)
    return copy


def _moved_card(artifact, tmp_path):
    """A copy of ``artifact`` whose genuine effective configuration is moved
    to ``config/card-at-generation.toml`` (the manifest's record and
    identity updated, so its payloads verify) and an undeclared
    ``config/effective.toml`` holding only an empty ``[process]`` table is
    put beside it."""

    import json
    import shutil

    from pyamplicol.artifacts import compute_artifact_id, load_manifest

    copy = tmp_path / f"moved-{len(list(tmp_path.iterdir()))}"
    shutil.copytree(artifact, copy)
    (copy / "config" / "effective.toml").rename(
        copy / "config" / "card-at-generation.toml"
    )
    manifest = json.loads((copy / "artifact.json").read_text())
    for payload in manifest["payloads"]:
        if payload["path"] == "config/effective.toml":
            payload["path"] = "config/card-at-generation.toml"
    manifest["configuration"]["effective_path"] = "config/card-at-generation.toml"
    manifest["artifact_id"] = compute_artifact_id(manifest)
    (copy / "artifact.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (copy / "config" / "effective.toml").write_text("[process]\n")
    load_manifest(copy, verify_payloads=True)
    return copy


EDITS = {
    "cap-byte": lambda text: text.replace("max_color_sectors", "#ax_color_sectors"),
    "reference": lambda text: text.replace("[3, 4, 2, 1]", "[3, 4, 1, 2]"),
    "deleted": lambda text: None,
}


def _first_ordinal_refused(artifact, name: str) -> bool:
    from pyamplicol.api.errors import CompatibilityError

    runtime = _load(artifact, name)
    listed = [a.id for a in runtime.physics.born_anchored_color_components]
    # The IDs always work.
    runtime.evaluate(POINTS, mu_r2=SCALES, color_flows=[listed[0]])
    try:
        runtime.evaluate(POINTS, mu_r2=SCALES, color_flows=["1"])
    except CompatibilityError as error:
        assert "select the flow by its ID" in str(error)
        return True
    return False


def _old_format(loop_sm_compiled_model, root, entries, aliases, option):
    """An artifact as written before the request recorded the card's colour
    selectors (``SliceRequest.colour_selectors`` absent)."""

    from pyamplicol.generation import loop_service

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(loop_service, "_card_colour_selectors", lambda backend: None)
        return _generate(
            loop_sm_compiled_model,
            root,
            entries,
            aliases,
            process=option,
            histories=[],
            spin=[],
            accuracy="lc",
        )


@pytest.fixture(scope="module")
def old_format(loop_sm_compiled_model, loop_native, tmp_path_factory):
    """Old-format artifacts: the capped u u~ > g g with its gluon-swapping
    alias, and u g > u g with the uncapped reference [3, 4, 2, 1]."""

    del loop_native
    return {
        "cap": _old_format(
            loop_sm_compiled_model,
            tmp_path_factory.mktemp("old-cap"),
            (("uugg", "u u~ > g g"),),
            (SWAP,),
            SUBSETS["cap"],
        ),
        "reference": _old_format(
            loop_sm_compiled_model,
            tmp_path_factory.mktemp("old-reference"),
            (("ug", "u g > u g"),),
            (),
            "reference_color_order = [3, 4, 2, 1]",
        ),
    }


# The 2 -> 2 cards of REFERENCED (the checks below read 2 -> 2 spellings).
_REFERENCED_2TO2 = sorted(
    key for key, (stored, _single, _option) in REFERENCED.items()
    if len(stored[1].split()) == 5
)


@pytest.mark.parametrize("referenced", _REFERENCED_2TO2, indirect=True)
def test_new_artifacts_record_the_card_selectors(subset, referenced, tmp_path):
    """A new artifact records the card's colour selectors with its request
    (covered by its identity): its mapped ordinals follow them and no edit,
    move or removal of the effective configuration changes that."""

    import json

    stored, _single, (_name, spelling), stored_name = referenced
    request = json.loads(
        (stored / "processes" / stored_name / "execution.json").read_text()
    )["request"]
    assert request["colour_selectors"]
    expected = _first_ordinal_refused(stored, spelling)
    for artifact, name, wanted in (
        (subset, "uugg_swap", True),
        (stored, spelling, expected),
    ):
        assert _first_ordinal_refused(artifact, name) is wanted
        for edit in EDITS.values():
            copy = _tampered(artifact, tmp_path, edit)
            assert _first_ordinal_refused(copy, name) is wanted
        assert _first_ordinal_refused(_moved_card(artifact, tmp_path), name) is wanted


def test_old_artifacts_read_only_the_verified_declared_card(old_format, tmp_path):
    """An artifact without the selector record reads the card's selectors from
    its manifest-declared effective configuration after checking its digest:
    intact, the uncapped reference serves its ordinals and the capped alias
    refuses; an edited or deleted card refuses the ordinals; a card moved to
    another declared path is read there (an undeclared effective.toml beside
    it is ignored)."""

    import json

    for name in ("cap", "reference"):
        request = json.loads(
            next((old_format[name] / "processes").glob("*/execution.json")).read_text()
        )["request"]
        assert "colour_selectors" not in request
    cap, reference = old_format["cap"], old_format["reference"]
    assert _first_ordinal_refused(cap, "uugg_swap")
    assert not _first_ordinal_refused(reference, "g u > g u")
    for edit in ("cap-byte", "deleted"):
        assert _first_ordinal_refused(
            _tampered(cap, tmp_path, EDITS[edit]), "uugg_swap"
        )
    for edit in ("reference", "deleted"):
        copy = _tampered(reference, tmp_path, EDITS[edit])
        assert _first_ordinal_refused(copy, "g u > g u"), edit
    assert _first_ordinal_refused(_moved_card(cap, tmp_path), "uugg_swap")
    assert not _first_ordinal_refused(_moved_card(reference, tmp_path), "g u > g u")


def test_selector_free_requests_keep_their_record():
    """A request without colour selectors records no ``colour_selectors``
    entry (selector-free artifacts keep their bytes)."""

    from pyamplicol.loops.v2.artifact import request_record
    from pyamplicol.loops.v2.assemble import SliceRequest

    request = SliceRequest("u u~ > g g", {"QCD": 2}, {"QCD": 4})
    assert "colour_selectors" not in request_record(request)
    selected = SliceRequest(
        "u u~ > g g", {"QCD": 2}, {"QCD": 4}, colour_selectors={"max_color_sectors": 1}
    )
    assert request_record(selected)["colour_selectors"] == {"max_color_sectors": 1}


def test_another_spelling_of_a_flow_id_selects_the_flow(stored, accuracy):
    """A mapped process's flow named in another valid spelling of the same
    flow (its lines in the stored block order, as a tree runtime of the
    stored process relabels them) selects the canonical flow; a word that
    is no flow stays refused."""

    from pyamplicol.api.errors import EvaluationError

    if accuracy != "lc":
        pytest.skip("colour flows exist at leading colour")
    runtime = _load(stored, "u d > u d")
    flows = [a.id for a in runtime.physics.born_anchored_color_components]
    assert flows == ["flow:3,1,4,2", "flow:3,2,4,1"]
    for canonical, other in (
        ("flow:3,1,4,2", "flow:4,2,3,1"),
        ("flow:3,2,4,1", "flow:4,1,3,2"),
    ):
        left = runtime.evaluate(POINTS, mu_r2=SCALES, color_flows=[other])
        right = runtime.evaluate(POINTS, mu_r2=SCALES, color_flows=[canonical])
        assert _numbers(left) == _numbers(right)
    with pytest.raises(EvaluationError):
        runtime.evaluate(POINTS, mu_r2=SCALES, color_flows=["flow:1,3,2,4"])
