# Gate-G1 benchmark (`python -m tools.loop_benchmark`)

End-to-end timing of the v2 one-loop engine against MadLoop, Recola and
OpenLoops under the speed-gate protocol (REQUIREMENTS_ADDENDUM D, MASTER_PLAN
§5.8): finite part only, stability checks off, one pinned thread, the same
frozen phase-space points for every tool.

| Module | Role |
|---|---|
| `processes.json` | Process specifications in the required-references format (`tools/loop_reference/required_processes.json`, scheme `qcd` = loop_sm-no_b_mass). |
| `streams.py`, `streams/` | Frozen streams of 128 distinct exact points per process; the first three are the reference campaign's. |
| `pyamplicol_v2.py` | pyAmpliCol v2 through `NativeExecutor.evaluate` (the public v2 runtime's call): generation time and memory, the accuracy check at the campaign points (untimed, against the fixture's providers at its tolerance: binary64 where the finite part's O1 estimate E <= 1e-9, `mqcd.O1_CAP`, else a double-double evaluation of the point, with E and the binary64 errors recorded; the user's ruling of 2026-10-29 on E1), per-batch timings with the stage split (Python per-point inputs, the native report's stages, master integrals), and `stability` estimates at chosen points. |
| `providers.py` | MadLoop, Recola and OpenLoops in production mode through the toolkit's drivers; optionally MadLoop's stage split from an instrumented copy. |
| `gate.py` | Combines the records into `docs/performance_reports/loop/data/g1.json`: gate verdicts, value comparison, cost-model recalibration. |
| `mqcd.py` | The M-QCD validation campaign (m-qcd/PLAN.md §1.4, §4): the row manifest `tests/fixtures/loop/mqcd/manifest.json`, reference adapters, generation per row (shared by carriers, points and checks), the acceptance rules 1-6 (the O1 estimate is `loops.v2.stability.RECOMMENDED_CHECKS`; rule 4 on the native-input rows takes the tree engine's committed colour correlations, `mqcd_tree_correlations.py`, `tests/fixtures/loop/mqcd/references/tree-correlations-<row>.json`), the extras (`ap`, `uv`, `hel`, `sp` through the special-point variants, `ward` through `loops.v2.ward.ward_check` on the native input path, `ff` D01's analytic quark form factor, the H rows' CKM relation; `nc` is MQ-NC's rule 7 test ids per row, manifest `nc_column` once `mqcd_manifest.MQNC_LANDED`, read by `build_mqcd.py --junit` from their JUnit XML, pending MQ-NC until then), M01 as a composite row (each MadLoop P reference against the subprocess's own generation and, `route: public`, against the public route's multiparticle artifact; MQ-MODEL's bitwise test as a `delegated` column; `delegated-ids` lists the delegated pytest ids), MQ-REF's per-point reference records (a point without a provider reference runs rules 2-4 only) and the restriction smokes; `python -m tools.loop_benchmark.mqcd run ROW... --ufo LOOP_SM --work DIR [--results DIR]` outside pytest. `mqcd_manifest.py` writes the manifest (the PLAN rows, MQ-REF's reference index, the rules' listings and the per-row tolerances the user's ruling of 2026-10-29 ~10:20 relaxes, with their evidence; binary64 points outside the O1 scope are reported by the records, not listed). The tiers are `tests/unit/test_loop_v2_mqcd_{manifest,default}.py` and the nightly file jobs `test_loop_v2_mqcd_nightly{,_2,...,_7}.py` (manifest `nightly_jobs`: rows packed by measured cost, each job within 30 min; shared bodies in `tests/unit/loop_mqcd_tiers.py`); `docs/performance_reports/loop/scripts/build_mqcd.py` turns the per-row records into `data/mqcd.json` (with the curated triage `data/mqcd-findings.json` and a per-row markdown table). |
| `msm_manifest.py` | The M-SM validation campaign (m-sm/PLAN.md §1.4, §4) on the same harness: `msm_manifest.py` writes `tests/fixtures/loop/msm/manifest.json` (PLAN §4.2's 70 core rows and MS-UFODB's SC10 in the M-QCD record type, plus per row the model (§4.1 model codes: the G_mu and alpha(M_Z) UFOs, conftest fixtures in the manifest's `models`), the corrections, the loop amplitude orders derived from the sectors and the Born amplitude orders, the loop coupling per correction for F_s, the expected sectors with typed unpredicted reasons, the R2 rule's `madloop_omitted_r2`, the couplings the reference's MadLoop export calls (`madloop_r2_called`) and the package a pending row waits for; once MS-REF's `required/msm_references.json` is on the branch a row takes its first binding run (with the run's rule-5 components and MG5's alpha(0) conversion per point over the run's tagged photons), its further binding runs become special-point variants `<row>@<suffix>` and a top-up run of another sector joins the existing reference as a per-sector `sectors` reference at the existing points; the script writes each nightly file job's thin entry point). `mqcd.py` runs it: F_s per correction (`sector_flux`), rule 4 on the engine's QCD and QED operators with the typed reasons (`rule4_reasons`; native-input rows `catani: "engine"`, the operators on the Python-input Born), rule 5's EW component form (`rule5_components`, MadLoop's Born x CT split), the R2 rule (`rule_r2`: Recola primary or MadLoop plus its omitted R2 component, the `madloop-components` reference; found structurally: the R2 couplings of the engine's admitted rules whose vertex a tree of the export's sectors can hold, `r2_reachability` over `r2_export_sectors` (production's colour-blind `InsertionReachability`), less the row's listed vanishing insertions `r2_vanishing` and those whose MG5 identical-coupling class, `r2_value_classes`, the export calls, must equal the row's `madloop_omitted_r2`), the `joint` extra (`rule_joint`: the joint request = the separate requests per loop order), the `ward` extra at a row's `ward_parameters` (in the real-mass scheme the gluon/photon Ward identity holds only where no external coloured/charged particle has an absorptive self-energy at its mass: the top-pair rows run it at MW = 180, MZ = 200; rows with an external W leave it to CMS), MG5's alpha(0) conversion of raw MadLoop over the tagged photons (`photon_conversion`; a row's `external_photons` is its request's `loop.external_photons`, and a variant with other tags, PI01's `@all` twin, generates its own slice), the EW reference formats (`ew-control`, `madloop-components`, `process-components`, `sectors`) and a row whose generation or evaluation raises recorded as failed (`Campaign.record`: one `eval` check holding the error), the complex-mass rows (a row's `mass_scheme`: its model transformed by `model_cms.complex_mass_model` at its fixed parameters, `Campaign.row_model`; CM01's MadLoop CMS controls in the `cms-control` format; the Ward extra a diagnostic under CMS, `diagnostic_extras`), the multiparticle rows MP01, MP02 (composite, as M-QCD's M01: the photon in p through `multiparticles`, the expansion against MadLoop's P directories up to the members without a Born, which the public route's dry run skips typed `loop-induced`, `multiparticle_members`; one subprocess variant per P reference), the `campaign` tier (the 2->5 target, CM07; `run ... --tier campaign --manifest tests/fixtures/loop/msm/manifest.json --model-ufo NAME=PATH`). The tiers are `tests/unit/test_loop_v2_msm_{manifest,default}.py` and `test_loop_v2_msm_nightly{,_2,...}.py`; `build_mqcd.py --manifest tests/fixtures/loop/msm/manifest.json --output data/msm.json --findings data/msm-findings.json --junit <xml>...` writes the report data (`msm-findings.json`: the campaign's findings, their fixes or routing; `--junit`: the JUnit XML of the rows' `delegated` columns, rule 5's epsIR = 0 check on DY01 and TT01 being MS-POLES's technical-card split tests in `test_loop_v2_ew_pole_split.py`). `processes.json`'s `gg_ttxemepg_ew` (scheme `ew-gmu`) is the indicative G1 EW row ([U5]). |

Typical campaign (one of our jobs per CCX on cores without SMT siblings; the
host is shared, so others' jobs are not controlled):

```sh
python -m tools.loop_benchmark streams uux_emepgg            # freeze a new stream
python -m tools.loop_benchmark pyamplicol uux_ddxg --batches 1 8 32 128 --reps 3 \
    --native-build BUILD_DIR --json runs/uux_ddxg.json          # integrated slice
python -m tools.loop_benchmark pyamplicol uux_ddxg --inputs native ...   # WP3.1 path
python -m tools.loop_benchmark providers uux_ddxg --cpu 153 --points 16 \
    --work WORK_DIR --reference-root ROOT --json runs/providers-uux_ddxg.json [--madloop-stages]
python -m tools.loop_benchmark stability gg_ggg --points 10 --inputs native \
    --arithmetic double double-double --json runs/stability-gg_ggg.json
python -m tools.loop_benchmark gate runs/*.json --json docs/performance_reports/loop/data/g1.json \
    --values-json docs/performance_reports/loop/data/g1-values.json --reference-root ROOT \
    --meta date=... slice_revision=... native_revision=... native_commit=... slice_build=... native_build=...
python tools/loop_v2_costmodel.py --g1 docs/performance_reports/loop/data/g1.json
```

`ROOT` is the provider reference root (`$LOOP_REFERENCE_ROOT`, toolkit
layout: `sources/MG5_aMC_v3_7_0`, `sources/recola2-2.3.0`,
`sources/OpenLoops-2.1.5`, MadLoop exports at `madloop.export` of
`processes.json`). The gate resolves every provider file relative to it:
a record's `export` (the absolute path of its run, possibly under a root
that moved) is never opened or stat'ed; its `runs/...` part under `ROOT`,
else the specification's `madloop.export`, is the export (an imported
campaign timing, `timing` of the specification, names none: its generation
is that of the specification's export). An imported timing outside the
protocol (`protocol_mode` false) is never a gate limit; where it does the
production work and more (a Recola run that also evaluates the IR poles,
with the protocol's Collier cache or without one) the import records
`production_upper_bound`, and the report takes it as an upper bound of that
provider's production time (u u~ > g g g g g: the ratio to the fastest
provider is then a lower bound). A new process needs only its specification in
`processes.json` (PDG codes, orders, provider process strings, `madloop.export`
or `unavailable` reasons) and its stream: particle names come from the model,
labels from the specification, and the gate refuses records of unknown
processes. The gate statistic is the median per point on both sides with an
uncertainty band. The gate is taken at batched B = 128 only (`GATE_BATCH`;
the user's rule of 2026-10-28, slice-status DECISIONS ~08:20 item 2,
MASTER_PLAN §5.8 amendment): every other timed batch (B = 1, the 2->5 rows'
B = 16, any other) keeps its checks, ratios, band and uncertainty with the
non-gating status `reported` (and `gate_batch`: 128), the checks' own verdict
as `measured_status`. A configuration's G1 verdict
(`gate` of the configuration in `g1.json`) is its B = 128 one; without a
B = 128 timing it is `missing`, with the reason, never one taken from another
batch. A pyAmpliCol B = 128 time below 5 ms per point is not gated (the
user's rule of 2026-10-24: verdict `below 5 ms: not gated (user
2026-10-24)`, the checks and ratios kept, their own verdict as
`measured_status`); `open` verdicts are repeated once (MASTER_PLAN §5.8 item 10);
the record given last for a configuration or provider decides, earlier runs
are kept.

A specification may carry `particle_veto` (the request's public veto:
g g > g g g g g without the top is NJet's massless five-flavour QCD) and
`reference_fixture` (the fixture the run's accuracy check uses, at its own
points and scales, e.g. `gg_ggggg_njet`; only the quantities a fixture
entry states are compared: NJet's `catani` entry has a Born and the poles,
no finite part). For the seven-leg rows,
`--warm-up 16` limits each B's untimed warm-up to one chunk of lanes (it
compiles every kernel), every block prints its time and the record is
written after every round; `--physical-points` (every pole, one batch)
checks the virtual's double pole over the Born against the universal
-(alpha_s/2pi) sum C_i at the run's colour accuracy, and `ward --physical`
gives a Ward run its own physical scale.

A generation that takes about an hour (g g > g g g g g) is stored once and
timed in bounded jobs: `pyamplicol KEY --store DIR --generate-only` writes
the process as the artifact's loop runtime member with its native point
inputs (`artifact.write_plan`, `point_inputs` = `LOOP_V2_NATIVE_POINT_INPUTS`,
"native-v2" since `7db32901`) beside
`generation.json`, and `pyamplicol KEY --load DIR ...` (or `stability KEY
--load DIR ...`) reads it as `V2VirtualRuntime` loads an artifact (nothing
regenerated; the values equal the generating run's bitwise) and times that
executor. The record keeps the stored generation and states the load
(`stored`: directory name, plan digest, the generating revision); a store is
never overwritten, a load of another configuration or native build is
refused, and a `--generate-only` record is no gate input.

`stability KEY --fixture --points I...` evaluates the reference fixture's
own points (the accuracy check's: e.g. NJet's ten seven-gluon points at
mu_R = 1000 GeV, of which only the first three are stream points, at other
scales) with the same checks, each row with its finite part's deviation
from every reference of the fixture (`deviation_vs_references`). The gate
keeps these rows apart (`fixture_stability`), and the report builder takes
the binary64 estimate and the double-double deviation at the fixture's worst
point from them.

Run the `pyamplicol` jobs under `taskset -c N` with `RAYON_NUM_THREADS=1`.
Respect HANDOFF §0.1 for provider generations (no generation expected to
exceed about 45 minutes).

Provider caches are those of production (REQUIREMENTS_ADDENDUM D):
`providers.collier_cache` switches the COLLIER global cache off only at
seven legs or more and only for a linked release with the documented N = 7
cache defect (`COLLIER_CACHE_DEFECT`: 1.2.9, 1.2.10). Recola links COLLIER
1.2.8 (cache on at every multiplicity); MadLoop's HEPTools COLLIER is 1.2.9
(`COLLIERGlobalCache 0` at seven legs); every provider record states the
decision and the release (`collier_cache`).

TRANSITIONAL (until package reference-relocate fixes the reference trees,
slice-status DECISIONS 2026-10-25 ~20:45 item 2): the reference trees still
name files of the root they were built under (the MadLoop exports'
`LOOP_LIBS` archives, the RUNPATH of `librecola.so` and `libmodelfile.so`,
OpenLoops' compiled-in installation path), so every `tools/loop_reference`
run of the toolkit itself still reads the old root. The harness never opens
those: `providers.relocated` takes each from the same place under `ROOT`
(MadLoop links the relocated archives; Recola's driver links with
`-rpath-link` and runs with `LD_LIBRARY_PATH` set to the relocated RUNPATH,
and a run whose resolved libraries lie outside `ROOT` is refused; OpenLoops
runs with `OpenLoopsPath`). A provider run under `strace -f -e trace=file`
accesses nothing outside the current root's trees
(`workspace/reports/engine-v2/measure-g1-7leg/records/logs-f4/`). Once the
trees name the current root (patched RUNPATHs and makefile definitions,
OpenLoops' path, with a strace proof for all three providers), this
workaround is retired: `relocated`, `library_path`, `loaded_libraries`,
`_elf_dynamic`, `_environment` and `_relocated_madloop_build` go with
`test_files_of_a_moved_root_are_taken_under_the_current_root`; the
reference-root resolution of the records' export paths and the strace check
stay.

Accepted deviation (user decision of 2026-10-25, slice-status DECISIONS
~20:05; not a defect): g g > g g g g g against NJet, binary64, points 4
(3.7e-8 from NJet's double-double value) and 8 (2.2e-8) of the fixture's
ten, above its 2e-8 tolerance, are "accepted (user 2026-10-25): O(1e-8)
binary64, within the estimate, DD = NJet": both lie within pyAmpliCol's own
binary64 estimate E (1.3e-6, 2.5e-7) and the double-double values equal
NJet's double-double values; the points are not timed stream points. Since
the user's ruling of 2026-10-29 on E1 the run's accuracy check asserts
these points (E > 1e-9) in double-double at the unchanged 2e-8 tolerance,
their binary64 errors recorded beside; the acceptance of the binary64
deviations lives in `docs/performance_reports/loop/data/milestone.json`
(`validation_decisions`), and the report builder checks its claims against
`g1.json` and marks the points (`summary.json` `validation.accepted`).
