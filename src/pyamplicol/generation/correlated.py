# SPDX-License-Identifier: 0BSD
"""Opt-in generation of complete coherent amplitudes and colour operators.

The ordinary generator never imports this module.  This first implementation
uses the existing generic compiled pipeline, but bypasses reductions whose
proof applies only to physical-helicity squared amplitudes.  In particular,
arbitrary external vector sources must not inherit physical-helicity zeros.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from os import PathLike
from pathlib import Path
from types import MappingProxyType
from typing import Literal, cast

from pyamplicol._internal.versions import CORRELATOR_ZERO_GROUPS_SCHEMA_VERSION
from pyamplicol.api.errors import GenerationError
from pyamplicol.api.models import CompiledModel
from pyamplicol.api.requests import ModelSource, ProcessSet
from pyamplicol.api.results import GenerationResult
from pyamplicol.artifacts import ArtifactBuilder
from pyamplicol.color.correlator_matrices import (
    build_color_correlator_matrices,
    process_color_legs,
)
from pyamplicol.color.nc_expansion import NcExpansion
from pyamplicol.color.plan import GenericColorPlan, build_color_plan
from pyamplicol.config import (
    Action,
    ColorContraction,
    ColorFFTBasis,
    ConfigClamp,
    ConfigResolution,
    EvaluatorExecutionMode,
    GenerationConfig,
    LCFlowLayout,
    RelationDiscoveryMode,
    RunConfig,
)
from pyamplicol.correlators import CorrelatorConfig
from pyamplicol.models.base import Model
from pyamplicol.processes.ir import CanonicalProcessIR
from pyamplicol.reporting import ProgressSink

from .artifact_writer import ApiBundleHook, ArtifactWriteResult
from .contracts import RuntimeExpressionSchema
from .dag_algorithms import (
    _infer_minimal_coupling_order_limits_from_color_plan,
    request_coupling_order_limits,
)
from .dag_compiler import compile_generic_dag
from .dag_types import GenericDAG
from .numerical_current_warmup import generic_dag_numerical_current_opt_out_report
from .progress import PhaseHandle
from .service import (
    GenerationBackend,
    _CompiledProcess,
    _DagProcess,
    _EvaluatorProcess,
    _NoModelSupportedAmplitudes,
    _PreparedProcessConstruction,
    _ProcessSelection,
)
from .singlet_exchange import require_representable_singlet_exchange
from .validation import build_validation_point

CORRELATOR_PAYLOAD_PATH = "correlators.json"


def correlated_configuration(
    config: GenerationConfig | RunConfig | ConfigResolution | None,
) -> ConfigResolution:
    """Retain requested colour accuracy with direct/compiled source execution."""

    if isinstance(config, ConfigResolution):
        requested, effective, clamps = config.requested, config.effective, config.clamps
    elif isinstance(config, RunConfig):
        requested = effective = config
        clamps = ()
    elif config is None or isinstance(config, GenerationConfig):
        requested = effective = RunConfig(
            action=Action.GENERATE,
            generation=GenerationConfig() if config is None else config,
        )
        clamps = ()
    else:
        raise TypeError("invalid correlated generation configuration")
    if (
        effective.color.contraction is ColorContraction.SYMMETRIC_GROUP_FFT
        and effective.color.fft_basis is ColorFFTBasis.ADJOINT
    ):
        raise ValueError(
            "adjoint FFT is not supported for correlated matrix elements; "
            "use the direct colour contraction"
        )
    if effective.process.loop_coupling_orders is not None:
        raise GenerationError(
            "virtual correlated generation is not integrated; loop corrections "
            "cannot use the tree coherent generation path"
        )
    result = replace(
        effective,
        color=replace(
            effective.color,
            contraction=ColorContraction.DIRECT,
            fft_basis=ColorFFTBasis.TRACE,
            lc_flow_layout=LCFlowLayout.TOPOLOGY_REPLAY,
        ),
        evaluator=replace(
            effective.evaluator, execution_mode=EvaluatorExecutionMode.COMPILED
        ),
        generation=replace(
            effective.generation,
            relation_discovery=replace(
                effective.generation.relation_discovery, mode=RelationDiscoveryMode.OFF
            ),
        ),
    )
    paths = (
        "color.contraction",
        "color.fft_basis",
        "color.lc_flow_layout",
        "evaluator.execution_mode",
        "generation.relation_discovery.mode",
    )

    def field(config: RunConfig, path: str) -> object:
        value: object = config
        for name in path.split("."):
            value = getattr(value, name)
        return value

    adjustments = tuple(
        ConfigClamp(
            path=path,
            requested=field(effective, path),
            effective=field(result, path),
            reason="correlations require complete coherent generic compiled amplitudes",
        )
        for path in paths
        if field(effective, path) != field(result, path)
    )
    # The source configuration may already have resolved recurrence's auto
    # compression to false. Re-select the default for this compiled lane, but
    # retain explicit user or prepared-pack choices.
    evaluator = result.evaluator
    if requested.evaluator.jit.compress == "auto" and not any(
        clamp.path == "evaluator.jit.compress" for clamp in clamps
    ):
        evaluator = replace(evaluator, jit=replace(evaluator.jit, compress="auto"))
    result = replace(
        result,
        evaluator=replace(
            evaluator,
            jit=replace(evaluator.jit, compress=evaluator.resolved_jit_compress),
        ),
    )
    return ConfigResolution(requested, result, (*clamps, *adjustments))


@dataclass(frozen=True)
class CorrelatedProcessMetadata:
    """Generation-local inputs; no new serialized copy of the DAG or model."""

    process: CanonicalProcessIR
    color_plan: GenericColorPlan
    runtime_schema: RuntimeExpressionSchema
    aliases: tuple[Mapping[str, object], ...]


class CorrelatedGenerationBackend(GenerationBackend):
    """Safety lane sharing model resolution, stage compilation and publishing."""

    def __init__(
        self,
        config: GenerationConfig | RunConfig | ConfigResolution | None,
        progress: ProgressSink | None,
        *,
        declarations: CorrelatorConfig,
        api_bundle_hook: ApiBundleHook | None = None,
        process_selection: _ProcessSelection | None = None,
    ) -> None:
        if not isinstance(declarations, CorrelatorConfig):
            raise TypeError("correlators must be a CorrelatorConfig")
        super().__init__(
            correlated_configuration(config),
            progress,
            api_bundle_hook=api_bundle_hook,
            process_selection=process_selection,
        )
        self.declarations = declarations
        self._correlated_processes: dict[str, CorrelatedProcessMetadata] = {}
        selection = self._process_selection
        partial = tuple(
            name
            for name in (
                "max_color_sectors",
                "reference_color_order",
                "selected_color_sector_ids",
                "selected_source_helicities",
            )
            if getattr(selection, name) is not None
        )
        if partial:
            raise GenerationError(
                "correlated generation requires complete colour and helicity coverage; "
                "remove " + ", ".join(f"process.{name}" for name in partial)
            )

    @property
    def _color_accuracy(self) -> str:
        # The inherited setting selects the correlated metric, not the source
        # basis or native ordinary consumer. All amplitudes remain full colour.
        return "full"

    @property
    def process_metadata(self) -> Mapping[str, CorrelatedProcessMetadata]:
        return MappingProxyType(self._correlated_processes)

    def generate(
        self,
        processes: ProcessSet,
        output: PathLike[str] | str,
        *,
        model: ModelSource | CompiledModel | None = None,
        mode: str = "error",
    ) -> GenerationResult:
        if mode == "append":
            raise GenerationError("correlated generation does not support append mode")
        for alias in processes.aliases:
            permutation = tuple(alias.particle_permutation)
            if permutation and permutation != tuple(range(len(permutation))):
                raise GenerationError(
                    "correlated generation currently requires identity process aliases"
                )
        self._correlated_processes.clear()
        return super().generate(processes, output, model=model, mode=mode)

    def _prepare_process_construction(
        self, process: CanonicalProcessIR, model: Model
    ) -> _PreparedProcessConstruction:
        if process.color_accuracy != "full":
            raise GenerationError("correlated process expansion must use full colour")
        by_label = {leg.label: leg for leg in process.legs}
        for label in self.declarations.spin_legs:
            leg = by_label.get(label)
            if leg is None or leg.outgoing_pdg is None:
                raise GenerationError(
                    f"spin-correlated leg {label} is absent from {process.process!r}"
                )
            source = model._source_ir(int(leg.outgoing_pdg))
            if (
                source.wavefunction_family != "vector"
                or source.component_dimension != 4
            ):
                raise GenerationError(
                    f"spin-correlated leg {label} requires a full "
                    "four-component vector source"
                )
        plan = build_color_plan(
            process, color_accuracy="full", fold_trace_reflections=False
        )
        if not plan.sectors or plan.truncated:
            raise GenerationError(
                f"process {process.process!r} has no complete colour plan"
            )
        # Within the model's expansion orders, also when nothing is inferred
        # (no tree within them: the request then has no Born).
        limits = request_coupling_order_limits(
            self._coupling_order_limits,
            model,
            policy=self._coupling_order_policy,
            infer=lambda bounds: _infer_minimal_coupling_order_limits_from_color_plan(
                process,
                model=model,
                color_plan=plan,
                max_coupling_orders=bounds or None,
            ),
        )
        require_representable_singlet_exchange(
            process, model=model, max_coupling_orders=limits or None
        )
        return _PreparedProcessConstruction(
            process=process,
            complete_color_plan=plan,
            restricted_color_plan=plan,
            materialized_sector_ids=None,
            coupling_order_limits=MappingProxyType(dict(limits)),
            topology_replay=None,
        )

    def _compile_concrete_process(
        self,
        process: CanonicalProcessIR,
        model: Model,
        *,
        progress_callback: Callable[[Mapping[str, str | int]], None] | None = None,
    ) -> tuple[GenericDAG, dict[str, object]]:
        prepared = self._prepare_process_construction(process, model)
        limits = dict(prepared.coupling_order_limits)
        dag = compile_generic_dag(
            process,
            model=model,
            color_plan=prepared.complete_color_plan,
            max_coupling_orders=limits or None,
            max_quark_pairs=self._max_quark_pairs,
            selected_source_helicities=None,
            selected_color_sector_ids=None,
            online_evaluation_reuse=False,
            backward_live_planning=False,
            lc_all_ordering_symmetry=False,
            closure_side_mask_pruning=False,
            color_order_mask_pruning=False,
            species_reachability_pruning=False,
            progress_callback=progress_callback,
            nc_expansion=self._nc_expansion,
        )
        if dag.truncated:
            raise GenerationError(
                f"process {process.process!r} DAG was unexpectedly truncated"
            )
        if not dag.has_amplitudes:
            raise _NoModelSupportedAmplitudes(
                f"process {process.process!r} has no model-supported "
                "tree-level amplitudes"
            )
        return dag, {
            "key": process.key,
            "process": process.process,
            "color_sector_count": dag.color_plan.sector_count,
            "color_coverage": dag.color_coverage,
            "helicity_coverage": dag.helicity_coverage,
            "source_count": len(dag.sources),
            "current_count": len(dag.currents),
            "interaction_count": len(dag.interactions),
            "interaction_evaluation_count": dag.interaction_evaluation_count,
            "amplitude_root_count": len(dag.amplitude_roots),
            "coupling_order_limits": limits,
        }

    def _prepare_warmup_process_inner(
        self,
        process: _DagProcess,
        model: Model,
        *,
        index: int,
        progress: PhaseHandle,
    ) -> _CompiledProcess:
        # No parity reduction, source-zero discovery, replay or numerical reuse.
        # Even exact identities proved only on physical sources are inapplicable.
        dag = process.dag
        validation = self._generation_config.validation
        sample_count = (
            validation.samples
            if validation.enabled and validation.post_build_validation
            else 1
        )
        points = tuple(
            build_validation_point(
                dag,
                model,
                process_id=process.expanded.request.name,
                seed=validation.seed + index * sample_count + sample_index,
            )
            for sample_index in range(sample_count)
        )
        relation = generic_dag_numerical_current_opt_out_report(
            dag, execution_mode="compiled"
        )
        filters = {
            "structural_helicity_reduction": {
                "applied": False,
                "before_amplitude_roots": len(dag.amplitude_roots),
                "after_amplitude_roots": len(dag.amplitude_roots),
                "mode": "complete correlated source basis",
            },
            "relation_discovery": relation,
        }
        progress.update(2, message="complete correlated source basis retained")
        return _CompiledProcess(
            expanded=process.expanded,
            dag=dag,
            helicity_sum_dag=None,
            helicity_selector_union_dag=None,
            coverage={**process.coverage, "relation_discovery": relation},
            filters=filters,
            validation_points=points,
        )

    def _construct_evaluator(
        self, process: _CompiledProcess, model: Model, phase: PhaseHandle
    ) -> _EvaluatorProcess:
        full_colour_plan = process.dag.color_plan
        result = super()._construct_evaluator(
            replace(process, dag=self._ordinary_consumer_dag(process.dag)),
            model,
            phase,
        )
        if result.helicity_sum_runtime_schema is not None:
            raise GenerationError(
                "correlated generation cannot contain companion or replay lanes"
            )
        # An LC consumer brings the ordinary LC selector lanes; the correlated
        # executor selects its coherent groups itself, without them.
        result = replace(result, helicity_selector_lanes=(), color_selector_lanes=())
        # Full source coverage does not promise the separate native per-point
        # selector ABI.  This lane deliberately has no selector/recurrence
        # schedules; the correlated executor selects its coherent groups itself.
        payload = result.runtime_schema.to_mapping()
        physics = dict(cast(Mapping[str, object], payload["physics"]))
        extensions = dict(cast(Mapping[str, object], physics.get("extensions", {})))
        extensions.pop("runtime_selectors", None)
        physics["extensions"] = extensions
        payload["physics"] = physics
        schema = RuntimeExpressionSchema.from_mapping(payload)
        result = replace(
            result,
            runtime_schema=schema,
            stage_input=replace(result.stage_input, runtime_schema=schema),
        )
        self._correlated_processes[process.expanded.request.name] = (
            CorrelatedProcessMetadata(
                process=process.dag.process,
                color_plan=full_colour_plan,
                runtime_schema=result.runtime_schema,
                aliases=process.expanded.aliases,
            )
        )
        return result

    def _ordinary_consumer_dag(self, dag: GenericDAG) -> GenericDAG:
        """The full-colour amplitudes contracted at the requested accuracy.

        Every amplitude stays full colour (the correlators need them); the
        artifact's ordinary value -- Runtime.evaluate and every native
        consumer -- is the requested accuracy's, as for an ordinary artifact.
        NLC contracts the same sectors with the NLC colour matrix."""

        requested = (
            str(self._run_config.color.accuracy)
            if self._run_config is not None
            else "full"
        )
        if requested == "full" or self._nc_expansion is not None:
            return dag
        process = replace(dag.process, color_accuracy=requested)
        plan = replace(dag.color_plan, process=process, color_accuracy=requested)
        if requested == "lc":
            # The LC metric of the complete plan is diagonal on the sectors
            # whose amplitudes the trees build (the canonical owners; their
            # block-permutation aliases carry none): LC is their diagonal.
            owners = {
                int(root.color_sector_id)
                if root.color_sector_id is not None
                else int(dag.currents[root.left_id].index.color_state.sector_id)
                for root in dag.amplitude_roots
            }
            plan = replace(
                plan,
                sectors=tuple(
                    sector for sector in plan.sectors if int(sector.id) in owners
                ),
            )
        return replace(dag, process=process, color_plan=plan)

    def correlator_payload(self) -> dict[str, object]:
        """Build the declared exact matrices once, at the ordinary write boundary."""

        processes: dict[str, object] = {}
        any_zeros = False
        for process_id, metadata in self._correlated_processes.items():
            declarations = self.declarations._resolve_color(
                process_color_legs(metadata.process)
            )
            amplitude = cast(
                Mapping[str, object],
                metadata.runtime_schema.to_mapping()["amplitude_stage"],
            )
            groups = cast(Sequence[Mapping[str, object]], amplitude["coherent_groups"])
            basis_by_helicity: dict[tuple[int, ...], set[int]] = {}
            grades_by_sector: dict[int, set[int]] = {}
            for group in groups:
                helicities = tuple(cast(Sequence[int], group["helicities"]))
                sector_id = cast(int, group["color_sector_id"])
                basis = basis_by_helicity.setdefault(helicities, set())
                basis.add(sector_id)
                grades_by_sector.setdefault(sector_id, set()).add(
                    cast(int, group.get("nc_grade", 0))
                )
            if not basis_by_helicity:
                raise GenerationError("correlated amplitudes have no coherent groups")
            owners: set[int] = set().union(*basis_by_helicity.values())
            zeros = _certified_zero_groups(
                basis_by_helicity, owners, self.declarations, process_id
            )
            # Open-line colour plans retain aliases whose amplitudes already
            # belong to canonical owners.  Never contract those aliases twice.
            expansion = self._nc_expansion
            matrices = build_color_correlator_matrices(
                metadata.color_plan,
                declarations.color_requests,
                sector_ids=sorted(owners),
                color_accuracy=cast(
                    Literal["lc", "nlc", "full"],
                    self._color_accuracy
                    if expansion is not None
                    else self._run_config.color.accuracy
                    if self._run_config is not None
                    else "lc",
                ),
                nc_expansion=expansion,
            )
            # The runtime multiplies every correlated value by the artifact's
            # normalization, whose colour factor is the leading-colour one when
            # the ordinary consumer is LC (its diagonal reduction carries no
            # colour factor); the stored entries, which include their colour
            # factor, are divided by it so that the product is unchanged.
            colour_normalization = _ordinary_colour_normalization(
                metadata.runtime_schema
            )
            if colour_normalization != 1:
                matrices = tuple(
                    replace(
                        matrix,
                        entries=tuple(
                            replace(
                                entry,
                                weight=entry.weight.scaled(
                                    Fraction(1, colour_normalization)
                                ),
                            )
                            for entry in matrix.entries
                        ),
                    )
                    for matrix in matrices
                )
            records = [matrix.to_json_dict() for matrix in matrices]
            if expansion is not None:
                for record in records:
                    record["nc_expansion"] = _with_reported_degrees(
                        cast(Mapping[str, object], record["nc_expansion"]),
                        cast(Sequence[Mapping[str, object]], record["entries"]),
                        grades_by_sector,
                        expansion,
                    )
            process_record: dict[str, object] = {
                "declarations": declarations.to_json_dict(),
                "spin_legs": list(declarations.spin_legs),
                "matrices": records,
                # The native execution schema keeps root group IDs but omits
                # these compiler descriptors, needed only by this consumer.
                "coherent_groups": groups,
            }
            if zeros:
                process_record["zero_coherent_groups"] = zeros
                any_zeros = True
            processes[process_id] = process_record
        # Schema 2 only adds the certified zero groups; an artifact without
        # them keeps schema 1, byte for byte, for every released reader.
        version = CORRELATOR_ZERO_GROUPS_SCHEMA_VERSION if any_zeros else 1
        return {
            "schema_version": version,
            "complete_source_basis": True,
            "declarations": self.declarations.to_json_dict(),
            "processes": processes,
        }

    def _write_correlator_payload(
        self, builder: ArtifactBuilder
    ) -> Mapping[str, object]:
        payload = self.correlator_payload()
        builder.add_json(CORRELATOR_PAYLOAD_PATH, payload, role="runtime-physics")
        return {
            "correlators": {
                "schema_version": payload["schema_version"],
                "path": CORRELATOR_PAYLOAD_PATH,
            }
        }

    def _write_artifact(self, *args: object, **kwargs: object) -> ArtifactWriteResult:
        # A caller's payload hook (the loop service's skipped members) is
        # composed with the correlator payload.
        extra = kwargs.pop("payload_hook", None)

        def payload(builder: ArtifactBuilder) -> Mapping[str, object]:
            out = dict(self._write_correlator_payload(builder))
            if callable(extra):
                out.update(extra(builder))
            return out

        return super()._write_artifact(*args, **kwargs, payload_hook=payload)


def _ordinary_colour_normalization(schema: RuntimeExpressionSchema) -> int:
    """The colour factor of the ordinary consumer's normalization: 1 when its
    contraction carries the colour factors (NLC, full colour), the
    leading-colour factor (a power of N_c) for an LC consumer."""

    payload = schema.to_mapping()
    physics = cast(Mapping[str, object], payload["physics"])
    if str(physics.get("color_accuracy")) != "lc":
        return 1
    normalization = cast(Mapping[str, object], payload.get("normalization", {}))
    factor = float(cast(float, normalization.get("color_factor", 1.0)))
    if factor < 1 or factor != int(factor):
        raise GenerationError(
            f"leading-colour normalization factor {factor!r} is not an integer"
        )
    return int(factor)


def _certified_zero_groups(
    basis_by_helicity: Mapping[tuple[int, ...], set[int]],
    owners: set[int],
    declarations: CorrelatorConfig,
    process_id: str,
) -> list[dict[str, object]]:
    """The (helicity, colour sector) amplitudes that are exactly zero.

    The complete source basis keeps a coherent group for every retained
    helicity and colour sector that has diagrams.  A pairing of quark lines
    joined only by colour-neutral exchanges has diagrams only at the
    helicities that keep each of its massless lines at one chirality (for a
    W, the left-handed one): elsewhere that sector's amplitude is an exact
    zero, decided when the DAG was built (the chirality selection; a decision
    that rests on a coupling zero only at the generation values of runtime
    parameters is covered by the guards recorded for it).  The correlator
    matrices span every owner sector; readers take a listed group as an exact
    zero and refuse any other gap.

    A replaced spin leg evaluates one placeholder helicity per spectator
    configuration, so that leg's helicity must not decide which sectors
    vanish; otherwise the placeholder would drop a live amplitude.
    """

    zeros = sorted(
        (helicities, sector)
        for helicities, basis in basis_by_helicity.items()
        for sector in owners - basis
    )
    for legs in declarations.spin_correlations:
        patterns: dict[tuple[int, ...], set[int]] = {}
        for helicities, basis in basis_by_helicity.items():
            spectator = tuple(
                value for leg, value in enumerate(helicities, 1) if leg not in legs
            )
            pattern = patterns.setdefault(spectator, set(basis))
            if pattern != basis:
                raise GenerationError(
                    f"spin correlation on legs {list(legs)} of {process_id!r} is "
                    "not available: the helicity of a replaced leg decides which "
                    "colour sectors have amplitudes"
                )
    return [
        {"helicities": list(helicities), "color_sector_id": sector}
        for helicities, sector in zeros
    ]


def _with_reported_degrees(
    record: Mapping[str, object],
    entries: Sequence[Mapping[str, object]],
    grades_by_sector: Mapping[int, set[int]],
    expansion: NcExpansion,
) -> dict[str, object]:
    """The matrix's expansion record with the N_c degrees it reports: the
    degree window of a strict truncation, or for the graded full colour every
    degree from P down to the lowest reachable one (p + g_l + g_r over the
    entries and the grades of their sectors' amplitude groups)."""

    reference = cast(int, record["reference_degree"])
    depth = expansion.depth
    if depth is None:
        reachable = [
            cast(int, entry["nc_power"]) + left + right
            for entry in entries
            for left in grades_by_sector.get(cast(int, entry["left_sector_id"]), {0})
            for right in grades_by_sector.get(cast(int, entry["right_sector_id"]), {0})
        ]
        lowest = min(reachable, default=reference)
    else:
        lowest = reference - depth
    return {**record, "degrees": list(range(reference, lowest - 1, -1))}


def generate_correlated(
    processes: ProcessSet,
    destination: str | Path,
    *,
    declarations: CorrelatorConfig,
    config: GenerationConfig | RunConfig | ConfigResolution | None = None,
    progress: ProgressSink | None = None,
    model: ModelSource | CompiledModel | None = None,
    mode: Literal["error", "append", "replace"] = "error",
) -> GenerationResult:
    return CorrelatedGenerationBackend(
        config, progress, declarations=declarations
    ).generate(processes, destination, model=model, mode=mode)
