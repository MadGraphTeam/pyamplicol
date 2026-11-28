# SPDX-License-Identifier: 0BSD
"""``pyamplicol model processes`` lists exactly the processes a generation
of the same request stores: same filters, same order, same names, at tree
level and at one loop, on the built-in SM and on a UFO."""

import io
import json

import pytest

from pyamplicol.cli import run_cli

pytestmark = pytest.mark.loop_physics


@pytest.fixture(scope="module")
def model_cache(tmp_path_factory):
    return tmp_path_factory.mktemp("listing-models")


def _cli(*arguments):
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli((*arguments, "--progress", "off"), stdout=stdout, stderr=stderr)
    assert code == 0, stderr.getvalue()
    return json.loads(stdout.getvalue()) if "--json" in arguments else None


def _card(tmp_path, cache, expression, *, model=True, loop=False, extra=""):
    card = tmp_path / "card.toml"
    card.write_text(
        f"""
action = "generate"
{
            f'''[model]
source = "loop_sm"
restriction = "no_b_mass"
cache_dir = {json.dumps(str(cache))}'''
            if model
            else ""
        }
[process]
entries = [{{ expression = {json.dumps(expression)}, name = "req" }}]
{'loop_coupling_orders = ["QCD"]' if loop else ""}
{extra}
[loop.preparation]
fixed_parameters = {{ WT = "0", WZ = "0", WW = "0", WH = "0" }}
[generation]
output = {json.dumps(str(tmp_path / "artifact"))}
"""
    )
    return card


def _listed(card):
    listing = _cli("model", "processes", "--card", str(card), "--json")
    return listing, [(row["name"], row["process"]) for row in listing["entries"]]


def _planned(card):
    plan = _cli("generate", "--card", str(card), "--dry-run", "--json")
    assert plan["unsupported_features"] == []
    return [(row["name"], row["expression"]) for row in plan["concrete_processes"]]


def _stored(card, *extra):
    _cli("generate", "--card", str(card), *extra)
    manifest = json.loads((card.parent / "artifact" / "artifact.json").read_text())
    return [(row["id"], row["expression"]) for row in manifest["processes"]]


def test_the_builtin_listing_is_the_builtin_generation_expansion(tmp_path, model_cache):
    card = _card(tmp_path, model_cache, "p p > j j", model=False)
    listing, listed = _listed(card)
    assert listing["route"] == "tree"
    # The built-in SM conserves charge and fermion families: 96 subprocesses,
    # as its generation (the compiled catalogue listed 4356, e.g. b b > b b~).
    assert listed == _planned(card)
    assert len(listed) == 96
    assert "b b > b b~" not in {process for _name, process in listed}


def test_the_one_loop_listing_is_the_one_loop_plan(tmp_path, model_cache):
    card = _card(
        tmp_path, model_cache, "p p > j j", loop=True, extra="max_quark_lines = 1"
    )
    listing, listed = _listed(card)
    assert listing["route"] == "one-loop"
    assert listed == _planned(card)
    assert len(listed) == 21


def test_the_one_loop_listing_leaves_out_the_skipped_members(tmp_path, model_cache):
    card = _card(tmp_path, model_cache, "p p > e+ e-", loop=True)
    listing, listed = _listed(card)
    assert listed == _planned(card)
    assert "G G > e+ e-" not in {process for _name, process in listed}
    assert [row["process"] for row in listing["skipped"]] == ["G G > e+ e-"]


def test_the_tree_listing_is_what_tree_generation_stores(tmp_path, model_cache):
    # g g > e+ e- has no tree-level diagram: tree generation skips it (the
    # tree dry run still lists it); u u~ > j j with max_quark_lines = 1 keeps
    # u u~ > g g only.
    for expression, extra, absent in (
        ("p p > e+ e-", "", "G G > e+ e-"),
        ("u u~ > j j", "max_quark_lines = 1", "u u~ > u u~"),
    ):
        root = tmp_path / expression.replace(" ", "").replace(">", "_")
        root.mkdir()
        card = _card(
            root,
            model_cache,
            expression,
            extra=extra + '\n[evaluator]\nexecution_mode = "compiled"',
        )
        listing, listed = _listed(card)
        assert listing["route"] == "tree"
        assert listed == _stored(card)
        assert absent not in {process for _name, process in listed}
