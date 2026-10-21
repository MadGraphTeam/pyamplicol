# One-loop reference controls

These small controls compare the Born–loop interference for
four-quark scattering, photon-only Drell–Yan, stable top-pair production and
gluon scattering. The QCD cases select Born/loop coupling powers 2/4. They are an
independent reference harness, not a pyAmpliCol loop implementation or a
performance acceptance campaign. The initial control uses binary64; it does
not establish DoubleFloat or arbitrary-precision support.

All provider sources, downloads, builds, logs and run directories belong in
the task's `workspace`. Keep the supplied `FOR_REFERENCE_ONLY` sources read-only.
The scripts accept paths and do not depend on the original task location.

The local two-vector CT tensor oracle can reuse the three `R2_GG_*_0.f`
ALOHA routines in the generated four-quark MadLoop build:

```bash
python3 tools/loop_reference/ct_tensor_oracle.py \
  --ufo "$LOOP_REFERENCE_ROOT/sources/MG5_aMC_v3_7_0/models/loop_sm" \
  --madloop-build "$LOOP_REFERENCE_ROOT/builds/madloop-uudd" \
  --build-dir "$LOOP_REFERENCE_ROOT/builds/ct-local-aloha" \
  --output "$LOOP_REFERENCE_ROOT/runs/ct-gluon-two-point-tensor.json"
```

Run in a licensed Symbolica environment. The oracle compiles isolated copies
of those routines into its own shared library; it never modifies their source.
Its 102 real/complex off-shell polarization checks validate only the local
Lorentz structures. Scalar CT normalization and physical process assembly need
separate controls. The independent ALOHA comparison uses binary64.

For an isolated top-pair external-field component report containing the
reference `born` and `wf` Laurent columns, run:

```bash
python3 tools/loop_reference/wavefunction_oracle.py \
  --ufo "$LOOP_REFERENCE_ROOT/sources/MG5_aMC_v3_7_0/models/loop_sm" \
  --reference "$LOOP_REFERENCE_ROOT/runs/top-pair-component-control.json" \
  --output "$LOOP_REFERENCE_ROOT/runs/top-pair-field-factor-oracle.json"
```

This derives the model's external-field factors, retains the two physical top
legs, and evaluates their interference factors in one native batch. The Born
values come from the reference. It tests field normalization/multiplicity and
scalar execution; it does not validate an independently computed Born amplitude.

The active four-gluon R2 local tensor control uses the gluon-scattering export:

```bash
python3 tools/loop_reference/four_gluon_oracle.py \
  --ufo "$LOOP_REFERENCE_ROOT/sources/MG5_aMC_v3_7_0/models/loop_sm" \
  --madloop-build "$LOOP_REFERENCE_ROOT/builds/madloop-gluon-scattering" \
  --mg5-source "$LOOP_REFERENCE_ROOT/sources/MG5_aMC_v3_7_0" \
  --build-dir "$LOOP_REFERENCE_ROOT/builds/ct-four-gluon-aloha" \
  --output "$LOOP_REFERENCE_ROOT/runs/ct-four-gluon-r2-oracle.json"
```

It checks all four Lorentz structures of active `V_R2RGA` with 256 component
polarizations and four complex polarization configurations each. Momenta are
off shell and conserved, and no polarization transversality is imposed. The
12 active colour bases and two complex ordered-trace probes give 196 exact
overlaps checked against MadGraph's own UFO importer and reduced trace-basis
colour matrix. Native SU(3) components and contractions come from Community;
the script implements no colour identities. This controls all 57 active local
basis entries but does not validate scalar coefficients, a whole process or
general-Nc continuation. The commented alternative four-gluon rule is unused.

## Provider versions and acquisition

