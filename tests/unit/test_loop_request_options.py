# SPDX-License-Identifier: 0BSD
"""Request options of one-loop generation on the shipped ``loop_sm``: each
option means what it means on the tree route, in the dry run and in
generation alike (real generation, small requests)."""

import io
import json

import numpy as np
import pytest

from pyamplicol.api import Generator, ProcessRequest, ProcessSet, Runtime
from pyamplicol.api.errors import EvaluationError, GenerationError
from pyamplicol.cli import run_cli
from pyamplicol.config import resolve_config

pytestmark = pytest.mark.loop_physics


@pytest.fixture(scope="module")
def model_cache(tmp_path_factory):
    return tmp_path_factory.mktemp("loop-request-options-models")


def _card(tmp_path, cache, *, expression, name, output="artifact", extra=""):
    card = tmp_path / f"{name}.toml"
    card.write_text(
        f"""
action = "generate"
[model]
source = "loop_sm"
restriction = "no_b_mass"
cache_dir = {json.dumps(str(cache))}
[process]
entries = [{{ expression = {json.dumps(expression)}, name = {json.dumps(name)} }}]
loop_coupling_orders = ["QCD"]
{extra}
[loop.preparation]
fixed_parameters = {{ WT = "0", WZ = "0", WW = "0", WH = "0" }}
[generation]
output = {json.dumps(str(tmp_path / output))}
"""
    )
    return card


