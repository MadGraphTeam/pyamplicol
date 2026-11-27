# SPDX-License-Identifier: 0BSD
from __future__ import annotations

from typing import TYPE_CHECKING

from pyamplicol.config.errors import ConfigurationError, PyAmpliColError

if TYPE_CHECKING:
    from .virtual_results import VirtualFailureDiagnostic, VirtualVerificationDiagnostic


class ModelError(PyAmpliColError):
    """A model source or compiled model is invalid."""


class GenerationError(PyAmpliColError):
    """Planning or artifact generation failed."""


class NoTreeDiagramError(GenerationError):
    """A tree-level request has no Feynman diagram at its coupling orders.

    Raised before any execution lane is built, the same for every lane and
    model source. ``processes`` holds the request expressions without a
    diagram; ``coupling_orders`` describes the requested coupling-order
    limits (empty: none). A request that has diagrams without a setting that
    removes them all raises ``RequestFilterError`` instead. Such a process may
    be loop-induced: it is then
    served at one loop (``process.loop_coupling_orders`` with
    ``process.loop_induced``, MG5_aMC syntax ``[noborn=QCD]``).
    ``key`` is ``"no-tree-diagram"``."""

    key = "no-tree-diagram"

    def __init__(
        self,
        message: str,
        *,
        processes: tuple[str, ...] = (),
        coupling_orders: str = "",
    ) -> None:
        super().__init__(message)
        self.processes = processes
        self.coupling_orders = coupling_orders


class RequestFilterError(GenerationError):
    """Settings of the request remove the tree-level Born it has without them.

    Raised before any execution lane is built. The message names the settings
    (``process.max_quark_lines``, ``process.max_coupling_orders``, the model's
    coupling-order expansion orders under the ``minimal`` policy), what each
    removed and which must be relaxed to serve the request: one of them, or
    several together when each alone keeps it empty (decided by the same Born
    check as generation, on the relaxed request). ``processes`` holds the
    request expressions so emptied and ``settings`` those settings. ``key`` is
    ``"request-filter"``."""

    key = "request-filter"

    def __init__(
        self,
        message: str,
        *,
        processes: tuple[str, ...] = (),
        settings: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.processes = processes
        self.settings = settings


class ProcessIdCollisionError(GenerationError):
    """Two public processes of an artifact would share an ID.

    The public IDs of an artifact are its process IDs and process alias IDs.
    Raised before anything is written when a generation, or an append to an
    existing artifact, would give one ID to two of them (the artifact is then
    left as it was); the message names both. ``process_ids`` holds the shared
    IDs. ``key`` is ``"process-id-collision"``."""

    key = "process-id-collision"

    def __init__(self, message: str, *, process_ids: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.process_ids = process_ids


class ArtifactError(PyAmpliColError):
    """An artifact is malformed, incomplete, or unavailable."""


class CompatibilityError(ArtifactError):
    """An artifact is incompatible with the active target or ABI."""


class ReductionUnavailable(CompatibilityError):
    """An explicitly requested one-loop reduction backend cannot serve the
    call: the native extension lacks it, it does not serve the call's
    carrier, the artifact does not admit it, or the call's output does not
    run it (``reduction="ninjars"`` / ``"tirust"``; ``"auto"`` falls back
    with its reason recorded instead). Raised before any point is
    evaluated; ``key`` is ``"reduction-unavailable"``."""

    key = "reduction-unavailable"


class EvaluationError(PyAmpliColError):
    """Runtime loading, selection, or evaluation failed."""

    def __init__(
        self,
        message: str,
        *,
        failures: tuple[VirtualFailureDiagnostic, ...] = (),
        verification: tuple[VirtualVerificationDiagnostic, ...] = (),
    ) -> None:
        super().__init__(message)
        self.failures = failures
        self.verification = verification


class DependencyError(PyAmpliColError):
    """A required optional or native dependency is unavailable."""


class NativePlatformError(DependencyError):
    """The running platform cannot load one of pyAmpliCol's native libraries.

    On Linux a native library needs ELF symbol versions from glibc
    (``GLIBC_2.38``, or an ABI marker such as ``GLIBC_ABI_GNU2_TLS``). Raised
    before ``pyamplicol._rusticol`` is loaded when the running glibc does not
    define one of them, or when the process does not run on glibc at all; and
    in place of the dynamic loader's "version `GLIBC_...' not found" error when
    it loads ``pyamplicol._rusticol`` (a library it depends on included) or
    Symbolica's extension at ``import pyamplicol``; other native code reports
    the loader's error unchanged. The dynamic loader would refuse the library
    for the same reason. It is not an ImportError, so code that treats a
    missing optional module as absent does not hide it.

    Attributes: ``library`` (path, if known), ``missing`` (the version names
    the running glibc does not define, numbered ones first), ``required`` (the
    newest glibc release among the missing numbered versions, ``"2.38"``; None
    when only ABI markers are missing, which no release number guarantees) and
    ``found`` (the running glibc release, None if the C library is not glibc).
    """

    def __init__(
        self,
        message: str,
        *,
        library: str | None = None,
        required: str | None = None,
        found: str | None = None,
        missing: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.library = library
        self.required = required
        self.found = found
        self.missing = missing


__all__ = [
    "ArtifactError",
    "CompatibilityError",
    "ConfigurationError",
    "DependencyError",
    "EvaluationError",
    "GenerationError",
    "ModelError",
    "NativePlatformError",
    "NoTreeDiagramError",
    "ProcessIdCollisionError",
    "PyAmpliColError",
    "ReductionUnavailable",
    "RequestFilterError",
]
