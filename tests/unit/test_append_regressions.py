# SPDX-License-Identifier: 0BSD
"""Every append reproduction raised in review, one loop and compiled tree,
in one file: an append keeps every public process ID and what it serves,
adds only processes the artifact does not hold, and evaluates at the
artifact's parameter point.

Rounds: settings compatibility (r1); parameter point both directions, IDs of
aliases and of served members, the reverse member case (r2); the arrow
(decay against scattering) and T12 promotions none/same/moved (r3); the
electron/positron automatic suffix (r4); the same process in another
spelling, the lowercase gluon and T12 kept (r5); the two-charge batch, its
reverse with a served member, a retry of an alias's process (r6); an
appended target's own permutation alias and nickname (r7)."""

import hashlib
import io
import json

import numpy as np
import pytest

from pyamplicol.api import Generator, ProcessRequest, ProcessSet, Runtime
from pyamplicol.api.errors import (
    EvaluationError,
    GenerationError,
    ProcessIdCollisionError,
)
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


def _digest(artifact):

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


def _born(artifact, process):
    result = Runtime.load(artifact, process=process).evaluate(
        _points(), mu_r2=[8315.0, 8315.0]
    )
    return [float(value[0]) for value in result.born_values]


def _copy(artifact, tmp_path):
    import shutil

    target = tmp_path / "copy"
    shutil.copytree(artifact, target)
    return target


def _history(name, i, j):
    """The colour correlation ``name``: T_i (bra) . T_j (ket)."""

    return {
        "id": name,
        "bra": [{"kind": "emit-gluon", "emitter": i, "emitted": -1}],
        "ket": [{"kind": "emit-gluon", "emitter": j, "emitted": -1}],
    }


def _correlated(artifact, process, name):
    result = Runtime.load(artifact, process=process).evaluate_correlated(
        _points(), color_correlation=name, mu_r2=[8315.0, 8315.0]
    )
    return repr(result.values)


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


def test_an_append_cannot_reuse_a_served_member_id_for_the_same_process(
    grouped_artifact, tmp_path
):
    from pyamplicol.api.errors import ProcessIdCollisionError

    # An ID keeps what it serves: even the same process, generated anew,
    # need not serve the same observables and values.
    card, stored = grouped_artifact
    artifact = _copy(stored, tmp_path)
    before, values = _digest(artifact), _values(artifact, "first")
    with pytest.raises(ProcessIdCollisionError, match="'first'"):
        Generator(resolve_config(card)).generate(
            ProcessRequest.parse("s s > s s", name="first"), artifact, mode="append"
        )
    assert _digest(artifact) == before
    assert _values(artifact, "first") == values


@pytest.mark.parametrize(
    "appended", [None, ("T12", 1, 2), ("T12", 1, 3)], ids=["none", "same", "moved"]
)
def test_an_append_cannot_change_what_a_served_id_correlates(
    tmp_path, model_cache, appended
):
    from pyamplicol.api.errors import ProcessIdCollisionError
    from pyamplicol.correlators import CorrelatorConfig

    card = _card(
        tmp_path,
        model_cache,
        expression="d d > d d",
        name="base",
        extra="flavor_blind = true",
    )
    generator = Generator(resolve_config(card))
    artifact = tmp_path / "artifact"
    generator.generate(
        ProcessSet(
            (
                ProcessRequest.parse("d d > d d", name="base"),
                ProcessRequest.parse("s s > s s", name="member"),
            )
        ),
        artifact,
        correlators=CorrelatorConfig.from_json_dict(
            {"color_correlations": [_history("T12", 1, 2)]}
        ),
    )
    before, t12 = _digest(artifact), _correlated(artifact, "member", "T12")
    correlators = (
        None
        if appended is None
        else CorrelatorConfig.from_json_dict(
            {"color_correlations": [_history(*appended)]}
        )
    )
    with pytest.raises(ProcessIdCollisionError, match="'member'"):
        generator.generate(
            ProcessRequest.parse("s s > s s", name="member"),
            artifact,
            mode="append",
            correlators=correlators,
        )
    assert _digest(artifact) == before
    assert _correlated(artifact, "member", "T12") == t12