* MadLoop: copy the supplied MG5_aMC 3.7.0 tree into the workspace.
* Recola: copy the supplied Recola2 2.3.0 tree into the workspace.
* OpenLoops: clone the [official repository](https://gitlab.com/openloops/OpenLoops)
  at tag `OpenLoops-2.1.5`, commit
  `8238fa2c2bf5408e2402e6aa1b786f392fe735b9`.
* Recola model: [SM 2.2.3](https://recola.hepforge.org/downloads/?f=SM_2.2.3.tar.gz).
  This is the conventional Feynman-gauge QCD/EW model, with diagonal CKM.
* Recola integrals: [Collier 1.2.8](https://collier.hepforge.org/downloads/?f=collier-1.2.8.tar.gz).
* Full EW UFOs: the official MadGraph model database supplies
  [loop_qcd_qed_sm](https://madgraph.mi.infn.it/Downloads/models/loop_qcd_qed_sm.tgz)
  and [loop_qcd_qed_sm_Gmu](https://madgraph.mi.infn.it/Downloads/models/loop_qcd_qed_sm_Gmu.tgz).
  These are subsequent EW-validation inputs, not inputs to this QCD control.

Build Collier, then the Recola SM model, then Recola with CMake. Pass
`-Dcollier_path=...` to the latter two builds, and `-Dmodelfile_path=...` to
Recola. Old Collier/model CMake files require
`-DCMAKE_POLICY_VERSION_MINIMUM=3.5` with CMake 4. Use source copies inside
the workspace because these projects put libraries/modules in their source
directories even when configured with a separate build directory.

Build OpenLoops with `python3 scons -j4`, then install its small `ppjj`
process library with `bash openloops libinstall ppjj -j4`. Explicit `bash`
also works on Nix systems without `/bin/bash`. Its bundled Collier is
separate from the Recola installation.

Generate the MadLoop control by running this card in the copied MG tree,
substituting an absolute workspace path for `OUTPUT`:

```text
set automatic_html_opening False
set auto_update 0
set output_dependencies internal
import model loop_sm-no_b_mass
set gauge Feynman
generate u u~ > d d~ QED=0 [virt=QCD]
output standalone OUTPUT -f
```

This initial standalone export uses bundled CutTools/IREGI. Its purpose is
independent correctness validation. The eventual MadLoop performance
baseline must also enable its supported optimized reduction libraries;
timings from this control do not establish that baseline.

For the photon-only Drell–Yan control, replace the `generate` line with
`generate u u~ > e- e+ / z QCD=0 QED=2 [virt=QCD]` and use a separate
workspace output. Build with `--case drell-yan --madloop OUTPUT` and/or
`--recola RECOLA_SOURCE`; run with
`--fixture tools/loop_reference/drell_yan_qcd.json --providers madloop recola`.
The Recola bridge uses its public `switchoff_coupling3_rcl('Z','e-','e+')`
before generation to remove Z exchange, sets a massless electron, and selects
Born/loop powers zero/two in the strong coupling. Both providers set the inverse
electromagnetic coupling explicitly (132.507 by default). The Born and all
three Laurent coefficients agree with the independent form factor below at
all three fixture points and at renormalization scales 1000 and 700 GeV.
The matched photon-only OpenLoops library remains unavailable in this suite;
this restriction is not a claim about either provider's ordinary Drell–Yan
capability.

For stable top-pair production, use `generate u u~ > t t~ QED=0 [virt=QCD]`
and another standalone output. Install the OpenLoops `pptt` library and build
all providers with `--case top-pair`. Run with
`--fixture tools/loop_reference/top_pair_qcd.json`. Its three decimal-input
points satisfy the massive on-shell and momentum-conservation relations exactly;
the final point lies near threshold. The public `pptt` source acquired for this
control has revision `e4668fa` (2020-06-23, process API 2).

For gluon scattering, use `generate g g > g g QED=0 [virt=QCD]`, build with
`--case gluon-scattering`, and run with
`--fixture tools/loop_reference/gluon_scattering_qcd.json`. OpenLoops' `ppjj`
library already supplies this channel. Use `set output_dependencies external`
when generating the MadLoop export to retain installed Ninja/Collier libraries;
all their sources and builds must still live in the workspace. `build.py` reads
the export's static-library list, so it links the reducers actually generated.
The earlier internal-dependency CutTools-only export showed finite-term errors
of several parts in 10^9 at these points, even after its own precision rescue.
The external-dependency export with Ninja/Collier enabled agrees with the other
two providers. This observation is specific to the recorded control, not a
general accuracy claim about any reduction library.

For quark annihilation into gluons, generate
`u u~ > g g QED=0 [virt=QCD]` with the same external dependencies, build with
`--case quark-gluon`, and run with
`--fixture tools/loop_reference/quark_gluon_qcd.json`. OpenLoops' existing
`ppjj` library supplies this channel too.

For the first five-leg control, generate
`u u~ > g g g QED=0 [virt=QCD]`, install OpenLoops `ppjjj`, build with
`--case quark-three-gluon`, and run with `quark_three_gluon_qcd.json`.
The three finite-decimal points are exact massless, momentum-conserving
rational rotations of a three-body configuration. Born/loop coupling powers
are 3/5 and the interference has squared QCD order 8. All three final gluons
are identical: the normalization is `1/(4*9*6)=1/216`. Independent provider
controls agree on Born and all three coefficients. The double-pole control is
`-(2*CF+3*CA)*alpha_s/(2*pi)*Born`; it uses the measured Born and does not
supply an independent five-leg Born formula. This validates the references,
not an implemented pyAmpliCol five-leg process or a performance gate.

The native drivers retain four external legs and Born power 2 by default;
five-leg builds select both dimensions and powers explicitly. The MadLoop
Fortran boundary takes its external count from the generated `nexternal.inc`.
`--case five-gluon` also supplies the native `g g -> g g g` registration,
but it has no validated fixture in this checkpoint.

The native MadLoop bridge requests relative accuracy `1e-11` for correctness
controls (the generated card otherwise defaults to `1e-3`). Rescue remains
inside the timed call. Fixed mass, width and electromagnetic inputs are bound
to both double and multiprecision model storage before recomputing couplings;
MadLoop's running-parameter updater only synchronizes the strong coupling and
scale. These controls still use binary64 external inputs and outputs.

The Gmu UFO initially uses Python 2 imports/`iteritems`. For normal Python
package loading, make a separate workspace copy, run MG's `convert model
ABSOLUTE_COPY_PATH`, then `python3 -m lib2to3 -w -n -f import COPY_PATH`
using Python 3.11. This preserves the original model and only converts the
compatibility copy. The nominal-alpha UFO already supports package imports.

## Build and run the native controls

Set `LOOP_REFERENCE_ROOT` to the workspace reference directory, and invoke
from the checkout containing this harness. Provider/library paths can differ:

```bash
python3 tools/loop_reference/build.py \
  --openloops "$LOOP_REFERENCE_ROOT/sources/OpenLoops-2.1.5" \
  --recola "$LOOP_REFERENCE_ROOT/sources/recola2-2.3.0" \
  --madloop "$LOOP_REFERENCE_ROOT/builds/madloop-uudd-5f" \
  --output-dir "$LOOP_REFERENCE_ROOT/builds/controls"

python3 tools/loop_reference/run.py \
  --bin-dir "$LOOP_REFERENCE_ROOT/builds/controls" \
  --madloop-dir "$LOOP_REFERENCE_ROOT/builds/madloop-uudd-5f" \
  --output-dir "$LOOP_REFERENCE_ROOT/runs/uudd-controls"
```

`build.py` can build individual providers by omitting the other arguments.
`run.py --providers recola openloops` selects a subset explicitly. A single
provider run checks analytic controls but cannot establish provider agreement.

Each executable reads one complete batch on stdin, initializes its provider,
warms the batch, and evaluates the timed repetitions in native C++ loops.
There is no Python call per phase-space point. Recola's Fortran bridge uses
the public API because the supplied 2.3.0 C++ header contains unrelated
missing declarations. MadLoop uses its native `OLP_static` target, avoiding
the generated optional f2py targets. Neither workaround changes provider
physics source.

The default run checks the three fixture points and batch sizes 1, 8, 32,
128. Larger batches cycle the control points; these are lane-consistency
checks, not a realistic timing distribution. Inputs and output serialization
are outside the native evaluation timer. Provider logs and a JSON report
are written under the requested output directory.

## Physics contract

The fixture fixes six quarks in loops, five active renormalization flavours,
massless bottom, stable top mass 173 GeV, alpha_s=0.118 and common UV/IR/
renormalization scale 1000 GeV. All providers sum final spins/colours and
average initial spins/colours. Both fixtures with two final gluons include the
final identical-particle factor `1/2`; the other fixtures have distinct final
particles.

Results include physical couplings and UV/R2 contributions. They return
`finite`, `single_pole`, `double_pole` in the MadLoop/BLHA convention
`Cepsilon=(4*pi)^epsilon/Gamma(1-epsilon)`. Recola's finite coefficient is
translated by adding `pi^2/6 * double_pole` at matched scales.

OpenLoops explicitly sets `truepoles=1`, `polenorm=0`, `ct_on=1`, `r2_on=1`,
`iop_on=0`. Recola explicitly sets `dynamic_settings=1` and
`compute_ir_poles=1`; its `NLO-IR1/2` values come from repeated integral
evaluation. That extra work remains inside its timing. MadLoop returns its
computed Laurent coefficients directly, without Born or alpha_s division.

In OpenLoops 2.1.5, `truepoles=1` disables the Collier cache and the generated
`vamp2pc` wrapper calls the complete amplitude three times with different pole
parameters. This is a materially different timing scope from an ordinary
finite-only production call. Do not replace these actual coefficients with
IR-operator predictions to improve benchmark numbers. In particular, identical
repeated points may hit OpenLoops' event-result cache in a finite-only diagnostic;
such timings cannot stand in for the distinct-point acceptance workload.

Record the generated-process compilation settings separately from the generic
library settings. The pinned release defaults to `loop_optimisation = -O0`,
while generic and Born kernels use `-O2`. The process metadata reports
`OLMode=3` for the installed `ppjj` channels, so the default compilation flags
do not mean that the obsolete OpenLoops 1 algorithm was selected. An optimized
process-library comparison must be validated and timed in its own build before
replacing any existing measurements; keep normal hybrid precision and actual
poles enabled.

The development audit rebuilt an isolated copy of the `ppjj` process library
with gfortran 15.2.0 using
`python scons -Q lt=ppjj generator=0 loop_optimisation=-O3 num_jobs=1`.
Generic/Born libraries and physics/stability settings were unchanged. The
copied generic library embeds its original installation prefix: the audit
therefore set `ol_setparameter_string("install_path", isolated_path)` before
registration and observed the isolated process library in the running process's
loaded mappings. Temporary compiler output was redirected with `TMPDIR` included
in the copied installation's `import_env` setting.

Five alternating paired blocks on CPU 382, each warming 128 calls then timing
128 calls over the same three-point stream, gave medians of 13.927 ms for the
default build and 14.123 ms for the `-O3` copy. Paired runtime ratios ranged
from 0.921 to 1.099; this does not establish an improvement. Born and every
Laurent coefficient passed throughout. The default build and original headline
measurements are retained. The diagnostic uses `OLMode=3`, `hp_mode=1`,
`stability_mode=11` (the normal on-the-fly preset), and the default eight-digit
hybrid target. A separate logged three-point check observed no quadruple
precision upgrades in its scalar, dressing or reduction counters. Neither
disabled rescue nor an OpenLoops 1 library explains the comparison.

The raw development audit is under
`workspace/reports/provider-timing-audit/`; `paired-gg.json` contains paired
samples and the observed library paths. These repeated-point observations
remain distinct from the required future random-point acceptance campaign.

Alongside pairwise provider agreement, the runner checks the analytic Born
value `4/9 * g_s^4 * (t^2+u^2)/s^2` and universal double pole
`-4*C_F*alpha_s/(2*pi)*Born`, with `C_F=4/3`. Agreement uses relative
tolerance `2e-9` with a `1e-3` scale floor. This deliberately small smooth
control does not replace later threshold, cancellation, singular-region,
coupling-order, correlation, colour-expansion or precision validation.

The gluon-scattering Born control is
`9/4*g_s^4*(3-u*t/s^2-s*u/t^2-s*t/u^2)`, including the final factor `1/2`.
It follows from the unpolarized cross section in
[PDG 2022, Eq. (51.12)](https://pdg.lbl.gov/2022/reviews/rpp2022-rev-cross-section-formulae.pdf).
Its universal double pole is `-4*CA*alpha_s/(2*pi)*Born`, with `CA=3`.
The generated MadLoop averaging denominator is 512, including final symmetry.

For `u u~ > g g`, the Born control is
`16/27*g_s^4*(t^2+u^2)*(1/(t*u)-9/(4*s^2))`, including final symmetry.
It follows from [PDG 2022, Eq. (51.9)](https://pdg.lbl.gov/2022/reviews/rpp2022-rev-cross-section-formulae.pdf).
The double pole is `-(2*CF+2*CA)*alpha_s/(2*pi)*Born`; MadLoop's averaging
denominator is 72. These formulae are independent validation controls, never
substitutes for generated amplitudes.

The top-pair Born control is the massive Dirac trace
`4/9*g_s^4*((mt^2-t)^2+(mt^2-u)^2+2*mt^2*s)/s^2`. Only its two massless
initial legs contribute double poles, giving
`-2*CF*alpha_s/(2*pi)*Born`; see
[Catani, Dittmaier and Trocsanyi, Eq. (21)](https://arxiv.org/html/hep-ph/0011222#S3).
All providers use stable top pole mass and five-flavour strong-coupling
renormalization. The reference includes external-field renormalization; a
bare-loop comparison requires explicit component separation.

The Drell–Yan oracle tests all coefficients independently. Write
`a=alpha_s*CF/(2*pi)` and `L=log(mu_R^2/s)`. Its initial-state-averaged Born
value is `2*e^4*Q_u^2/Nc*(t^2+u^2)/s^2`; the virtual/Born coefficients are
`a*(pi^2-8-3*L-L^2, -3-2*L, -2)`. This follows from the one-loop quark form
factor in [Moch, Vermaseren and Vogt, Eq. (22)](https://arxiv.org/html/hep-ph/0507039#S3),
continued with `log(-s-i0)=log(s)-i*pi` and converted from the exponential
MSbar prefactor to the declared Cepsilon. The epsilon-squared conversion
removes the spacelike zeta(2) constant. The three frozen points exercise
different scattering angles and two invariant masses at fixed scale.

In this specific massless photon-exchange QCD process, the standalone
`loop_sm` export contains one Born graph, one loop graph, one effective R2
graph and no UV graph. Its model-rule R2 interference is `-2*a*Born` for
`lhv=1`. Subtracting this from the complete reference isolates the
four-dimensional bare-numerator result; this is a process-specific audit,
not a generic rule for deriving bare amplitudes.

At the reduction boundary, OneLOop uses
`rGamma=Gamma(1+eps)*Gamma(1-eps)^2/Gamma(1-2*eps)`. Since
`rGamma*Gamma(1-eps)=1+O(eps^3)`, a raw integral with measure
`mu_R^(2*eps)/(i*pi^(2-eps)*rGamma)` converts to the conventional Feynman
measure and Cepsilon coefficients by `i/(16*pi^2)` through finite order.
There is no additional pole-to-finite shift for that adapter. Graph/UFO
factors and Born interference must still be applied separately.

## Papers acquired for this milestone

Keep the supplied Recola PDFs and download these primary papers into the
workspace reference `papers` directory:

* [OpenLoops 2](https://arxiv.org/pdf/1907.13071)
* [On-the-fly reduction](https://arxiv.org/pdf/1710.11452)
* [Original OpenLoops](https://arxiv.org/pdf/1111.5206)
* [FDF and generalized open loops](https://arxiv.org/pdf/1404.4783)
* [Primary epsilon-particle rules](https://arxiv.org/pdf/1111.4965)
* [Ninja](https://arxiv.org/pdf/1403.1229)
* [UFO 2.0](https://arxiv.org/pdf/2304.09883)
* [SM rational terms and gamma-five schemes](https://arxiv.org/pdf/1106.5030)
* [Chiral symmetry-restoring counterterms](https://arxiv.org/pdf/2406.17013)

## Exact tensor and direct-R2 R0 oracle

`tensor_oracle.py` uses the public Symbolica Community tensor, HEP graph,
amplitude and one-loop APIs. Run with the licensed Community environment:

```bash
python3 tools/loop_reference/tensor_oracle.py \
  --output "$LOOP_REFERENCE_ROOT/runs/tensor-r0/report.json"
python3 -m pytest tools/loop_reference/test_tensor_oracle.py -q
```

The exact checks contract physical and evanescent representation identities,
verify a dimensional Dirac trace, retain its explicit epsilon coefficient,
and verify that gamma-five anticommutes in four dimensions while the generic
dimensional chain remains unsimplified. The last result is a capability
boundary: no BMHV algebra, chiral electroweak or finite symmetry-restoring
counterterm certificate follows from it. Separate representation ports
prevent accidental contractions; a general split Clifford algebra remains
to be implemented through the dependency.

The nonchiral top-loop Higgs-to-diphoton oracle is adapted from Community's
example, retaining its generated graph weights, fermion signs and routing.
It generates both orientations independently in D and four dimensions.
With `q_D^2=q_4^2-mu2`, the full tensor difference per orientation is
`-4*mu2*g4(mu,nu)` after stripping `Nc*Q^2*e^2*y*m`. Physical transverse
projection, summing orientations and the form-factor normalization give
`2*mu2`. Dependency reduction computes the extra-dimensional integral
`I(q_tilde^2)=-1/2`, hence the normalized `R2=1`. The separate full-D
reduction retains the epsilon-dependent bubble coefficient and gives total
rational term 2; `R1=1` is inferred from that total minus R2.

`diphoton_r2.json` exports the exact polynomial and a nonsingular massive
triangle route for the NinjaRS adapter: epsilon sectors `[2*mu2, 0, 0]`,
expected Laurent coefficients `[1, 0, 0]`. Its rational-number strings
should be converted directly into the target arithmetic, without binary64
intermediates. The integration identity used to obtain the extra-dimensional
integral is an integrated rotational identity, not a pointwise numerator
replacement. The oracle uses no effective R2 vertex.

This is a small symbolic validation oracle, not the production recurrence,
an extension to loop-induced process support, a proof for CMS/BSM models,
or a numerical precision/batch test. It was exercised with the published
Community distribution 3.0.2 (kernel 3.0.1). The executable checks require
a license because graph generation uses native workers. Keep the license
in the process environment; do not put it in fixtures or reports.

The remaining pure-gluon local source tensors can be checked with
`gluon_vertex_oracle.py --ufo MODEL --madloop-build EXPORT --mg5-source MG5
--build-dir WORKSPACE_BUILD --output REPORT`. This covers the off-shell derivative
three-gluon tensor and ordinary/UV quartic bases with 1,672 ALOHA component
comparisons and 34 exact MadGraph colour overlaps. The model preparation helper
`loops.model_gluons.prepare_gluon_counterterm_basis` exposes exact ordinary basis
representatives and the separately checked two-/four-point R2 primitives.

`wavefunction_oracle.py` also accepts the gluon-scattering component fixture. It
first proves that all four Born graphs receive identical source external-field
factors, then compares their interference using reference Born values. The three
heavy-quark groups and four external legs retain their source multiplicity;
mass-zero branches are evaluated by the native conditional evaluator. This is
an independent field-factor control, not a full amplitude calculation.

## Flavour-changing FFV and full-source mixed-order control

The local charged-current fixture can be regenerated independently with:

```bash
python tools/loop_reference/charged_ffv_oracle.py \
  --ufo "$LOOP_REFERENCE_ROOT/sources/MG5_aMC_v3_7_0/models/loop_sm" \
  --madgraph "$LOOP_REFERENCE_ROOT/sources/MG5_aMC_v3_7_0" \
  --build-dir "$LOOP_REFERENCE_ROOT/builds/charged-ffv-local" \
  --output "$LOOP_REFERENCE_ROOT/runs/charged_ffv_local.json"
```

The script generates unchanged ALOHA routines. Independent complex Yukawas and
unequal masses feed two off-shell scalar/fermion currents into the chiral vector
vertex. `charged_ffv_local.json` contains those current components and the final
contraction with its common ALOHA `-i` removed. It is a local tensor/frame control,
not a model or dimensional gamma-five certificate.

`uudd_mixed_sm_qcd.json` is a separate complete MadLoop 3.7 control for
`u u~ > d d~ QCD<=4 QED<=4 [virt=QCD]`, with native
`Process.split_orders=['QCD','QED']`. It uses `loop_sm-full`, Feynman gauge,
unrestricted Wolfenstein CKM, the explicit parameters in the fixture, native
Laurent outputs and initial spin/colour averaging 1/36. All widths and light
fermion masses/Yukawas are zero; the top mass is 173 GeV and its independent
Yukawa mass is 172 GeV. Helicity filtering is disabled and `ImprovePSPoint=-1`
preserves the supplied exact points. It includes all source W/Z/photon/gluon
Born diagrams and QCD loop corrections. It does not establish joint QCD+QED
correction coverage or any performance target.

The model-rule top-pair fixtures `tests/fixtures/loop/top-pair-model.json`
(`g g > t t~`, `u u~ > t t~`) and `top-pair-higgs-model.json`
(`e+ e- > t t~ h`) are regenerated from an unmodified MG5_aMC checkout:

```bash
for set in top-pair top-pair-higgs; do
  python3 tools/loop_reference/madloop_top_pair_model.py generate --set $set \
    --mg5 "$LOOP_REFERENCE_ROOT/sources/MG5_aMC_v3_7_0" \
    --builds "$LOOP_REFERENCE_ROOT/builds"
  python3 tools/loop_reference/madloop_top_pair_model.py run --set $set \
    --mg5 "$LOOP_REFERENCE_ROOT/sources/MG5_aMC_v3_7_0" \
    --builds "$LOOP_REFERENCE_ROOT/builds" --runs "$LOOP_REFERENCE_ROOT/runs/$set-model" \
    --fixture tests/fixtures/loop/$set-model.json
done
```

The points are exact on-shell terminating decimals, built deterministically.
The counterterm split (UV vertex, wave function, R2, isolated top-mass UV and
R2 quark two-point insertions) only sets the generated `SKIPLOOPEVAL` switch
and skips counterterm interference indices in copies of `loop_matrix.f`; bare
is full minus the counterterm sum. Binary64 references, no timing claim.

## Required-process references (MASTER_PLAN 5.6-5.7)

One parameterised toolkit produces independent provider references for any
process listed in `required_processes.json`; nothing in it is process-specific.

| File | Role |
|---|---|
| `required_processes.json` | Process specifications: PDGs, Born amplitude orders (powers of `g_s`, `e`), correction type, scheme, MG5/Recola/OpenLoops process strings and OpenLoops library. Schemes hold the exact decimal parameters shared by all providers. |
| `required_spec.py` | Loader (derives loop orders), external masses, averaging/symmetry metadata, universal double-pole factor. |
| `exact_points.py` | Deterministic exact on-shell 2->n points with terminating decimals (massive pairs included); see its docstring for the construction and its representability limit. |
| `madloop_export.py` | MG5_aMC standalone export (optimized output, external Ninja/Collier, split orders `QCD,QED`), built with MG5's production Fortran flags (Source libraries and `make OLP_static`; `--recompile` rebuilds an existing export); writes `<export>.generation.json` with graph counts, observed orders, `fortran_flags` and generation/export/compile times. |
| `madloop_driver.f90`, `recola_driver.f90`, `openloops_driver.cpp` | Generic native drivers (no Python per point): Born and Laurent coefficients selected by squared split order (MadLoop) or coupling power (Recola/OpenLoops). |
| `references.py` | `run` one provider (builds its driver, sets matched parameters, pins one CPU, records times and the provider versions read from the trees/libraries actually used), `merge` the available providers into one JSON with all-pairs cross-checks, `summary` (Markdown table) and `watch` (periodic re-merge of long runs that exits once every expected run has finished, failed or died). |
| `run_required.sh` | Convenience wrapper: points (if absent) + `run` + `merge` under `$LOOP_REFERENCE_ROOT/runs/required/<process>/`. |
| `build_recola_patched.sh`, `recola_colorbranch.patch` | Isolated Recola build with the seven-gluon `colorBranch` fix (below). |

Typical use (licence not needed; run from any directory):

```bash
source workspace/reference/env.sh
export LOOP_REFERENCE_ROOT=workspace/reference LOOP_REFERENCE_PYTHON=python
python tools/loop_reference/madloop_export.py --spec tools/loop_reference/required_processes.json \
  --process gg_ttxgg --mg5 $LOOP_REFERENCE_ROOT/sources/MG5_aMC_v3_7_0 \
  --output $LOOP_REFERENCE_ROOT/runs/required/gg_ttxgg/madloop-export
for provider in madloop recola openloops; do
  tools/loop_reference/run_required.sh gg_ttxgg $provider <cpu>
done
```

Each provider writes `status-<provider>.json` (`running`/`done`/`failed: ...`),
`<provider>-run/output.log` and `<provider>-result.json`; `reference.json` is the
merge. `run --tag <t>` writes a secondary run (`<provider>-<t>-result.json`)
whose timings and deviations from the reference run are attached to the merge
(`providers.<provider>.secondary_runs.<t>`) but never used as values; it is used
for MadLoop at its production stability setting (below). MadLoop runs can wait
for a long export with `--wait-for-export`; they fail as soon as no live
`madloop_export.py` process for that export remains. A failed or interrupted provider is resumed by rerunning the same
`run_required.sh` line; a MadLoop export is resumed by deleting the incomplete
export directory and rerunning `madloop_export.py` (it refuses to overwrite).

### Matched settings

Both schemes: Feynman gauge, all widths zero (stable top; the complex-mass
scheme then reduces to real on-shell masses), massless `b`, `tau` and light
fermions, diagonal CKM, `alpha_s=0.118` at `mu_R` with five active flavours
(top decoupled) and six quark flavours in loops, `mu_UV=mu_IR=mu_R` per point,
UV counterterms and complete R2 on, actual poles from every provider.

* `qcd` (MG5 `loop_sm-no_b_mass`): `alpha=1/132.507` fixed, `G_F=1.16639e-5`,
  `MZ=91.188`, `MW` derived at tree level (`80.419002...`), `MH=125`,
  `MT=ymt=173`. Recola: `use_alpha0_scheme(alpha)` with derived `MW`;
  OpenLoops: `ew_scheme=1` with the same `G_F`, `MZ` and derived `MW`, which
  reproduces `alpha` exactly. EW renormalization is absent in QCD corrections.
* `ew-gmu` (converted `loop_qcd_qed_sm_Gmu`, default restriction): G_mu input
  and renormalization scheme, `G_F=1.16639e-5`, `MW=80.419`, `MZ=91.188`,
  `MH=125`, `MT=ymt=173`. MadLoop generates `[virt=QCD QED]` with squared-order
  selection of the Born-virtual interference, i.e. every one-loop graph of the
  selected coupling order (EW and QCD-EW mixed, closed fermion loops), which is
  how OpenLoops `*_ew` libraries (`EW=n,1`) and Recola (`select_gs_power_LoopAmpl`)
  define the NLO EW virtual. Recola: `use_gfermi_scheme`; OpenLoops:
  `ew_scheme=1`, `ew_renorm_scheme=1`, `ew_renorm=1` (EW counterterms are off by
  default for a directly registered EW library).

Conventions: MadLoop/BLHA `C_eps=(4 pi)^eps/Gamma(1-eps)`; OpenLoops
`truepoles=1`, `polenorm=0`, `iop_on=0`, used directly; Recola finite part
converted by `+pi^2/6 * D`. The MadLoop reference run requests relative
accuracy `1e-11` (its stability test then sends most 6- and 7-leg top points to
the quadruple-precision Ninja rescue, return code 328) and forces the stability
test on every call; its times are therefore not a production baseline. A second
MadLoop run (`--tag production --madloop-accuracy -1`) keeps MadLoop's own
`MLStabThres=1e-3` and default stability test (`CTModeRun=-1`) and records the
production per-point times and return codes, plus its deviation from the
reference run; this is the MadLoop timing to use for the speed gate. Both keep
`ImprovePSPoint=2`.

MadLoop build flags. A bare `output standalone` leaves `GLOBAL_FLAG` unset in
`Source/make_opts`, i.e. gfortran `-O0` for everything except `polynomial.f`
(MadLoop's own makefile always uses `-O3` there). MG5_aMC's production flags are
its run-card defaults `global_flag=-O`, `aloha_flag=`, `matrix_flag=` (3.7.0),
which `CommonRunCmd.update_make_opts` writes into `make_opts` whenever MG5 runs
optimised (`bin/mg5_aMC` re-executes itself with `python -O` unless `--debug`;
the NLO template likewise uses `FFLAGS=-O`); `-O3`/`-ffast-math` appear only as
run-card suggestions. `madloop_export.py` reads these defaults through MG5's
`RunCardLO`, writes them with MG5's `update_make_opts_full`, rebuilds DHELAS/MODEL
and `OLP_static`, and records them as `fortran_flags`. `references.py run`
records the export's flags in `settings.fortran_flags` (with
`production_build`), compiles the quadruple-precision model repair with the same
`GLOBAL_FLAG`, and refuses a production-timing run (`--madloop-accuracy <= 0`) on
an export not built with them. The exports of the first campaign were `-O0`;
their production timings were re-measured on rebuilt copies
(`<process>/madloop-export-production-flags`, same CPU, previous driver
re-timed right before as a control in `pre-production-flags/`): values agree
with the `-O0` build to rounding and the times drop by the factors listed under
"Production-flag re-timing" below. The reference-value runs (`madloop-result.json`,
quadruple-precision rescue forced) keep their `-O0` build; their times are not
speed-gate timings.

Production-flag re-timing (MadLoop production setting, mean seconds per point,
one pinned CPU, 2026-10-20; "control" is the previous `-O0` driver re-timed on
the same CPU just before the `-O` run; value change in the merge metric against
the `-O0` production values; every point return code 216). Initial calls are not
compared: the `-O` runs started from a fresh run directory (helicity filter
computed again).

| process | `-O0` as recorded | `-O0` control | `-O` (production) | control / `-O` | max value change |
|---|---|---|---|---|---|
| gg_ttx | 0.001178 | 0.001097 | 0.000961 | 1.14 | 0.0e+00 |
| gg_ttx_ew | 0.004276 | 0.002313 | 0.001996 | 1.16 | 0.0e+00 |
| uux_emepg_ew | 0.007876 | 0.004941 | 0.004443 | 1.11 | 5.4e-15 |
| uux_emepddxg | 0.1822 | 0.1741 | 0.1427 | 1.22 | 0.0e+00 |
| gg_ttxemep_ew | 0.2861 | 0.2573 | 0.2382 | 1.08 | 5.1e-15 |
| uux_emepggg | 1.833 | 1.723 | 1.409 | 1.22 | 0.0e+00 |
| gg_ttxemepg_qcd | 3.765 | 3.738 | 3.031 | 1.23 | 0.0e+00 |
| gg_ttxgg | 7.5 | 7.001 | 5.263 | 1.33 | 0.0e+00 |
| gg_ttxemepg_ew | 8.444 | 7.896 | 6.975 | 1.13 | 1.4e-14 |
| gg_gggg | 52.98 | 52.41 | 37.18 | 1.41 | 0.0e+00 |

The gain is modest (not profiled; the reduction libraries Ninja, Collier and
CutTools are prebuilt by the MG5 installation independently of these flags, and
`polynomial.f` was already `-O3`).

Stress from the point cut: `exact_points.py` admits every point with
`2|p_i.p_j| >= s/1000` (`--cut`, default `1/1000`), so the required points include
nearly soft/collinear configurations. At the reference request (`1e-11`) many
6- and 7-leg points fail MadLoop's double-precision stability test and need the
quadruple-precision rescue (return code 328, at 50-80x the double-precision
time on the 6- and 7-leg top processes); at the production `MLStabThres=1e-3`
every required point passes in double precision (code 216). The default cut
therefore deliberately stresses MadLoop's stability test: reference-run times
measure the quadruple-precision rescue, production-run times only the
double-precision path (no rescue was triggered at these points).

MadLoop's parameter card receives each scheme value as its
exact decimal text (checked to reproduce the same binary64 on re-reading). Recola
uses `dynamic_settings=1`, `compute_ir_poles=1`.
At seven or more external legs the COLLIER global cache is disabled in both
MadLoop (Collier 1.2.9, `COLLIERGlobalCache=0`) and Recola (Collier 1.2.8,
`set_cache_mode_rcl(0)`), following the NinjaRS owners' report of a wrong
global-cache result at `N=7`, rank 9.

Recola near-tolerance rows. In `g g -> t t~ e- e+ g` (QCD) and
`g g -> t t~ e- e+` (EW) the largest pairwise differences (`1.0e-8` and
`1.8e-8` in the finite part of point 3) come from Recola alone: MadLoop and
OpenLoops agree there to `6e-13` and `1.6e-12`, while Recola differs from both
by the same amount. Recola leaves COLLIER at its default required accuracy for
tensor integrals, `1e-8` (critical `1e-1`, mode COLI). With the driver commands
`tis_accuracy 1e-12 1e-6` (after `generate`; `set_TIs_required/critical_accuracy_rcl`)
Recola agrees with OpenLoops to `1.7e-11` (QCD) and `2.9e-12` (EW) at a cost of
~1.5x per point; `collier_mode 3` (COLI+DD) alone does not help, pure DD
(`collier_mode 2`) fixes the EW case but breaks the 7-point QCD poles
(`workspace/reference/runs/required/recola-settings-study/`). The references keep Recola's
defaults (all processes pass `2e-8`); the agreement reported for these two
processes is limited by COLLIER's default accuracy, not by a convention.

The merge compares every unordered pair of providers (per row:
`provider_pair_relative_errors`, `provider_pair_strict_relative_errors`; the
reported maximum is over pairs of validated providers) coefficient by coefficient with
`|a-b|/max(|a|,|b|,|Born| coupling/(2 pi))` (no floor for the Born; strict
relative errors are listed too) and the universal double pole
`D = -(coupling/2pi) * sum_i C_i * Born` (QCD: `C_F`/`C_A` per massless
coloured leg; EW: `Q_i^2` per massless charged leg). Tolerance `2e-8`, as for
the earlier seven-leg controls. Timings are single-thread by-products: point 1
is evaluated untimed for initialization, then each point once.

Recola defect at seven gluons: `makeSkeleton` declares the automatic array
`colorBranch(bLDef)`, but `reallocate_bLDef` enlarges `bLDef` beyond the
initial 500000 branches during generation of `g g -> g g g g g`; the following
`colorBranch(b)` writes overflow the array and glibc aborts with "double free or
corruption" in `reallocate_bLDef` (also with an unlimited stack).
`recola_colorbranch.patch` makes the array allocatable and grows it with
`bLDef`; it changes nothing while no reallocation happens (bitwise identical
`g g -> t t~` results). The patched copy is built separately in
`workspace/reference/builds/recola2-2.3.0-colorbranch-fix` and selected with
`LOOP_REFERENCE_RECOLA`; reproduce it with

```bash
tools/loop_reference/build_recola_patched.sh workspace/reference/sources/recola2-2.3.0 \
  workspace/reference/sources/COLLIER-1.2.8 workspace/reference/models/SM_2.2.3 <new-dir>
```

(a fresh build from this script gives bitwise identical `g g -> t t~` values).
The supplied "2.3.0" tree reports version 2.2.5 itself (banner and
`recolaConfigVersion.cmake`); result files record that self-reported version and
the tree path.

### EW matching findings (g g -> t t~ e- e+ g, `ew-gmu`)

* OpenLoops `ppllttj_ew` (channel `eexttxggg`, `EW=2,1 QCD=3,0`, `nf=6`,
  massless leptons) computes every one-loop graph of order `g_s^3 e^4`
  interfered with the `g_s^3 e^2` Born, in the G_mu input and renormalization
  scheme (`ew_scheme=1`, `ew_renorm_scheme=1`) with on-shell masses. EW
  counterterms must be enabled with `ew_renorm=1` when the EW library is
  registered directly. Its default `complex_mass_scheme=1` gives results identical
  (1e-14) to `complex_mass_scheme=0` at zero widths.
* Recola's default complex-mass scheme is not equivalent at zero widths: it
  changed the finite part by 4e-4 (`g g -> t t~ e- e+`) and 2.7e-3
  (`g g -> t t~ e- e+ g`) while leaving `g g -> t t~` and `u u~ -> e- e+ g`
  unchanged, i.e. it enters through the top-Z couplings. With
  `set_on_shell_scheme_rcl` Recola agrees with OpenLoops to 1e-9 (seven legs)
  and 2e-8 (six legs); rotated points reproduce Recola to 1e-12, so the earlier
  difference was not numerical.
* MadLoop with the converted `loop_qcd_qed_sm_Gmu` (`[virt=QCD QED]`, real
  masses) first differed from the agreeing Recola/OpenLoops pair on
  `g g -> t t~ e- e+` EW by 1e-7 to 3e-7 in the finite part only (poles agreed
  to 1e-11; Higgs-mass and `mu_R` dependent). **Cause established: an MG5_aMC
  3.7.0 defect in MadLoop's quadruple-precision path, not a UFO counterterm
  convention.** MadLoop at its production stability setting (double precision,
  return code 216) agreed with OpenLoops to 1e-10, while the reference run
  (quadruple-precision rescue, code 328) did not; comparing every double- and
  quadruple-precision model parameter after the same card read isolated the EW
  on-shell renormalization constants (e.g. `ZAWCFT_UV_EW_FIN`, relative 4.8e-9;
  `C_UVTXTA2EW` 5.5e-7), and the exported `MP_REGLOG` returns
  `log(MW^2/MU_R^2)` with relative error 4.8e-9: the MP model functions
  (`MP_REGLOG`, `MP_REGLOGP/M`, `MP_REGSQRT`, `MP_GRREGLOG`, template in
  `madgraph/iolibs/export_v4.py`) call `CMPLX(...)` without `KIND=16`, which
  rounds real arguments to single precision; their `TWOPII` also uses the pi
  literal `3.14169258...` (branch terms only, no effect here). The defect also
  touches QCD: the top-decoupling counterterm `log(MU_R^2/MT^2)` gave the 5e-9
  MadLoop spread of `g g -> t t~ g g`. `references.py` compiles a repaired copy
  of the export's `model_functions.f` into the run directory and links it
  before `libmodel.a` (the export is untouched; repairs are listed in
  `settings.mg5_quadruple_precision_model_function_repairs`). With it the
  quadruple-precision MadLoop agrees with OpenLoops to 1.5e-13..2.4e-12 on
  `g g -> t t~ e- e+` EW, and MadLoop is a validated provider for every
  process. The defect is in MG5's exported Fortran, not in the UFO: evaluated
  correctly, the UFO EW counterterms agree with Recola/OpenLoops.
  `exclusions.json` remains available for documented exclusions but none is
  in use.

## Legacy-engine oracles for the v2 engine (WP0.1)

`legacy_capture.py` freezes the legacy per-diagram engine before the v2 engine
replaces it (oracles O1 and O2 of `docs/development/loop_v2/DESIGN.md` section
14) for the control set gg->gg, uu~->dd~g, uu~->ggg, Drell-Yan (photon only),
uu~->dd~, uu~->tt~, uu~->uu~ and uu~->uu~g, in binary64 and in 200-bit
arbitrary precision:

* `tests/fixtures/loop/legacy/<name>.json` (O1): Born and the six virtual
  components per squared order and Laurent coefficient at every point, the
  matched counterterm and external-field insertion multisets, and for gg->gg
  the leading-colour projection with its colour degrees;
* `tests/fixtures/loop/legacy/<name>.families.json.gz` (O2): per denominator
  family (shifts as external-momentum combinations, squared masses, monomial
  powers) the Born-weighted numerator coefficients the legacy engine reduces,
  at the first point.

It uses the generic source compiler on MG5_aMC `loop_sm` with `MB=0` (the
providers' `loop_sm-no_b_mass` scheme), the points of the committed provider
references, and stores the engine's own decimal strings, so a rerun reproduces
the files byte for byte:

```bash
python tools/loop_reference/legacy_capture.py --ufo <MG5>/models/loop_sm [--process ...] [--check]
```

The fixtures were last regenerated for the coordinated re-pin (b5c5e83b; native
b71edd24: NinjaRS aa6a6307, oneloopmaster 8ec256fc, Symbolica 9cdc2949).
binary64 values are bitwise unchanged. The 200-bit values moved at rounding
level. O1, worst change relative to the largest modulus of its Laurent row:
4.2e-60 (dy) to 1.9e-54 (uux_ggg bare). O2, worst change relative to the
family's largest coefficient: dy 2.3e-60, uux_uux 3.0e-60, tt 3.5e-60, uudd
4.5e-60, gg_gg 5.8e-60, uux_ggg 2.5e-58, uux_ddxg 9.3e-57 (family 5) and
uux_uuxg 1.6e-56 (family 22). The b5c5e83b message gives 2.5e-58 as the O2
maximum, which misses the two five-leg quark controls. The captures are
byte-identical with the Community kernel at e679e8c1 or 9cdc2949: their
arbitrary-precision arithmetic runs in the native.

`tests/unit/test_loop_v2_oracles.py` checks the regeneration and the agreement
of the providers with each other and with the legacy engine (<= 1e-9 in the
metric of the required references). The three slice processes `uux_ddxg`,
`uux_uux` and `uux_uuxg` (role `slice` in `required_processes.json`) were
produced with `run_required.sh` like every other required process. For a
massless 2->2 final state `exact_points.py` uses the seed parameter for the
scale and the scattering axis; larger final states keep their points.
