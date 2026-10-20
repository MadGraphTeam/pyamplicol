# SPDX-License-Identifier: 0BSD
"""Focused checks of the MG5 quadruple-precision model-function repair."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import references  # noqa: E402

SNIPPET = """      DOUBLE COMPLEX FUNCTION REGLOG(ARG_IN)
        ARG=DCMPLX(DBLE(ARG),0.0D0)
      END
        COMPLEX*32 FUNCTION MP_REGLOG(ARG_IN)
        PARAMETER (TWOPII=2.0E0_16
     $   *3.14169258478796109557151794433593750E0_16*(0.0E0_16
     $   ,1.0E0_16))
          ARG=CMPLX(REAL(ARG,KIND=16),0.0E0_16)
          ARG=CMPLX(0.0E0_16,IMAGPART(ARG))
          MP_RECMS=CMPLX(REAL(EXPR),KIND=16)
          X = (MP_CONDIF(CMPLX(MP__CMS,KIND=16).NE.(0.0E0_16
     $     ,0.0E0_16),CMPLX(CONJG(CMPLX(MP__Z
     $     ,KIND=16)),KIND=16)))
        END
"""


def test_repair_adds_kind_only_where_missing_and_fixes_pi():
    fixed, repairs = references.fix_qp_model_functions(SNIPPET)
    assert "ARG=CMPLX(REAL(ARG,KIND=16),0.0E0_16,KIND=16)" in fixed
    assert "ARG=CMPLX(0.0E0_16,IMAGPART(ARG),KIND=16)" in fixed
    assert "MP_RECMS=CMPLX(REAL(EXPR),KIND=16)\n" in fixed
    assert "DCMPLX(DBLE(ARG),0.0D0)" in fixed  # double precision untouched
    assert ",KIND=16)),KIND=16)))" in fixed  # continued call already has KIND
    assert references.QP_PI_TYPO not in fixed and references.QP_PI in fixed
    assert repairs[0] == "added KIND=16 to 2 CMPLX calls in MP_ functions"
    assert references.fix_qp_model_functions(fixed) == (fixed, [])