def test_an_incoming_member_cannot_take_a_stored_id_with_other_observables(
    tmp_path, model_cache
):
    from pyamplicol.api.errors import ProcessIdCollisionError
    from pyamplicol.correlators import CorrelatorConfig

    card = _card(
        tmp_path,
        model_cache,
        expression="s s > s s",
        name="member",
        extra="flavor_blind = true",
    )
    generator = Generator(resolve_config(card))
    artifact = tmp_path / "artifact"
    generator.generate(ProcessRequest.parse("s s > s s", name="member"), artifact)
    before = _digest(artifact)
    with pytest.raises(ProcessIdCollisionError, match="'member'"):
        generator.generate(
            ProcessSet(
                (
                    ProcessRequest.parse("d d > d d", name="base"),
                    ProcessRequest.parse("s s > s s", name="member"),
                )
            ),
            artifact,
            mode="append",
            correlators=CorrelatorConfig.from_json_dict(
                {"color_correlations": [_history("T12", 1, 2)]}
            ),
        )
    assert _digest(artifact) == before


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


def test_a_member_served_twice_is_ambiguous_in_every_spelling(grouped_artifact):
    _, artifact = grouped_artifact
    for spelling in ("s s > s s", "S S > S S"):
        with pytest.raises(EvaluationError, match="ambiguous") as error:
            Runtime.load(artifact, process=spelling)
        assert "first, second" in str(error.value)
    for process in ("first", "second"):
        assert Runtime.load(artifact, process=process).physics.process == "s s > s s"


@pytest.mark.parametrize("direction", ["member-then-record", "record-then-member"])
def test_the_arrow_is_part_of_a_process_identity(tmp_path, model_cache, direction):
    # Z > g s s~ (a decay) and Z g > s s~ (a scattering) list the same PDGs in
    # the same order; they are different processes, so neither may take the
    # other's ID.
    from pyamplicol.api.errors import ProcessIdCollisionError

    card = _card(
        tmp_path,
        model_cache,
        expression="z > s s~ g",
        name="base",
        extra="flavor_blind = true",
    )
    generator = Generator(resolve_config(card))
    artifact = tmp_path / "artifact"
    if direction == "member-then-record":
        # `take` is served through `base` (a side permutation of it).
        generator.generate(
            ProcessSet(
                (
                    ProcessRequest.parse("z > s s~ g", name="base"),
                    ProcessRequest.parse("z > g s s~", name="take"),
                )
            ),
            artifact,
        )
        incoming = ProcessRequest.parse("z g > s s~", name="take")
        kept = "Z > G s s~"
    else:
        generator.generate(ProcessRequest.parse("z g > s s~", name="take"), artifact)
        incoming = ProcessSet(
            (
                ProcessRequest.parse("z > s s~ g", name="base"),
                ProcessRequest.parse("z > g s s~", name="take"),
            )
        )
        kept = "Z G > s s~"
    before = _digest(artifact)
    assert Runtime.load(artifact, process="take").physics.process == kept
    with pytest.raises(ProcessIdCollisionError, match="'take'"):
        generator.generate(incoming, artifact, mode="append")
    assert _digest(artifact) == before
    assert Runtime.load(artifact, process="take").physics.process == kept


def test_an_unnamed_append_avoids_the_id_of_a_served_member(tmp_path, model_cache):
    # e- u > e- u is served through u e- > u e- (a side permutation) as
    # e_u_to_e_u; an unnamed e+ u > e+ u, whose readable name is the same,
    # takes the digest-suffixed name, as against a stored ID.
    card = _card(
        tmp_path,
        model_cache,
        expression="u e- > u e-",
        name="unused",
        extra="flavor_blind = true",
    )
    generator = Generator(resolve_config(card))
    artifact = tmp_path / "artifact"
    generator.generate(
        ProcessSet(
            (ProcessRequest.parse("u e- > u e-"), ProcessRequest.parse("e- u > e- u"))
        ),
        artifact,
    )
    served = Runtime.load(artifact, process="e_u_to_e_u")
    assert served.physics.process == "e- u > e- u"
    before = _values(artifact, "e_u_to_e_u")
    stored_before = {row["id"] for row in _manifest(artifact)["processes"]}
    generator.generate(ProcessRequest.parse("e+ u > e+ u"), artifact, mode="append")
    stored = {row["id"]: row["expression"] for row in _manifest(artifact)["processes"]}
    added = {name: stored[name] for name in set(stored) - stored_before}
    assert list(added.values()) == ["e+ u > e+ u"]
    # The readable name is a served member's: the digest-suffixed form.
    assert all(name.startswith("e_u_to_e_u_") for name in added)
    assert _values(artifact, "e_u_to_e_u") == before
    # The same process again, in either order, is a duplicate (refused).
    from pyamplicol.api.errors import ProcessIdCollisionError

    digest = _digest(artifact)
    for expression in ("e- u > e- u", "u e+ > u e+"):
        with pytest.raises(ProcessIdCollisionError):
            generator.generate(
                ProcessRequest.parse(expression), artifact, mode="append"
            )
        assert _digest(artifact) == digest