def _cli(*arguments):
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli((*arguments, "--progress", "off"), stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def _compiled(card):
    """The shipped model compiled into the card's cache (a dry run never
    compiles one)."""

    code, _, stderr = _cli(
        "model", "processes", "u u~ > g g", "--card", str(card), "--json"
    )
    assert code == 0, stderr


def _plan(card, *extra):
    code, stdout, stderr = _cli(
        "generate", "--card", str(card), "--dry-run", "--json", *extra
    )
    assert code == 0, stderr
    return json.loads(stdout)


def _manifest(output):
    return json.loads((output / "artifact.json").read_text())


def _points():
    """Two massless 2 -> 2 points at sqrt(s) = 1000 GeV."""

    energy = 500.0
    points = []
    for cos, phi in ((0.3, 0.7), (-0.6, 2.1)):
        sin = (1.0 - cos * cos) ** 0.5
        k = [energy * sin * np.cos(phi), energy * sin * np.sin(phi), energy * cos]
        points.append(
            [
                [energy, 0.0, 0.0, energy],
                [energy, 0.0, 0.0, -energy],
                [energy, *k],
                [energy, *(-x for x in k)],
            ]
        )
    return points


def _values(artifact, process):
    """Born and Laurent values of ``process`` at ``_points`` (exact repr)."""

    result = Runtime.load(artifact, process=process).evaluate(
        _points(), mu_r2=[8315.0, 8315.0]
    )
    return repr((result.born_values, result.values))


# F1: process.max_quark_lines ------------------------------------------------


def test_max_quark_lines_cuts_the_one_loop_plan_as_the_tree_route(
    tmp_path, model_cache
):
    card = _card(
        tmp_path,
        model_cache,
        expression="p p > j j",
        name="ppjj",
        extra="max_quark_lines = 1",
    )
    _compiled(card)
    plan = _plan(card)
    assert plan["unsupported_features"] == []
    rows = plan["estimated_coverage"]["processes"]
    # q q~ > g g, q g > q g, q~ g > q~ g, g g > q q~ (five flavours) and
    # g g > g g: the subprocesses with at most one quark line.
    assert len(rows) == 21
    assert len(plan["concrete_processes"]) == 21
    assert {row["process"] for row in rows} >= {"G G > G G", "u u~ > G G"}
    # Names are those of the uncut expansion (as the tree route's).
    assert {row["key"] for row in rows} >= {"ppjj_108", "ppjj_39", "ppjj_7"}
    uncut = _plan(card, "--max-quark-lines", "null")
    assert len(uncut["estimated_coverage"]["processes"]) == 108


def test_max_quark_lines_that_empties_a_request_is_refused_naming_it(
    tmp_path, model_cache
):
    card = _card(
        tmp_path,
        model_cache,
        expression="u d > u d",
        name="ud",
        extra="max_quark_lines = 1",
    )
    _compiled(card)
    plan = _plan(card)
    (blocker,) = plan["unsupported_features"]
    assert "process.max_quark_lines = 1" in blocker
    assert plan["estimated_coverage"]["processes"] == []
    assert plan["concrete_processes"] == []
    with pytest.raises(GenerationError, match=r"process\.max_quark_lines = 1") as error:
        Generator(resolve_config(card)).generate(
            ProcessRequest.parse("u d > u d", name="ud"), tmp_path / "artifact"
        )
    assert error.value.key == "request-filter"
    assert error.value.settings == ("process.max_quark_lines",)
    assert not (tmp_path / "artifact").exists()


def test_max_quark_lines_generation_keeps_the_values_of_the_kept_processes(
    tmp_path, model_cache
):
    card = _card(
        tmp_path,
        model_cache,
        expression="u u~ > j j",
        name="uxjj",
        extra="max_quark_lines = 1",
    )
    code, _, stderr = _cli("generate", "--card", str(card))
    assert code == 0, stderr
    stored = [
        (row["id"], row["expression"])
        for row in _manifest(tmp_path / "artifact")["processes"]
    ]
    assert stored == [("uxjj_6", "u u~ > G G")]
    single = _card(
        tmp_path, model_cache, expression="u u~ > g g", name="uugg", output="single"
    )
    code, _, stderr = _cli("generate", "--card", str(single))
    assert code == 0, stderr
    assert _values(tmp_path / "artifact", "uxjj_6") == _values(
        tmp_path / "single", "uugg"
    )


@pytest.mark.parametrize(
    ("model", "expected"),
    [(("--model", "loop_sm", "--restriction", "no_b_mass"), 21), ((), None)],
)
def test_model_processes_applies_max_quark_lines(model, expected):
    def listed(*extra):
        code, stdout, stderr = _cli(
            "model", "processes", "p p > j j", *model, "--json", *extra
        )
        assert code == 0, stderr
        return json.loads(stdout)

    full = listed()
    cut = listed("--max-quark-lines", "1")
    lines = {
        entry["key"]: entry["ir"]["color_endpoints"]["pair_count"]
        for entry in full["entries"]
    }
    kept = {key for key, count in lines.items() if count <= 1}
    assert {entry["key"] for entry in cut["entries"]} == kept
    assert cut["n_entries"] == len(kept) < full["n_entries"]
    assert cut["max_quark_lines"] == 1
    assert cut["n_dropped_by_max_quark_lines"] == full["n_entries"] - len(kept)
    if expected is not None:
        assert len(kept) == expected


# F2: appending to a one-loop artifact ----------------------------------------


def _digest(artifact):
    import hashlib

    digest = hashlib.sha256()
    for path in sorted(artifact.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(artifact)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.fixture
def one_loop_artifact(tmp_path, model_cache):
    card = _card(tmp_path, model_cache, expression="u u~ > g g", name="uugg")
    code, _, stderr = _cli("generate", "--card", str(card))
    assert code == 0, stderr
    return card, tmp_path / "artifact"


def test_cli_append_of_a_compatible_one_loop_request_succeeds(
    one_loop_artifact, tmp_path, model_cache
):
    card, artifact = one_loop_artifact
    # The CLI records mode = "append" and the new entry; neither shapes the
    # stored processes.
    code, _, stderr = _cli(
        "generate",
        "--card",
        str(card),
        "--process",
        "d d~ > g g",
        "--name",
        "ddgg",
        "--mode",
        "append",
    )
    assert code == 0, stderr
    stored = [row["id"] for row in _manifest(artifact)["processes"]]
    assert stored == ["uugg", "ddgg"]
    fresh = _card(
        tmp_path, model_cache, expression="d d~ > g g", name="ddgg", output="fresh"
    )
    code, _, stderr = _cli("generate", "--card", str(fresh))
    assert code == 0, stderr
    assert _values(artifact, "ddgg") == _values(tmp_path / "fresh", "ddgg")


def test_python_append_of_another_process_count_succeeds(one_loop_artifact):

    card, artifact = one_loop_artifact
    # generation.workers = "auto" resolves to the appended request's process
    # count (2 here, 1 in the artifact).
    Generator(resolve_config(card)).generate(
        ProcessSet(
            (
                ProcessRequest.parse("s s~ > g g", name="ssgg"),
                ProcessRequest.parse("c c~ > g g", name="ccgg"),
            )
        ),
        artifact,
        mode="append",
    )
    stored = [row["id"] for row in _manifest(artifact)["processes"]]
    assert stored == ["uugg", "ssgg", "ccgg"]
    for process in stored:
        assert "nan" not in _values(artifact, process)


def test_incompatible_append_names_the_setting_before_generating(
    one_loop_artifact, monkeypatch
):
    import pyamplicol.loops.v2.artifact as loop_artifact

    card, artifact = one_loop_artifact
    before = _digest(artifact)

    def forbidden(*args, **kwargs):
        raise AssertionError("an incompatible append must not generate")

    monkeypatch.setattr(loop_artifact, "generate_process", forbidden)
    configuration = resolve_config(card, overrides=("color.accuracy=lc",))
    with pytest.raises(GenerationError, match=r"setting color\.accuracy") as error:
        Generator(configuration).generate(
            ProcessRequest.parse("d d~ > g g", name="ddgg"), artifact, mode="append"
        )
    assert '"lc" in this request but "full" in the artifact' in str(error.value)
    assert _digest(artifact) == before


# F9: refusals before any process is generated --------------------------------


def test_a_refused_entry_is_refused_before_any_entry_is_generated(
    tmp_path, model_cache, monkeypatch
):
    import pyamplicol.loops.v2.artifact as loop_artifact

    # The second entry tags a final-state photon in a request with the QED
    # correction on a model without the alpha(0) conversion counterterm.
    card = tmp_path / "photons.toml"
    card.write_text(
        f"""
action = "generate"
[model]
source = "loop_qcd_qed_sm"
cache_dir = {json.dumps(str(model_cache))}
[process]
entries = [{{ expression = "a u > u g", name = "first" }},
           {{ expression = "u u~ > a g", name = "second" }}]
loop_coupling_orders = ["QCD", "QED"]
coupling_order_policy = "explicit"
max_coupling_orders = {{ QCD = 2, QED = 2 }}
[loop.preparation]
fixed_parameters = {{ WT = "0", WZ = "0", WW = "0", WH = "0" }}
[generation]
output = {json.dumps(str(tmp_path / "artifact"))}
"""
    )
    _compiled(card)
    plan = _plan(card)
    (blocker,) = plan["unsupported_features"]
    assert blocker.startswith("external-photon-scheme: 'u u~ > A G'")
    # Every entry's members or none: none, as generation refuses them all.
    assert plan["estimated_coverage"]["processes"] == []
    assert plan["estimated_coverage"]["process_count"] == 0
    assert plan["concrete_processes"] == []

    def forbidden(*args, **kwargs):
        raise AssertionError("a refused request must not generate any process")

    monkeypatch.setattr(loop_artifact, "generate_process", forbidden)
    with pytest.raises(GenerationError, match="external-photon-scheme") as error:
        Generator(resolve_config(card)).generate(
            ProcessSet(
                (
                    ProcessRequest.parse("a u > u g", name="first"),
                    ProcessRequest.parse("u u~ > a g", name="second"),
                )
            ),
            tmp_path / "artifact",
        )
    assert error.value.key == "external-photon-scheme"
    assert not (tmp_path / "artifact").exists()


# F8: external particle names -------------------------------------------------


def test_one_loop_runtimes_name_external_particles_by_the_model(one_loop_artifact):
    _, artifact = one_loop_artifact
    for process, names in (
        ("uugg", ["u", "u~", "G", "G"]),
        ("u u~ > g g", ["u", "u~", "G", "G"]),
        # A side permutation of the stored process: its own leg order.
        ("u~ u > g g", ["u~", "u", "G", "G"]),
    ):
        particles = Runtime.load(artifact, process=process).physics.external_particles
        assert [particle.name for particle in particles] == names
        assert [particle.pdg_id for particle in particles][:2] == (
            [2, -2] if names[0] == "u" else [-2, 2]
        )


# F5: overlapping requests ----------------------------------------------------


def test_a_twice_stored_process_is_ambiguous_in_every_spelling(tmp_path, model_cache):
    card = _card(tmp_path, model_cache, expression="u u~ > g g", name="uugg")
    artifact = tmp_path / "artifact"
    # Overlapping requests store the common process under each request's
    # id, as the tree route does.
    Generator(resolve_config(card)).generate(
        ProcessSet(
            (
                ProcessRequest.parse("u u~ > g g", name="uugg"),
                ProcessRequest.parse("u u~ > g g", name="again"),
            )
        ),
        artifact,
    )
    for spelling in ("u u~ > g g", "u u~ > G G", "U U~ > G G", "u~ u > G G"):
        with pytest.raises(EvaluationError, match="ambiguous") as error:
            Runtime.load(artifact, process=spelling)
        assert "again, uugg" in str(error.value)
    assert _values(artifact, "again") == _values(artifact, "uugg")


# F7: a dry run on a model it cannot load -------------------------------------


def test_one_loop_dry_run_on_an_uncompiled_model_fails_as_the_tree_one(tmp_path):
    from pyamplicol.api.errors import ModelError

    empty = tmp_path / "empty-cache"
    card = _card(tmp_path, empty, expression="u u~ > g g", name="uugg")
    tree = _card(tmp_path, empty, expression="u u~ > g g", name="tree")
    tree.write_text(tree.read_text().replace('loop_coupling_orders = ["QCD"]', ""))
    for request in (card, tree):
        code, stdout, stderr = _cli(
            "generate", "--card", str(request), "--dry-run", "--json"
        )
        assert code == 2, stdout
        assert "dry-run does not compile external model sources" in stderr
    with pytest.raises(ModelError, match="dry-run does not compile"):
        Generator(resolve_config(card)).plan(
            ProcessRequest.parse("u u~ > g g", name="uugg")
        )
    assert not empty.exists() or not any(empty.rglob("*.json"))


@pytest.mark.parametrize(
    ("policy", "qed", "key"),
    [
        ("auto", 1, "no-loop-amplitude"),
        ("skip", 1, "loop-induced"),
        ("skip", 2, "loop-induced"),
    ],
)
def test_a_plan_wide_refusal_lists_no_process_in_any_field(
    tmp_path, model_cache, policy, qed, key
):
    # The cut leaves g g > a a, which has no Born (and at QED <= 1 no loop
    # amplitude): the request is refused, so no field lists a process.
    card = _card(
        tmp_path,
        model_cache,
        expression="x y > a a",
        name="sample",
        extra=f"""multiparticles = {{ x = ["g", "u"], y = ["g", "u~"] }}
max_quark_lines = 0
loop_induced = "{policy}"
coupling_order_policy = "explicit"
max_coupling_orders = {{ QCD = 2, QED = {qed} }}""",
    )
    _compiled(card)
    plan = _plan(card)
    (blocker,) = plan["unsupported_features"]
    assert blocker.startswith(f"{key}: ")
    coverage = plan["estimated_coverage"]
    assert plan["concrete_processes"] == []
    assert coverage["processes"] == []
    assert coverage["process_count"] == 0
    assert coverage["skipped_members"] == []
    assert coverage["runtime_capabilities"] == []
    code, _, stderr = _cli("generate", "--card", str(card))
    assert code != 0
    assert key in stderr
    assert not (tmp_path / "artifact").exists()


# Public process IDs through an append (review r2) ----------------------------


def _born(artifact, process):
    result = Runtime.load(artifact, process=process).evaluate(
        _points(), mu_r2=[8315.0, 8315.0]
    )
    return [float(value[0]) for value in result.born_values]


@pytest.fixture(scope="module")
def grouped_artifact(tmp_path_factory, model_cache):
    """Exact flavour grouping: ``d d > d d`` stored as ``up``, ``s s > s s``
    served through it as ``first`` and as ``second``."""

    root = tmp_path_factory.mktemp("grouped")
    card = _card(
        root,
        model_cache,
        expression="d d > d d",
        name="up",
        extra="flavor_blind = true",
    )
    Generator(resolve_config(card)).generate(
        ProcessSet(
            (
                ProcessRequest.parse("d d > d d", name="up"),
                ProcessRequest.parse("s s > s s", name="first"),
                ProcessRequest.parse("s s > s s", name="second"),
            )
        ),
        root / "artifact",
    )
    assert [row["id"] for row in _manifest(root / "artifact")["processes"]] == ["up"]
    return card, root / "artifact"


def _copy(artifact, tmp_path):
    import shutil

    target = tmp_path / "copy"
    shutil.copytree(artifact, target)
    return target


def test_an_append_cannot_take_a_served_member_id_for_another_process(
    grouped_artifact, tmp_path
):
    from pyamplicol.api.errors import ProcessIdCollisionError

    card, stored = grouped_artifact
    artifact = _copy(stored, tmp_path)
    before, born = _digest(artifact), _born(artifact, "first")
    assert born[0] == 5.540289417365958
    with pytest.raises(ProcessIdCollisionError, match="'first'"):
        Generator(resolve_config(card)).generate(
            ProcessRequest.parse("u u~ > g g", name="first"), artifact, mode="append"
        )
    assert _digest(artifact) == before
    assert _born(artifact, "first") == born


def test_an_append_may_promote_a_served_member_of_the_same_process(
    grouped_artifact, tmp_path
):
    card, stored = grouped_artifact
    artifact = _copy(stored, tmp_path)
    served = _values(artifact, "first")
    Generator(resolve_config(card)).generate(
        ProcessRequest.parse("s s > s s", name="first"), artifact, mode="append"
    )
    assert [row["id"] for row in _manifest(artifact)["processes"]] == ["up", "first"]
    # The promoted member keeps its contract: the same process and value
    # (its own generation now, equal to the exact relation it was served by).
    assert Runtime.load(artifact, process="first").physics.process == "s s > s s"
    promoted = np.array(_born(artifact, "first"))
    assert np.allclose(promoted, _born(stored, "first"), rtol=1e-13, atol=0)
    assert _values(artifact, "second") == _values(stored, "second")
    assert served is not None


def test_an_incoming_member_cannot_take_a_stored_id(tmp_path, model_cache):
    from pyamplicol.api.errors import ProcessIdCollisionError

    card = _card(
        tmp_path,
        model_cache,
        expression="u u~ > g g",
        name="taken",
        extra="flavor_blind = true",
    )
    artifact = tmp_path / "artifact"
    generator = Generator(resolve_config(card))
    generator.generate(ProcessRequest.parse("u u~ > g g", name="taken"), artifact)
    before, values = _digest(artifact), _values(artifact, "taken")
    with pytest.raises(ProcessIdCollisionError, match="'taken'"):
        generator.generate(
            ProcessSet(
                (
                    ProcessRequest.parse("d d > d d", name="down"),
                    ProcessRequest.parse("s s > s s", name="taken"),
                )
            ),
            artifact,
            mode="append",
        )
    assert _digest(artifact) == before
    assert _values(artifact, "taken") == values


def test_an_append_cannot_take_an_alias_id(tmp_path, model_cache):
    from pyamplicol.api import ProcessAlias
    from pyamplicol.api.errors import ProcessIdCollisionError

    card = _card(tmp_path, model_cache, expression="u u~ > g g", name="first")
    artifact = tmp_path / "artifact"
    generator = Generator(resolve_config(card))
    generator.generate(
        ProcessSet(
            (ProcessRequest.parse("u u~ > g g", name="first"),),
            (ProcessAlias("other", "first", (1, 0, 2, 3)),),
        ),
        artifact,
    )
    before, values = _digest(artifact), _values(artifact, "first")
    with pytest.raises(ProcessIdCollisionError, match="'other'"):
        generator.generate(
            ProcessRequest.parse("d d~ > e+ e-", name="other"), artifact, mode="append"
        )
    assert _digest(artifact) == before
    assert _values(artifact, "first") == values
    assert Runtime.load(artifact, process="other").physics.process == "u~ u > G G"


# Model parameters of an append (review r2) -----------------------------------


@pytest.mark.parametrize(
    ("stored", "appended"),
    [("u u~ > z g", "u u~ > e+ e-"), ("u u~ > e+ e-", "u u~ > z g")],
)
def test_an_append_evaluating_another_parameter_point_is_refused(
    tmp_path, model_cache, stored, appended
):
    # Stable external widths fix WZ = 0 for u u~ > z g only: the Drell-Yan
    # process evaluates the model's Z width.
    card = _card(tmp_path, model_cache, expression=stored, name="base")
    text = card.read_text().replace(
        'fixed_parameters = { WT = "0", WZ = "0", WW = "0", WH = "0" }',
        'fixed_parameters = { WT = "0" }',
    )
    card.write_text(
        text.replace(
            "[loop.preparation]", '[loop]\nexternal_widths = "zero"\n[loop.preparation]'
        )
    )
    artifact = tmp_path / "artifact"
    generator = Generator(resolve_config(card))
    generator.generate(ProcessRequest.parse(stored, name="base"), artifact)
    before = _digest(artifact)
    with pytest.raises(GenerationError, match=r"WZ = ") as error:
        generator.generate(
            ProcessRequest.parse(appended, name="more"), artifact, mode="append"
        )
    message = str(error.value)
    assert "2.441404" in message and "0.0" in message
    assert _digest(artifact) == before


# Exact flavour members in the Python selector (review r2) --------------------


def test_a_member_served_twice_is_ambiguous_in_every_spelling(grouped_artifact):
    _, artifact = grouped_artifact
    for spelling in ("s s > s s", "S S > S S"):
        with pytest.raises(EvaluationError, match="ambiguous") as error:
            Runtime.load(artifact, process=spelling)
        assert "first, second" in str(error.value)
    for process in ("first", "second"):
        assert Runtime.load(artifact, process=process).physics.process == "s s > s s"


# The quark-line cut before aliases (review r2) -------------------------------


def test_the_quark_line_cut_applies_before_an_alias_is_resolved(tmp_path, model_cache):
    from pyamplicol.api import ProcessAlias

    card = _card(
        tmp_path,
        model_cache,
        expression="x y > a a",
        name="sample",
        extra="""multiparticles = { x = ["g", "u"], y = ["g", "u~"] }
max_quark_lines = 0
loop_induced = "include"
max_coupling_orders = { QCD = 2, QED = 2 }""",
    )
    request = ProcessSet(
        (ProcessRequest.parse("x y > a a", name="sample"),),
        (ProcessAlias("twophotons", "sample", (0, 1, 3, 2)),),
    )
    generator = Generator(resolve_config(card))
    plan = generator.plan(request)
    assert plan.unsupported_features == ()
    assert [(p.name, p.expression) for p in plan.concrete_processes] == [
        ("sample_1", "G G > A A")
    ]
    generator.generate(request, tmp_path / "artifact")
    (record,) = _manifest(tmp_path / "artifact")["processes"]
    assert record["id"] == "sample_1"
    assert [alias["id"] for alias in record["aliases"]] == ["twophotons"]
    assert Runtime.load(tmp_path / "artifact", process="twophotons").physics.process
