# SPDX-License-Identifier: 0BSD
"""The QED-order-weighted normalization contract of global-coupling models.

A model whose stage evaluators carry local vertex couplings only (the built-in
SM) restores g_s and e with one global factor (4 pi alpha_s)^q
(8 pi alpha_ew)^e. A Born with amplitudes of several coupling orders instead
takes the global factor (4 pi alpha_s)^N, N the common total order of its
amplitudes, and weighs every QED order of an amplitude by
rho = sqrt((8 pi alpha_ew) / (4 pi alpha_s)) = sqrt(2 alpha_ew / alpha_s) at the
current run-time inputs (``generation.born_orders``). This module holds the
names both generation and the runtimes read.
"""

from __future__ import annotations

from collections.abc import Mapping

#: The run-time inputs of the global coupling factor.
NORMALIZATION_ALPHA_S = "normalization.alpha_s_me_check"
NORMALIZATION_ALPHA_EW = "normalization.alpha_ew"

#: The largest rho^2 = 2 alpha_ew / alpha_s the runtimes accept (2^52): beyond
#: it the binary64 weights and global factor leave the floating-point range.
QED_ORDER_WEIGHT_MAX_SQUARED = 2**52

#: ``coupling_policy`` of a QED-order-weighted normalization payload. Every
#: electroweak vertex coupling slot carries rho (compiled and eager lanes);
#: every closure of an amplitude component with QED order e carries rho^e
#: (recurrence and on-the-fly lanes).
QED_ORDER_WEIGHTED_COUPLING_POLICY = (
    "stage evaluators include local vertex couplings; each QED order of an "
    "amplitude is weighted by sqrt(8 pi alpha_ew / (4 pi alpha_s))"
)

#: The recurrence process-normalization convention of such a payload; its
#: plans intern closure factors per QED order.
QED_ORDER_WEIGHTED_NORMALIZATION_CONVENTION = (
    "runtime-normalization-extension-qed-order-weights-v1"
)
DEFAULT_NORMALIZATION_CONVENTION = "runtime-normalization-extension-v1"


def is_qed_order_weighted(normalization: Mapping[str, object] | None) -> bool:
    """Whether a normalization payload weighs its amplitude orders at run time."""

    return bool(normalization) and (
        normalization.get("coupling_policy") == QED_ORDER_WEIGHTED_COUPLING_POLICY
    )


__all__ = [
    "DEFAULT_NORMALIZATION_CONVENTION",
    "NORMALIZATION_ALPHA_EW",
    "NORMALIZATION_ALPHA_S",
    "QED_ORDER_WEIGHTED_COUPLING_POLICY",
    "QED_ORDER_WEIGHTED_NORMALIZATION_CONVENTION",
    "QED_ORDER_WEIGHT_MAX_SQUARED",
    "is_qed_order_weighted",
]