def test_an_identical_unnamed_append_is_refused_in_any_spelling(tmp_path, model_cache):
    # s g > s g is served through d g > d g with the colour correlation T12;
    # re-appending it unnamed, in any spelling of its particles, names the
    # same process: it is a duplicate (refused), not a new process under a
    # digest name, and the expression keeps serving T12.
    from pyamplicol.api.errors import ProcessIdCollisionError
    from pyamplicol.correlators import CorrelatorConfig

    card = _card(
        tmp_path,
        model_cache,
        expression="d g > d g",
        name="unused",
        extra="flavor_blind = true",
    )
    generator = Generator(resolve_config(card))
    artifact = tmp_path / "artifact"
    generator.generate(
        ProcessSet(
            (ProcessRequest.parse("d g > d g"), ProcessRequest.parse("s g > s g"))
        ),
        artifact,
        correlators=CorrelatorConfig.from_json_dict(
            {"color_correlations": [_history("T12", 1, 2)]}
        ),
    )
    assert Runtime.load(artifact, process="s_g_to_s_g").physics.process == "s G > s G"
    before, t12 = _digest(artifact), _correlated(artifact, "s g > s g", "T12")
    for spelling in ("s g > s g", "s G > s G", "S g > S g"):
        with pytest.raises(ProcessIdCollisionError, match="'s_g_to_s_g'"):
            generator.generate(ProcessRequest.parse(spelling), artifact, mode="append")
        assert _digest(artifact) == before
    assert _correlated(artifact, "s g > s g", "T12") == t12


def test_an_append_holding_a_process_already_there_is_refused(tmp_path, model_cache):
    # Every stored, aliased or served process is checked, whatever its ID:
    # (a) a two-charge batch stores e+ u > e+ u under a digest-suffixed ID,
    # whose identical retry is refused; (b) a batch with the served member
    # e- u > e- u and a new process is refused as a whole; (c) a retry of an
    # alias's process is refused. Each time the artifact is unchanged and the
    # expressions stay unambiguous (the served member keeps its ID and value).
    from pyamplicol.api import ProcessAlias
    from pyamplicol.api.errors import ProcessIdCollisionError

    card = _card(
        tmp_path,
        model_cache,
        expression="u e- > u e-",
        name="unused",
        extra="flavor_blind = true",
    )
    generator = Generator(resolve_config(card))
    artifact = tmp_path / "artifact"
    generator.generate(
        ProcessSet(
            (
                ProcessRequest.parse("u e- > u e-"),
                ProcessRequest.parse("e- u > e- u"),
                ProcessRequest.parse("e+ u > e+ u"),
                ProcessRequest.parse("u u~ > g g", name="first"),
            ),
            (ProcessAlias("other", "first", (1, 0, 2, 3)),),
        ),
        artifact,
    )
    before = _digest(artifact)
    member = Runtime.load(artifact, process="e- u > e- u").physics.process_id
    values = _values(artifact, "e- u > e- u")
    positron = Runtime.load(artifact, process="e+ u > e+ u").physics.process_id
    assert positron.startswith("e_u_to_e_u_")
    for batch in (
        ProcessRequest.parse("e+ u > e+ u"),
        ProcessSet(
            (ProcessRequest.parse("e- u > e- u"), ProcessRequest.parse("c e+ > c e+"))
        ),
        ProcessRequest.parse("u~ u > g g"),
    ):
        with pytest.raises(ProcessIdCollisionError, match="already in the artifact"):
            generator.generate(batch, artifact, mode="append")
        assert _digest(artifact) == before
    assert Runtime.load(artifact, process="e+ u > e+ u").physics.process_id == positron
    assert Runtime.load(artifact, process="e- u > e- u").physics.process_id == member
    assert _values(artifact, "e- u > e- u") == values
    assert Runtime.load(artifact, process="u~ u > g g").physics.process == "u~ u > G G"


