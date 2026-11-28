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
    # As a dry run, the listing compiles no model: fill the card's cache.
    _cli("model", "inspect", "--card", str(card), "--json")
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
    _cli("model", "inspect", "--card", str(card), "--json")
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

    # As a dry run, the listing compiles no model: fill the cache first.
    _cli("model", "inspect", "--card", str(card), "--json")
    listed = refusal("model", "processes", "--card", str(card), "--json")
    generated = refusal("generate", "--card", str(card))
    assert not (tmp_path / "artifact").exists()
    # The same reason (generation names the process it was compiling).
    assert listed.split(": ", 1)[1] in generated


def _outcome(*arguments):
    """Exit code and, on success, the listed (or planned) names; on failure
    the reason of the last error line."""

    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli((*arguments, "--progress", "off"), stdout=stdout, stderr=stderr)
    if code == 0:
        if "--json" not in arguments:
            return code, None
        payload = json.loads(stdout.getvalue())
        rows = payload.get("entries", payload.get("concrete_processes"))
        return code, [row["name"] for row in rows]
    error = [line for line in stderr.getvalue().splitlines() if "ERROR" in line][-1]
    return code, error.split(": ", 1)[1]


@pytest.mark.parametrize(
    ("model", "mode"),
    [
        # The built-in SM without the model cache: the packaged preparation.
        ("cache = false", "recurrence"),
        ("cache = false", "on-the-fly"),
        ('source = "built-in-sm-heft"\ncache = false', "recurrence"),
        # A shipped UFO by name with a restriction (compiled first, below).
        (
            'source = "loop_sm"\nrestriction = "no_b_mass"\ncache_dir = "{cache}"',
            "compiled",
        ),
        # Without a compiled model: the dry run refuses, the listing prepares
        # the model as generation does (into the cache, or in memory).
        ('source = "loop_sm"\ncache_dir = "{empty}"', "compiled"),
        ('source = "loop_sm"\ncache = false', "compiled"),
    ],
    ids=[
        "builtin-nocache-recurrence",
        "builtin-nocache-on-the-fly",
        "heft-nocache",
        "ufo-restriction",
        "ufo-uncompiled",
        "ufo-nocache",
    ],
)
def test_the_listing_resolves_the_model_as_the_dry_run(
    tmp_path, model_cache, model, mode
):
    card = tmp_path / "card.toml"
    card.write_text(
        f"""
action = "generate"
[model]
{model.format(cache=model_cache, empty=tmp_path / "empty")}
[process]
entries = [{{ expression = "u u~ > g g", name = "p" }}]
[evaluator]
execution_mode = "{mode}"
[generation]
output = {json.dumps(str(tmp_path / "artifact"))}
"""
    )
    if "{cache}" in model:
        _cli("model", "inspect", "--card", str(card), "--json")
    planned = _outcome("generate", "--card", str(card), "--dry-run", "--json")
    listed = _outcome("model", "processes", "--card", str(card), "--json")
    cold = "empty" in model or 'loop_sm"\ncache = false' in model
    if cold:
        assert planned[0] != 0 and "dry-run does not compile" in planned[1]
        assert listed == (0, ["p"])
        # After a generation, the same (the cache filled, or still off).
        _cli("generate", "--card", str(card))
        assert _outcome("model", "processes", "--card", str(card), "--json") == (
            0,
            ["p"],
        )
    else:
        assert listed == planned
        assert listed[0] == 0


@pytest.mark.parametrize("mode", ["compiled", "recurrence"])
@pytest.mark.parametrize(
    ("expression", "selection", "accuracy", "orders", "listed"),
    [
        # A leading-colour sector without a tree amplitude, and one with;
        # a cap that keeps only the former.
        ("c d > u s", "selected_color_sector_ids = [0]", "lc", True, False),
        ("c d > u s", "selected_color_sector_ids = [1]", "lc", True, True),
        ("c d > u s", "max_color_sectors = 1", "lc", True, False),
        # A helicity configuration whose amplitude vanishes.
        (
            "e+ e- > mu+ mu-",
            "selected_source_helicities = { 1 = 1, 2 = 1, 3 = 1, 4 = 1 }",
            "full",
            False,
            False,
        ),
    ],
    ids=[
        "sector-without-amplitude",
        "sector-with-amplitude",
        "cap-without-amplitude",
        "all-plus-helicities",
    ],
)
def test_a_fixed_selection_is_checked_on_what_it_selects(
    tmp_path, mode, expression, selection, accuracy, orders, listed
):
    card = tmp_path / "card.toml"
    card.write_text(
        f"""
action = "generate"
[process]
entries = [{{ expression = "{expression}", name = "sample" }}]
{selection}
{'coupling_order_policy = "explicit"' if orders else ""}
{"max_coupling_orders = { QCD = 0, QED = 2 }" if orders else ""}
[color]
accuracy = "{accuracy}"
[evaluator]
execution_mode = "{mode}"
[generation]
output = {json.dumps(str(tmp_path / "artifact"))}
"""
    )
    code, result = _outcome("model", "processes", "--card", str(card), "--json")
    if listed:
        assert (code, result) == (0, ["sample"])
    else:
        # The mode's generation refuses with the same reason (its own).
        assert code != 0
        generated = _outcome("generate", "--card", str(card))
        # Long reasons are shortened in the error line: their beginning.
        assert generated[0] != 0 and result[:80] in generated[1]


