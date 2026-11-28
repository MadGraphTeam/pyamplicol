# SPDX-License-Identifier: 0BSD
"""An append keeps every public process ID of a tree artifact: the IDs of
process-group members served through a representative too."""

import hashlib
import json

import pytest

from pyamplicol.api import Generator, ProcessRequest, ProcessSet, Runtime
from pyamplicol.api.errors import ProcessIdCollisionError
from pyamplicol.config import resolve_config


def _digest(artifact):
    digest = hashlib.sha256()
    for path in sorted(artifact.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(artifact)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.fixture
def grouped(tmp_path):
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


def test_an_append_cannot_take_a_served_member_id_for_another_process(grouped):
    generator, artifact = grouped
    before = _digest(artifact)
    with pytest.raises(ProcessIdCollisionError, match="'charm'"):
        generator.generate(
            ProcessRequest.parse("d d~ > g g", name="charm"), artifact, mode="append"
        )
    assert _digest(artifact) == before
    assert Runtime.load(artifact, process="charm").physics.process == "c c~ > g g"


def test_an_append_cannot_reuse_a_served_member_id_for_the_same_process(grouped):
    generator, artifact = grouped
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