def test_an_appended_target_may_bring_its_own_aliases(tmp_path, model_cache):
    # A new u u~ > g g with an alias exchanging its identical gluons is one
    # process: admitted, the alias served by it at the exchanged momenta. An
    # alias whose name is taken, and two appended targets of one process,
    # are refused.
    from pyamplicol.api import ProcessAlias
    from pyamplicol.api.errors import ProcessIdCollisionError

    card = _card(tmp_path, model_cache, expression="d d~ > g g", name="ddgg")
    generator = Generator(resolve_config(card))
    artifact = tmp_path / "artifact"
    generator.generate(ProcessRequest.parse("d d~ > g g", name="ddgg"), artifact)
    generator.generate(
        ProcessSet(
            (ProcessRequest.parse("u u~ > g g", name="jets"),),
            (
                ProcessAlias("swap_jets", "jets", (0, 1, 3, 2)),
                # A plain nickname of the same process.
                ProcessAlias("nickname", "jets"),
            ),
        ),
        artifact,
        mode="append",
    )

    points = _points()
    swapped = [[point[0], point[1], point[3], point[2]] for point in points]
    alias = Runtime.load(artifact, process="swap_jets").evaluate(
        points, mu_r2=[8315.0, 8315.0]
    )
    target = Runtime.load(artifact, process="jets").evaluate(
        swapped, mu_r2=[8315.0, 8315.0]
    )
    assert repr((alias.born_values, alias.values)) == repr(
        (target.born_values, target.values)
    )
    nickname = Runtime.load(artifact, process="nickname").evaluate(
        points, mu_r2=[8315.0, 8315.0]
    )
    direct = Runtime.load(artifact, process="u u~ > g g").evaluate(
        points, mu_r2=[8315.0, 8315.0]
    )
    assert repr((nickname.born_values, nickname.values)) == repr(
        (direct.born_values, direct.values)
    )
    assert Runtime.load(artifact, process="u u~ > g g").physics.process == "u u~ > G G"
    before = _digest(artifact)
    for batch in (
        ProcessSet(
            (ProcessRequest.parse("s s~ > g g", name="strange"),),
            (ProcessAlias("ddgg", "strange", (0, 1, 3, 2)),),
        ),
        ProcessSet(
            (
                ProcessRequest.parse("c c~ > g g", name="charm"),
                ProcessRequest.parse("c c~ > g g", name="charm_again"),
            )
        ),
    ):
        with pytest.raises(ProcessIdCollisionError):
            generator.generate(batch, artifact, mode="append")
        assert _digest(artifact) == before


# Compiled tree -------------------------------------------------------------


@pytest.fixture
def grouped_tree(tmp_path):
    """``c c~ > g g`` served as ``charm`` through ``u u~ > g g`` (``up``)."""

    card = tmp_path / "card.toml"
    card.write_text(
        f"""
action = "generate"
[process]
entries = [{{ expression = "u u~ > g g", name = "up" }}]
flavor_blind = true
[evaluator]
execution_mode = "compiled"
[generation]
output = {json.dumps(str(tmp_path / "unused"))}
"""
    )
    generator = Generator(resolve_config(card))
    artifact = tmp_path / "artifact"
    generator.generate(
        ProcessSet(
            (
                ProcessRequest.parse("u u~ > g g", name="up"),
                ProcessRequest.parse("c c~ > g g", name="charm"),
            )
        ),
        artifact,
    )
    assert Runtime.load(artifact, process="charm").physics.process == "c c~ > g g"
    return generator, artifact


def test_an_append_cannot_take_a_served_member_id_on_a_compiled_tree(grouped_tree):
    generator, artifact = grouped_tree
    before = _digest(artifact)
    with pytest.raises(ProcessIdCollisionError, match="'charm'"):
        generator.generate(
            ProcessRequest.parse("d d~ > g g", name="charm"), artifact, mode="append"
        )
    assert _digest(artifact) == before
    assert Runtime.load(artifact, process="charm").physics.process == "c c~ > g g"


def test_an_append_cannot_reuse_a_served_member_id_on_a_compiled_tree(grouped_tree):
    generator, artifact = grouped_tree
    before = _digest(artifact)
    with pytest.raises(ProcessIdCollisionError, match="'charm'"):
        generator.generate(
            ProcessRequest.parse("c c~ > g g", name="charm"), artifact, mode="append"
        )
    assert _digest(artifact) == before