@pytest.mark.parametrize("mode", ["recurrence", "compiled"])
def test_a_helicity_selection_follows_the_requested_mode(tmp_path, mode):
    # Built-in HEFT z z > g g with leg 1 at helicity +1: recurrence serves it
    # (a nonzero value), compiled construction refuses it; the listing says
    # what the requested mode does.
    card = tmp_path / "card.toml"
    card.write_text(
        f"""
action = "generate"
[model]
source = "built-in-sm-heft"
[process]
entries = [{{ expression = "z z > g g", name = "sample" }}]
coupling_order_policy = "explicit"
max_coupling_orders = {{ QCD = 0, QED = 1, HIG = 1 }}
selected_source_helicities = {{ 1 = 1 }}
[color]
accuracy = "full"
[evaluator]
execution_mode = "{mode}"
[generation]
output = {json.dumps(str(tmp_path / "artifact"))}
"""
    )
    listed = _outcome("model", "processes", "--card", str(card), "--json")
    generated = _outcome("generate", "--card", str(card))
    if mode == "recurrence":
        assert generated[0] == 0
        manifest = json.loads((tmp_path / "artifact" / "artifact.json").read_text())
        assert listed == (0, [row["id"] for row in manifest["processes"]])
    else:
        assert listed[0] != 0 and generated[0] != 0
        assert listed[1][:80] in generated[1]


_LOOP_DECLARATION = """
[loop]
r2_strategy = "model"
[loop.model]
loop_coupling_orders = ["QCD"]
uv_complete = true
model_r2_complete = true
[loop.model.scheme]
dimensional_regularization = "HV"
external_states = "physical-four-dimensional"
gamma5 = "source-UFO-four-dimensional-prescription"
renormalization = "source-UFO mass-dependent decoupling"
mass_scheme = "real-on-shell"
finite_restoration = "source-UFO-local-rules"
model_convention = "loop_sm lhv=1 supplied QCD rules"
"""


@pytest.mark.parametrize("cache", ["cold", "off"])
def test_a_one_loop_listing_prepares_its_model_as_one_loop_generation(tmp_path, cache):
    # loop_sm with a UFO function of its own (sqr), which one-loop generation
    # admits (the tree model gate does not): listed before and after a
    # generation, with a cold cache and with caching off, as stored.
    import shutil
    from pathlib import Path

    import pyamplicol

    model = tmp_path / "sm"
    shutil.copytree(
        Path(pyamplicol.__file__).parent / "assets" / "models" / "ufo" / "loop_sm",
        model,
    )
    with (model / "function_library.py").open("a") as library:
        library.write(
            "sqr = Function(name = 'sqr', arguments = ('z',), expression = 'z*z')\n"
        )
    card = tmp_path / "card.toml"
    card.write_text(
        f"""
action = "generate"
[model]
source = {json.dumps(str(model))}
restriction = "no_b_mass"
{"cache = false" if cache == "off" else ""}
cache_dir = {json.dumps(str(tmp_path / "cache"))}
[process]
entries = [{{ expression = "u g > u g", name = "up" }},
           {{ expression = "c g > c g", name = "charm" }}]
loop_coupling_orders = ["QCD"]
{_LOOP_DECLARATION}
[loop.preparation]
fixed_parameters = {{ WT = "0", WZ = "0", WW = "0", WH = "0" }}
[generation]
output = {json.dumps(str(tmp_path / "artifact"))}
"""
    )
    before = _outcome("model", "processes", "--card", str(card), "--json")
    _cli("generate", "--card", str(card))
    manifest = json.loads((tmp_path / "artifact" / "artifact.json").read_text())
    stored = sorted(row["id"] for row in manifest["processes"])
    after = _outcome("model", "processes", "--card", str(card), "--json")
    assert before[0] == 0 and sorted(before[1]) == stored
    assert after == before


@pytest.mark.parametrize("mode", ["recurrence", "on-the-fly"])
def test_a_listing_keeps_the_dry_runs_own_model_refusal(tmp_path, mode):
    # The packaged HEFT model takes no restriction in these modes: the
    # listing refuses with the dry run's own reason, not another one.
    card = tmp_path / "card.toml"
    card.write_text(
        f"""
action = "generate"
[model]
source = "built-in-sm-heft"
restriction = "no_b_mass"
cache = false
[process]
entries = [{{ expression = "u u~ > g g", name = "up" }}]
[evaluator]
execution_mode = "{mode}"
[generation]
output = {json.dumps(str(tmp_path / "artifact"))}
"""
    )
    planned = _outcome("generate", "--card", str(card), "--dry-run", "--json")
    listed = _outcome("model", "processes", "--card", str(card), "--json")
    assert planned[0] != 0 and "uses the default restriction" in planned[1]
    assert listed == planned
