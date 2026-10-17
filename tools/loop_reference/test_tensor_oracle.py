# SPDX-License-Identifier: 0BSD
"""Run explicitly with the licensed Community environment; no external providers."""

import json
from pathlib import Path

from tools.loop_reference.tensor_oracle import diphoton_r2_oracle, tensor_conformance


def test_physical_evanescent_and_gamma5_boundary():
    result = tensor_conformance()
    assert result["gamma5_generic_dimension"] == "unsimplified; BMHV is not certified"


def test_dependency_generated_r2_matches_reduction_fixture():
    result = diphoton_r2_oracle()
    fixture = json.loads(Path(__file__).with_name("diphoton_r2.json").read_text())
    assert fixture["numerator_epsilon_sectors"] == [
        result["projected_normalized_sum"],
        "0",
        "0",
    ]
    assert fixture["expected_laurent"] == {
        "finite": result["r2"],
        "single_pole": "0",
        "double_pole": "0",
    }
