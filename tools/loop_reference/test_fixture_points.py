# SPDX-License-Identifier: 0BSD
"""The provider toolkit's decimal top-pair points (``--fixture
tools/loop_reference/top_pair_qcd.json``) are exactly on shell."""

import json
from decimal import Decimal, localcontext
from pathlib import Path


def test_original_decimal_fixture_is_exactly_on_shell():
    path = Path(__file__).resolve().parent / "top_pair_qcd.json"
    points = json.loads(path.read_text(), parse_float=str, parse_int=str)["points"]
    assert points
    with localcontext() as context:
        context.prec = 100
        for point in points:
            for index, leg in enumerate(point):
                p = [Decimal(component) for component in leg]
                assert p[0] ** 2 - sum(x * x for x in p[1:]) == (
                    0 if index < 2 else Decimal(173) ** 2
                )
            for component in range(4):
                assert Decimal(point[0][component]) + Decimal(
                    point[1][component]
                ) == Decimal(point[2][component]) + Decimal(point[3][component])