@pytest.mark.parametrize("direction", ["member-then-record", "record-then-member"])
def test_the_arrow_is_part_of_a_tree_process_identity(tmp_path, direction):
    # Compiled tree on a UFO: Z > g s s~ (a decay) and Z g > s s~ (a
    # scattering) list the same PDGs in the same order.
    import io

    from pyamplicol.cli import run_cli

    cache = tmp_path / "models"
    card = tmp_path / "card.toml"
    card.write_text(
        f"""
action = "generate"
[model]
source = "loop_sm"
restriction = "no_b_mass"
cache_dir = {json.dumps(str(cache))}
[process]
entries = [{{ expression = "z > s s~ g", name = "base" }}]
flavor_blind = true
[evaluator]
execution_mode = "compiled"
[generation]
output = {json.dumps(str(tmp_path / "unused"))}
"""
    )
    # The model compiled into the card's cache.
    assert (
        run_cli(
            ("model", "inspect", "--card", str(card), "--json"),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        == 0
    )
    generator = Generator(resolve_config(card))
    artifact = tmp_path / "artifact"
    pair = ProcessSet(
        (
            ProcessRequest.parse("z > s s~ g", name="base"),
            ProcessRequest.parse("z > g s s~", name="take"),
        )
    )
    crossed = ProcessRequest.parse("z g > s s~", name="take")
    first, second = (
        (pair, crossed)
        if direction == "member-then-record"
        else (
            crossed,
            pair,
        )
    )
    generator.generate(first, artifact)
    before = _digest(artifact)
    kept = Runtime.load(artifact, process="take").physics.process
    with pytest.raises(ProcessIdCollisionError, match="'take'"):
        generator.generate(second, artifact, mode="append")
    assert _digest(artifact) == before
    assert Runtime.load(artifact, process="take").physics.process == kept


def test_an_identical_unnamed_append_is_refused_on_a_compiled_tree(tmp_path):
    # Compiled tree on a UFO (the gluon spelled G), with flavour grouping:
    # re-appending g u > g u unnamed, in either spelling, is the same process
    # as the stored one, refused (not stored again under a digest name), and
    # its expression stays unambiguous.
    import io

    from pyamplicol.api.errors import GenerationError
    from pyamplicol.cli import run_cli

    cache = tmp_path / "models"
    card = tmp_path / "card.toml"
    card.write_text(
        f"""
action = "generate"
[model]
source = "loop_sm"
restriction = "no_b_mass"
cache_dir = {json.dumps(str(cache))}
[process]
entries = [{{ expression = "u g > u g", name = "unused" }}]
flavor_blind = true
[evaluator]
execution_mode = "compiled"
[generation]
output = {json.dumps(str(tmp_path / "unused"))}
"""
    )
    assert (
        run_cli(
            ("model", "inspect", "--card", str(card), "--json"),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        == 0
    )
    generator = Generator(resolve_config(card))
    artifact = tmp_path / "artifact"
    generator.generate(
        ProcessSet(
            (ProcessRequest.parse("u g > u g"), ProcessRequest.parse("g u > g u"))
        ),
        artifact,
    )
    assert Runtime.load(artifact, process="g u > g u").physics.process == "G u > G u"
    before = _digest(artifact)
    for spelling in ("g u > g u", "G u > G u"):
        with pytest.raises(GenerationError, match="g_u_to_g_u"):
            generator.generate(ProcessRequest.parse(spelling), artifact, mode="append")
        assert _digest(artifact) == before
    assert Runtime.load(artifact, process="g u > g u").physics.process == "G u > G u"


def test_a_compiled_tree_append_holding_a_process_already_there_is_refused(tmp_path):
    # Built-in SM, compiled: a two-charge batch stores e+ u > e+ u under a
    # digest-suffixed ID; its identical retry, and a batch holding e- u > e- u
    # with a new process, are refused; the expressions stay unambiguous.
    from pyamplicol.api.errors import GenerationError

    card = tmp_path / "card.toml"
    card.write_text(
        f"""
action = "generate"
[process]
entries = [{{ expression = "e- u > e- u", name = "unused" }}]
[evaluator]
execution_mode = "compiled"
[generation]
output = {json.dumps(str(tmp_path / "unused"))}
"""
    )
    generator = Generator(resolve_config(card))
    artifact = tmp_path / "artifact"
    generator.generate(
        ProcessSet(
            (ProcessRequest.parse("e- u > e- u"), ProcessRequest.parse("e+ u > e+ u"))
        ),
        artifact,
    )
    before = _digest(artifact)
    positron = Runtime.load(artifact, process="e+ u > e+ u").physics.process_id
    for batch in (
        ProcessRequest.parse("e+ u > e+ u"),
        ProcessSet(
            (ProcessRequest.parse("e- u > e- u"), ProcessRequest.parse("e+ c > e+ c"))
        ),
    ):
        with pytest.raises(GenerationError, match="already"):
            generator.generate(batch, artifact, mode="append")
        assert _digest(artifact) == before
    assert Runtime.load(artifact, process="e+ u > e+ u").physics.process_id == positron
    assert (
        Runtime.load(artifact, process="e- u > e- u").physics.process == "e- u > e- u"
    )


def test_a_compiled_tree_target_may_bring_its_own_aliases(tmp_path):
    from pyamplicol.api import ProcessAlias

    card = tmp_path / "card.toml"
    card.write_text(
        f"""
action = "generate"
[process]
entries = [{{ expression = "d d~ > g g", name = "ddgg" }}]
[evaluator]
execution_mode = "compiled"
[generation]
output = {json.dumps(str(tmp_path / "unused"))}
"""
    )
    generator = Generator(resolve_config(card))
    artifact = tmp_path / "artifact"
    generator.generate(ProcessRequest.parse("d d~ > g g", name="ddgg"), artifact)
    generator.generate(
        ProcessSet(
            (ProcessRequest.parse("u u~ > g g", name="jets"),),
            (
                ProcessAlias("swap_jets", "jets", (0, 1, 3, 2)),
                # A plain nickname of the same process.
                ProcessAlias("nickname", "jets"),
            ),
        ),
        artifact,
        mode="append",
    )

    energy = 500.0
    point = [
        [energy, 0.0, 0.0, energy],
        [energy, 0.0, 0.0, -energy],
        [energy, 300.0, 0.0, 400.0],
        [energy, -300.0, 0.0, -400.0],
    ]
    swapped = [point[0], point[1], point[3], point[2]]
    alias = Runtime.load(artifact, process="swap_jets").evaluate([point])
    target = Runtime.load(artifact, process="jets").evaluate([swapped])
    assert repr(alias) == repr(target)
    nickname = Runtime.load(artifact, process="nickname").evaluate([point])
    direct = Runtime.load(artifact, process="u u~ > g g").evaluate([point])
    assert repr(nickname) == repr(direct)
    before = _digest(artifact)
    for batch in (
        ProcessSet(
            (ProcessRequest.parse("s s~ > g g", name="strange"),),
            (ProcessAlias("ddgg", "strange", (0, 1, 3, 2)),),
        ),
        ProcessSet(
            (
                ProcessRequest.parse("c c~ > g g", name="charm"),
                ProcessRequest.parse("c c~ > g g", name="charm_again"),
            )
        ),
    ):
        with pytest.raises(ProcessIdCollisionError):
            generator.generate(batch, artifact, mode="append")
        assert _digest(artifact) == before


# The invariant, by the runtime's own loaders (r8) ------------------------------


def _spellings(expression):
    """Every spelling a selector serves by a side permutation of
    ``expression``: each order of the particles on each side."""

    from itertools import permutations, product

    initial, final = (side.split() for side in expression.split(">"))
    return {
        " ".join(left) + " > " + " ".join(right)
        for left, right in product(permutations(initial), permutations(final))
    }


def _resolution_table(artifact):
    """Every public ID of ``artifact`` and every spelling of every process it
    serves (each order of each recorded expression's particles on each side)
    -> what the real selectors serve for it: ``Runtime.load`` (the native
    selector for a tree artifact, the Python one at one loop) and, on a tree
    artifact, the Python selector too; or the error they raise."""

    from pyamplicol.artifacts.manifest import load_manifest
    from pyamplicol.loops.v2.artifact import _select

    manifest = json.loads((artifact / "artifact.json").read_text())
    ids, expressions = [], []
    for record in manifest["processes"]:
        ids.append(record["id"])
        expressions.append(record["expression"])
        for alias in record.get("aliases", ()):
            ids.append(alias["id"])
            expressions.append(alias["expression"])
    groups_path = artifact / "process-groups.json"
    if groups_path.is_file():
        for group in json.loads(groups_path.read_text())["groups"]:
            for member in group["members"]:
                if not member["generated"]:
                    ids.append(member["process_id"])
                    expressions.append(member["process"])
    keys = list(
        dict.fromkeys(
            [*ids, *(s for expression in expressions for s in _spellings(expression))]
        )
    )
    tree = "loop" not in json.dumps(manifest["runtime"]).lower()
    loaded = load_manifest(artifact) if tree else None
    table = {}
    for key in keys:
        try:
            physics = Runtime.load(artifact, process=key).physics
            served = (physics.process_id, physics.process)
        except Exception as error:
            served = f"error: {type(error).__name__}"
        if tree:
            try:
                record, member = _select(loaded, key, any_basis=True)
                python = str(member.process_id) if member is not None else record["id"]
            except Exception as error:
                python = f"error: {type(error).__name__}"
            served = (served, python)
        table[key] = served
    return table


def _check_invariant(base, artifact, generator, batch):
    """Append ``batch`` to a copy of ``base``: admitted, every key of the
    result names one process and every key of ``base`` the same as before;
    refused, the artifact is byte-identical."""

    import shutil

    shutil.copytree(base, artifact)
    before_digest, before = _digest(artifact), _resolution_table(artifact)
    try:
        generator.generate(batch, artifact, mode="append")
    except GenerationError:
        assert _digest(artifact) == before_digest
        return "refused"
    after = _resolution_table(artifact)
    assert all("error" not in str(value) for value in after.values()), after
    assert all(after[key] == value for key, value in before.items()), (before, after)
    return "admitted"


def _tree_generator(tmp_path):
    card = tmp_path / "card.toml"
    card.write_text(
        f"""
action = "generate"
[process]
entries = [{{ expression = "u g > u g", name = "unused" }}]
flavor_blind = true
[evaluator]
execution_mode = "compiled"
[generation]
output = {json.dumps(str(tmp_path / "unused"))}
"""
    )
    return Generator(resolve_config(card))


def _swap_alias_base(generator, root, first, swap):
    from pyamplicol.api import ProcessAlias

    generator.generate(
        ProcessSet(
            (ProcessRequest.parse(first, name="first"),),
            (ProcessAlias("first_swap", "first", swap),),
        ),
        root,
    )


@pytest.mark.parametrize("route", ["tree", "one-loop"])
def test_an_alias_cannot_take_an_expression_another_alias_serves(
    tmp_path, model_cache, route
):
    # u g > u g with alias first_swap serving g u > u g; appending u g > g u
    # with alias second_swap serving g u > u g too is refused (the
    # expression would select two aliases), in both orders.
    from pyamplicol.api import ProcessAlias

    generator = (
        _tree_generator(tmp_path)
        if route == "tree"
        else Generator(
            resolve_config(
                _card(tmp_path, model_cache, expression="u g > u g", name="unused")
            )
        )
    )
    for index, (first, swap, second, second_swap) in enumerate(
        (
            ("u g > u g", (1, 0, 2, 3), "u g > g u", (1, 0, 3, 2)),
            ("u g > g u", (1, 0, 3, 2), "u g > u g", (1, 0, 2, 3)),
        )
    ):
        base = tmp_path / f"base{index}"
        _swap_alias_base(generator, base, first, swap)
        served = Runtime.load(base, process="g u > u g").physics.process_id
        outcome = _check_invariant(
            base,
            tmp_path / f"after{index}",
            generator,
            ProcessSet(
                (ProcessRequest.parse(second, name="second"),),
                (ProcessAlias("second_swap", "second", second_swap),),
            ),
        )
        assert outcome == "refused"
        assert served == "first_swap"


def test_appends_keep_the_resolution_invariant_on_a_compiled_tree(tmp_path):
    from pyamplicol.api import ProcessAlias

    generator = _tree_generator(tmp_path)
    base = tmp_path / "base"
    generator.generate(
        ProcessSet(
            (
                ProcessRequest.parse("u g > u g", name="ug"),
                ProcessRequest.parse("c g > c g", name="cg"),
                ProcessRequest.parse("e- u > e- u"),
                ProcessRequest.parse("e+ u > e+ u"),
                ProcessRequest.parse("u u~ > g g g", name="three"),
            ),
            (ProcessAlias("first_swap", "ug", (1, 0, 2, 3)),),
        ),
        base,
    )
    candidates = {
        "another order of a stored process under a fresh ID": (
            ProcessRequest.parse("g u > g u", name="fresh"),
            "refused",
        ),
        "another order of a stored 2 -> 3 process": (
            ProcessRequest.parse("u~ u > g g g", name="three_crossed"),
            "refused",
        ),
        "second alias of an aliased expression": (
            ProcessSet(
                (ProcessRequest.parse("u g > g u", name="second"),),
                (ProcessAlias("second_swap", "second", (1, 0, 3, 2)),),
            ),
            "refused",
        ),
        "identical retry under a suffixed ID": (
            ProcessRequest.parse("e+ u > e+ u"),
            "refused",
        ),
        "a held process next to a new one": (
            ProcessSet(
                (
                    ProcessRequest.parse("e- u > e- u"),
                    ProcessRequest.parse("e+ c > e+ c"),
                )
            ),
            "refused",
        ),
        "the process of an alias": (ProcessRequest.parse("g u > u g"), "refused"),
        "a served member's ID for another process": (
            ProcessRequest.parse("d g > d g", name="cg"),
            "refused",
        ),
        "a served member's process under a new ID": (
            ProcessRequest.parse("c g > c g", name="cg2"),
            "refused",
        ),
        "a held process under a new name": (
            ProcessRequest.parse("e+ u > e+ u", name="positron2"),
            "refused",
        ),
        "two new targets whose aliases serve one expression": (
            ProcessSet(
                (
                    ProcessRequest.parse("d g > d g", name="dg"),
                    ProcessRequest.parse("d g > g d", name="dg_crossed"),
                ),
                (
                    ProcessAlias("dg_swap", "dg", (1, 0, 2, 3)),
                    ProcessAlias("dg_crossed_swap", "dg_crossed", (1, 0, 3, 2)),
                ),
            ),
            "refused",
        ),
        "a new target with its own aliases": (
            ProcessSet(
                (ProcessRequest.parse("u u~ > g g", name="jets"),),
                (
                    ProcessAlias("swap_jets", "jets", (0, 1, 3, 2)),
                    ProcessAlias("nickname", "jets"),
                ),
            ),
            "admitted",
        ),
        "an unnamed new process": (ProcessRequest.parse("u u~ > e+ e-"), "admitted"),
    }
    for index, (name, (batch, expected)) in enumerate(candidates.items()):
        outcome = _check_invariant(base, tmp_path / f"after{index}", generator, batch)
        assert outcome == expected, name


def test_appends_keep_the_resolution_invariant_at_one_loop(tmp_path, model_cache):
    from pyamplicol.api import ProcessAlias

    card = _card(
        tmp_path,
        model_cache,
        expression="u g > u g",
        name="unused",
        extra="flavor_blind = true",
    )
    generator = Generator(resolve_config(card))
    base = tmp_path / "base"
    generator.generate(
        ProcessSet(
            (
                ProcessRequest.parse("u g > u g", name="ug"),
                ProcessRequest.parse("c g > c g", name="cg"),
            ),
            (ProcessAlias("first_swap", "ug", (1, 0, 2, 3)),),
        ),
        base,
    )
    candidates = {
        "another order of a stored process under a fresh ID": (
            ProcessRequest.parse("g u > g u", name="fresh"),
            "refused",
        ),
        "second alias of an aliased expression": (
            ProcessSet(
                (ProcessRequest.parse("u g > g u", name="second"),),
                (ProcessAlias("second_swap", "second", (1, 0, 3, 2)),),
            ),
            "refused",
        ),
        "the process of an alias": (ProcessRequest.parse("g u > u g"), "refused"),
        "a served member's process under a new ID": (
            ProcessRequest.parse("c g > c g", name="cg2"),
            "refused",
        ),
        "two new targets whose aliases serve one expression": (
            ProcessSet(
                (
                    ProcessRequest.parse("d g > d g", name="dg"),
                    ProcessRequest.parse("d g > g d", name="dg_crossed"),
                ),
                (
                    ProcessAlias("dg_swap", "dg", (1, 0, 2, 3)),
                    ProcessAlias("dg_crossed_swap", "dg_crossed", (1, 0, 3, 2)),
                ),
            ),
            "refused",
        ),
        "a new target with its own aliases": (
            ProcessSet(
                (ProcessRequest.parse("u u~ > g g", name="jets"),),
                (
                    ProcessAlias("swap_jets", "jets", (0, 1, 3, 2)),
                    ProcessAlias("nickname", "jets"),
                ),
            ),
            "admitted",
        ),
    }
    for index, (name, (batch, expected)) in enumerate(candidates.items()):
        outcome = _check_invariant(base, tmp_path / f"after{index}", generator, batch)
        assert outcome == expected, name
