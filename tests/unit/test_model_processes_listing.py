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


def _artifact_groups(artifact):
    """The stored processes and the served ones (name, process, served by)
    of a generated artifact."""

    manifest = json.loads((artifact / "artifact.json").read_text())
    stored = [(row["id"], row["expression"]) for row in manifest["processes"]]
    groups = json.loads((artifact / "process-groups.json").read_text())["groups"]
    served = sorted(
        (member["process_id"], member["process"], group["representative"]["process_id"])
        for group in groups
        for member in group["members"]
        if not member["generated"]
    )
    return stored, served


def _listed_groups(listing):
    stored = [(row["name"], row["process"]) for row in listing["entries"]]
    served = sorted(
        (row["name"], row["process"], row["served_by"]) for row in listing["served"]
    )
    assert listing["n_stored"] == len(stored) == listing["n_entries"]
    assert listing["n_served"] == len(served)
    assert listing["n_addressable"] == len(stored) + len(served)
    for row in listing["entries"]:
        assert row["serves"] == [
            name for name, _process, by in served if by == row["name"]
        ]
    return stored, served


@pytest.mark.parametrize("route", ["one-loop", "tree"])
def test_a_grouped_listing_says_what_is_stored_and_what_is_served(
    tmp_path, model_cache, route
):
    # Flavour grouping: d d > d d stored, s s > s s served through it under
    # two IDs (the three-request example), at one loop (exact grouping) and
    # in compiled tree generation (flavour-blind).
    loop = route == "one-loop"
    card = _card(
        tmp_path,
        model_cache,
        "d d > d d",
        loop=loop,
        extra="flavor_blind = true"
        + ("" if loop else '\n[evaluator]\nexecution_mode = "compiled"'),
    )
    text = card.read_text().replace(
        '[{ expression = "d d > d d", name = "req" }]',
        '[{ expression = "d d > d d", name = "down" }, '
        '{ expression = "s s > s s", name = "strange1" }, '
        '{ expression = "s s > s s", name = "strange2" }]',
    )
    card.write_text(text)
    listing = _cli("model", "processes", "--card", str(card), "--json")
    listed = _listed_groups(listing)
    _cli("generate", "--card", str(card))
    assert listed == _artifact_groups(tmp_path / "artifact")
    assert listed[0] == [("down", "d d > d d")]
    assert [name for name, _p, _by in listed[1]] == ["strange1", "strange2"]


@pytest.mark.parametrize(
    ("model", "extra"),
    [
        # A fixed colour sector at full colour, and an LC sector the process
        # does not have.
        (None, 'selected_color_sector_ids = [0]\n[color]\naccuracy = "full"'),
        (None, 'selected_color_sector_ids = [6]\n[color]\naccuracy = "lc"'),
        # The shipped HEFT: a closed gluon trace times an open colour line.
        (
            "built-in-sm-heft",
            'coupling_order_policy = "explicit"\n'
            "max_coupling_orders = { QCD = 0, QED = 1, HIG = 1 }",
        ),
    ],
    ids=["fixed-sector-full", "absent-lc-sector", "heft-closed-trace"],
)
def test_the_listing_refuses_what_tree_generation_refuses(tmp_path, model, extra):
    card = tmp_path / "card.toml"
    card.write_text(
        f"""
action = "generate"
{f'[model]{chr(10)}source = "{model}"' if model else ""}
[process]
entries = [{{ expression = "g g > t t~", name = "sample" }}]
{extra}
[evaluator]
execution_mode = "compiled"
[generation]
output = {json.dumps(str(tmp_path / "artifact"))}
"""
    )

    def refusal(*arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        code = run_cli((*arguments, "--progress", "off"), stdout=stdout, stderr=stderr)
        assert code != 0, stdout.getvalue()
        return [line for line in stderr.getvalue().splitlines() if "ERROR" in line][-1]

    listed = refusal("model", "processes", "--card", str(card), "--json")
    generated = refusal("generate", "--card", str(card))
    assert not (tmp_path / "artifact").exists()
    # The same reason (generation names the process it was compiling).
    assert listed.split(": ", 1)[1] in generated
