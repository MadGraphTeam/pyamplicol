# SPDX-License-Identifier: 0BSD
"""Request options of one-loop generation on the shipped ``loop_sm``: each
option means what it means on the tree route, in the dry run and in
generation alike (real generation, small requests)."""

import io
import json

import numpy as np
import pytest

from pyamplicol.api import Generator, ProcessRequest, Runtime
from pyamplicol.api.errors import GenerationError
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
    from pyamplicol.api import ProcessSet

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
