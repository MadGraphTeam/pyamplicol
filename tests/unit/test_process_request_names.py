"""Automatic process names stay readable and are unique within one call.

The readable default name drops charge signs, case and punctuation, so two
distinct expressions can share it (``u mu- > u mu-`` and ``u mu+ > u mu+``).
Generating such processes in one call must work: the colliding requests take
the digest form, every other name is the unchanged default name.
"""

from __future__ import annotations

import itertools
import re

import pytest

from pyamplicol.api import ProcessRequest, ProcessSet
from pyamplicol.api.requests import (
    _default_process_name,
    _digest_process_name,
    parse_process_requests,
)
from pyamplicol.api.services import _appended_process_names, _process_set
from tools.developer.builtin_sm_ufo_sweep import two_to_two_processes

_DIGEST_FORM = re.compile(r"^[a-z][a-z0-9_]*_[0-9a-f]{10}$")


def _colliding_two_to_two_groups() -> list[tuple[str, ...]]:
    groups: dict[str, list[str]] = {}
    for process in two_to_two_processes():
        groups.setdefault(_default_process_name(process), []).append(process)
    return [tuple(group) for group in groups.values() if len(group) > 1]


_GROUPS = _colliding_two_to_two_groups()
_PAIRS = [pair for group in _GROUPS for pair in itertools.combinations(group, 2)]


def test_the_two_to_two_catalogue_has_colliding_default_names() -> None:
    # The census of every 2 -> 2 Standard Model process: 126 names shared by
    # 268 processes (164 pairs), from charge signs alone.
    assert len(_GROUPS) >= 100
    assert ("u mu- > u mu-", "u mu+ > u mu+") in _PAIRS or (
        "u mu+ > u mu+",
        "u mu- > u mu-",
    ) in _PAIRS


@pytest.mark.parametrize("pair", _PAIRS, ids=lambda pair: " | ".join(pair))
def test_every_colliding_pair_gets_distinct_names_in_one_call(
    pair: tuple[str, str],
) -> None:
    for ordered in (pair, pair[::-1]):
        names = [request.name for request in _process_set(list(ordered)).requests]
        assert len(set(names)) == 2
        assert names == [_digest_process_name(expression) for expression in ordered]
        assert all(_DIGEST_FORM.fullmatch(name) for name in names)
    # Alone, each process keeps its readable default name.
    for expression in pair:
        assert _process_set(expression).requests[0].name == _default_process_name(
            expression
        )


def test_whole_colliding_catalogue_in_one_call() -> None:
    processes = [process for group in _GROUPS for process in group]
    names = [request.name for request in _process_set(processes).requests]
    assert len(set(names)) == len(names)


def test_names_without_a_collision_are_unchanged() -> None:
    expressions = ["u mu- > u mu-", "u mu+ > u mu+", "e+ e- > mu+ mu-", "g g > g g"]
    names = [request.name for request in _process_set(expressions).requests]
    assert names[2:] == ["e_e_to_mu_mu", "g_g_to_g_g"]
    assert names[0] != names[1]
    # A whitespace variant is the same expression, hence a duplicate request.
    with pytest.raises(ValueError, match="repeated: 'u_mu_to_u_mu'"):
        _process_set(["u mu- > u mu-", "u  mu- >   u mu-"])


def test_from_expressions_and_explicit_names() -> None:
    names = [
        request.name
        for request in ProcessSet.from_expressions(
            ["u mu- > u mu-", "u mu+ > u mu+"]
        ).requests
    ]
    assert len(set(names)) == 2
    # Explicit names are never changed; an automatic name equal to one of
    # them takes the digest form.
    requests = parse_process_requests(
        [("u mu- > u mu-", "u_mu_to_u_mu"), ("u mu+ > u mu+", None)]
    )
    assert requests[0].name == "u_mu_to_u_mu"
    assert requests[1].name == _digest_process_name("u mu+ > u mu+")
    kept = ProcessRequest.parse("u mu+ > u mu+", name="mine")
    assert parse_process_requests([kept, "u mu- > u mu-"])[0] is kept
    assert parse_process_requests([kept, "u mu- > u mu-"])[1].name == "u_mu_to_u_mu"


def test_append_reserves_the_names_of_the_artifact() -> None:
    reserved = {"u_mu_to_u_mu": "u mu- > u mu-"}
    other = parse_process_requests(["u mu+ > u mu+"], reserved=reserved)
    assert other[0].name == _digest_process_name("u mu+ > u mu+")
    # The same expression again keeps its name (the writer refuses the
    # duplicate process as before).
    same = parse_process_requests(["u mu- > u mu-"], reserved=reserved)
    assert same[0].name == "u_mu_to_u_mu"


def test_appended_names_of_a_missing_artifact(tmp_path) -> None:
    assert _appended_process_names(tmp_path / "missing") == {}
