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
    SCALES,
    _generate,
    mapped,  # noqa: F401  (the mapping artifact fixture)
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
