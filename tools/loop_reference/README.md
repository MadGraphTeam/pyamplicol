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

(The external-field component oracle `wavefunction_oracle.py` ran the legacy
engine and was removed with it, MQ-LEGACY-REMOVE.)

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
comparisons and 34 exact MadGraph colour overlaps.

The removed `wavefunction_oracle.py` (legacy engine) also accepted the
gluon-scattering component fixture.

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
| `madloop_ct_parameters.py` | MadLoop's own counterterm-parameter values of a loop UFO at one card: MG5_aMC's Fortran model library as a MadLoop standalone output writes it (`UFO_model_to_mg4`, export format `madloop`, quadruple precision), for every coupling, compiled with the production flags and the quadruple-precision repairs of `references.py`; its own `setpara` reads the card, a driver prints every Laurent piece (`_2EPS_`, `_1EPS_`, `_FIN_`) bit-exactly in double and quadruple precision (JSON). Source of `tests/fixtures/loop/madloop-ct-parameters.json` (below). |
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

### Provider files come from the reference root

Provider trees name absolute paths of the place they were built in: the
RUNPATH of Recola's, COLLIER's and the Recola model's shared libraries, the
HEPTools archives in a MadLoop export's `MadLoop_makefile_definitions`
(`LOOP_LIBS`), OpenLoops' compiled-in `install_path` (where it loads
`proclib/` from), NJet's `pkg-config` files and RUNPATHs. After the working
root moved on 2026-10-24 every run read the old tree until the trees were
relocated (package reference-relocate,
`workspace/reports/engine-v2/reference-relocate/`: inventory, scripts, evidence).
`references.py run` therefore refuses, before linking or loading anything, a
MadLoop export, `LOOP_LIBS` archive, provider tree or (recursive) library
RUNPATH entry outside `--reference-root` (default `$LOOP_REFERENCE_ROOT`;
`run_required.sh` passes it) or the system prefixes (`provider_paths.py`; a
path outside is judged by its text and never opened, symbolic links are
followed one component at a time). Without a configured root it warns and
does not check. OpenLoops runs with `OpenLoopsPath` set to the given tree, so
its process libraries never come from a compiled-in path. The NJet runner
checks its build the same way (the build directory and the reference root).

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

### MadLoop's counterterm-parameter values (`madloop_ct_parameters.py`)

`tests/fixtures/loop/madloop-ct-parameters.json` holds every Laurent piece of
every CT parameter MadLoop's model library writes for `loop_qcd_qed_sm_Gmu_py3`
(143) and `loop_qcd_qed_sm` (139) at the oracle card of
`tests/unit/test_loop_v2_ew.py` (the `gg_ttx_ew` card, the restricted models'
other values), in double and quadruple precision; the v2 engine's CT values
must equal them (`test_counterterm_scalars_equal_madloop`). Produced with

```bash
python tools/loop_reference/madloop_ct_parameters.py --mg5 <MG5_aMC_v3_7_0> \
    --ufo <reference>/models/loop_qcd_qed_sm_Gmu_py3 --card card.json \
    --output <new work directory> --json ml_gmu.json
```

(`card.json`: {UFO external parameter name: decimal string}; about 2 min,
mostly compiling the couplings). The UFO is copied into the work directory and
imported from there with MG5's default restriction, real-mass scheme and
Feynman gauge, as `madloop_export.py` does; MG5's import writes `py.py` and
`additional_command` into the current directory. Findings:

* MG5's Fortran `REGLOG`, `REGLOGP`, `REGLOGM`, `REGSQRT` and `GRREGLOG` replace
  a vanishing imaginary part of either sign by +0 before taking a branch: an
  argument exactly on the negative real axis takes the side of a positive
  imaginary part. At real masses that side changes HWcft_UV_EW by 80 % and
  HMass2_UV_EW by 1.7 % against the -0 side.
* The quadruple-precision lane reads the card through a binary64 buffer
  (`MP_LHA_GET_REAL` in `lha_read.f`): its inputs are the card's decimals
  rounded to binary64, so an exact-decimal comparison differs at 1e-15.
* Cross-check: the 12 CT pieces of the `g g > t t~ [QCD QED]` G_mu standalone
  export behind `required/gg_ttx_ew.json`, dumped from that export's own
  `lib/libmodel.a` at its own param_card, are bit-identical in both precisions.

### Seven-leg QCD references

`tests/fixtures/loop/required/uux_ggggg.json` is the merged reference of
`workspace/reference/runs/required/uux_ggggg/` (`reference.json`, copied
unchanged on 2026-10-23): MadLoop and Recola at three points, validated to
`6.2e-10` (tolerance `2e-8`). Generation on this host: MadLoop 12.2 h
(5,793 s graphs + 38,040 s export + 122 s compile), Recola 2.8 h (10,220 s);
per point MadLoop 558 s (production stability setting, return code 216) and
Recola 182 s. OpenLoops has no public library for this process. No
MadLoop, Recola or OpenLoops `g g -> g g g g g` reference exists: its MadLoop
(colour factors ~89 days by MG5's estimate) and Recola (> 57 h) runs were
stopped and are not restarted (REQUIREMENTS_ADDENDUM F); NJet is its
independent reference (below).

## M-QCD reference campaign (`mqcd_campaign.py`)

The MadLoop references of the M-QCD milestone
(`workspace/reports/engine-v2/m-qcd/PLAN.md` §4, package MQ-REF). Nothing in
the runner is process-specific: rows, runs, schemes and point families are
data.

| File | Role |
|---|---|
| `mqcd_campaign.json` (written by `make_mqcd_campaign.py`) | The 76 rows of §4.2 (class, process, restriction code and its pyAmpliCol route, reference kind E/N/R, tier, extras) and the 78 reference runs producing them (process key of `required_processes.json`, export, points family, per-helicity, second providers with their §4.1 trigger or 'diagnostic', MadLoop accuracy target, provider exclusions, per-point reference notes and `point_status`, including declared rule 1 outliers); per row the `helicity_reference` run. |
| `mqcd_campaign.py` | `export`, `points`, `run` (MadLoop's quadruple-precision evaluation under `timeout 2700`, pinned; `split_points` runs one job per point, then `combine`), `merge` (passes the run's `point_status`), `fixture` (absolute paths rewritten to `${LOOP_REFERENCE_ROOT}` / `${REPOSITORY}`; refuses any `/shared`, `/home`, `/tmp` or non-compiler `/nix/store` path left), `relocate` (the same rewrite, by text, of committed fixtures outside the campaign; every value unchanged, checked leaf by leaf), `manifest`, `status`. Work directories `$LOOP_REFERENCE_ROOT/runs/mqcd/<run>/`. |
| `supplied_points.py` | Points for every mass pattern `exact_points.py` cannot build (several massive subsystems, massive beams, irrational MW, light massive pairs above 800 GeV): 60-digit construction printed exactly on a 30-digit quantum (no 28-digit context rounding at print time), momentum conservation exact in the printed decimals and the recorded defects those of the printed values; configurations it cannot reach are refused before the search, and the search is bounded; families `regular`, `threshold`, `soft`, `collinear`, `radiation-zero`, `rest` (2->1); `--rotate x`, `--half-scale-point`, `--madloop-qp-point`. |
| `tests/fixtures/loop/required/mqcd/<run>.json` | One merged reference per run (the `references.py merge` format plus `sectors`, `madloop_accuracy`, `per_helicity`, `restriction`, `parameter_overrides`, a per-row `reference` record, `tolerance_scope`, `mqcd_run`). |
| `tests/fixtures/loop/required/mqcd_references.json` | The manifest MQ-VALIDATE consumes: per row the pyAmpliCol route (restriction, fixed parameters), each reference run (fixture, process, orders, points, MadLoop return code, evaluation precision and accuracy per point and loop squared split order, `binding_rows`, rule 1 `outliers`, notes, exclusions, second-provider trigger and outcome), the existing references (return codes, evaluation precision, `point_binding`: binding, or superseded by the run row that re-evaluates the same point in quadruple precision, with the deviation), `binding_references` (the one binding reference of every point) and `helicity_reference`; parameters, per-point `reference` records and per-helicity rows stay in the fixtures; `conventions` documents indexing, the records and that fixture tolerances are not M-QCD acceptance values. |

Typical use:

```bash
source workspace/reference/env.sh
export LOOP_REFERENCE_ROOT=workspace/reference LOOP_REFERENCE_PYTHON=python
python tools/loop_reference/mqcd_campaign.py export uux_gg      # own exports only
python tools/loop_reference/mqcd_campaign.py points uux_gg
python tools/loop_reference/mqcd_campaign.py run uux_gg --cpu <cpu>
python tools/loop_reference/mqcd_campaign.py merge uux_gg && \
python tools/loop_reference/mqcd_campaign.py fixture uux_gg && \
python tools/loop_reference/mqcd_campaign.py manifest
```

MadLoop evaluates every point in quadruple precision (fix round 2;
`madloop_settings.evaluation` of `mqcd_campaign.json`): `references.py run
--madloop-quadruple` compiles a copy of the export's `loop_matrix.f` whose
double-precision acceptance test is bypassed (`force_quadruple_stage`), so
every point goes on to MadLoop's own quadruple-precision stage, where its
stability test (forced on every call, two propagator directions,
`MLStabThres` 1e-13) accepts Ninja or else CutTools, exactly as for a point
whose double-precision estimate failed; `--madloop-param
HelicityFilterLevel=0` computes every helicity configuration; a run returning
a double-precision point is refused (`--madloop-require-quadruple`), and every
run starts without the helicity and loop filters an earlier run left in its
directory. Why (§1.4 rule 1 compares double-double values with the reference
at 1e-12 per coefficient):

* MadLoop's accuracy (`ML5_0_COMPUTE_ACCURACY`) is ONE number per squared split
  order, `sum_k |v_k(mode 1) - v_k(mode 2)| / (|sum_k v_k| / 3)` over the three
  Laurent coefficients: not a per-coefficient accuracy. The batch-2 evaluation
  (`MLStabThres` 1e-13, rescue only where that estimate failed) kept 209 of 303
  points in binary64 with cancelling coefficients up to 4.3e-12 off (C02 point
  0 finite 2.0e-12, D11 point 1 single pole 4.3e-12, A06 point 1 single pole
  1.2e-12, at estimates of ~1e-14 or exactly 0, where no threshold forces the
  quadruple-precision stage).
* MadLoop's numerical helicity filter (`HelicityFilterLevel` 2, `ZeroThres`
  1e-9) zeroes helicity configurations below 1e-9 of the average and folds
  numerically equal ones: for the massive-b rows it dropped and folded
  mass-suppressed configurations (C01 point 1: finite 3.2e-11, poles 4.8e-13
  off, in both precisions; with `HelicityFilterLevel = 0` MadLoop = Recola to
  1e-15).
* A fixed `CTModeRun = 4` (Ninja in quadruple precision without fallback;
  `--madloop-ctmode`, a diagnostic the merge refuses as a reference) is worse
  where MadLoop's test rejects Ninja (g g > t t~ g points 0, 3: double pole
  3.1e-11 off the universal relation, CutTools 1e-14; g g > u u~ u u~ points
  0, 2, 3: 5.5e-12, CutTools 3.5e-13 .. 1.1e-12) although its `CTModeRun = 5`
  twin agrees with it to 1e-13; `MLStabThres` 1e-20 rejects Ninja on a
  one-ulp difference of its two directions. MadLoop's own selection at 1e-13
  is kept.

Three runs keep their batch-2 evaluation (`madloop_evaluation`, reason
recorded): B05 and E06 (quadruple precision at every point already, 2.0-2.4
CPU-hours each; their helicity filters contain no folded and no
mass-suppressed entry) and the collinear limit points (a fixed quadruple
precision returns NaN at the unstable theta = 1e-4, 1e-5 points). The
re-evaluated runs keep the batch-2 values as the secondary run `mlstabthres`
(`relative_deviation_from_reference_run` in the fixture). The E rows get
`<key>_sectors` runs on their existing exports at the committed points plus a
mu_R = mu_0/2 copy of point 1 (every squared split order, MadLoop's accuracy
per sector), and every new row has three points plus that copy. Where such a
run re-evaluates an existing reference's point (same exact point and mu_R) in
MadLoop's quadruple-precision stage with an ok record, the run's row is the
binding reference and the existing point is superseded (manifest
`point_binding`, with its strict relative deviation; required/uux_uux.json
point 1, a double-precision MadLoop value of batch 1 with accuracy 0.0, is
1.2e-12 off in the single pole); the existing fixture's other providers stay
the rule 1 (ii) values there.

Reference outliers (rule 1 names them): declared per point in the run's
`point_status` as `outlier` (rule, ruling, the state of conditions (i) and
(ii), provider evidence), recorded as `reference.outlier` in the fixture and
listed in the manifest's `outliers`. g g > u u~ u u~ (A18) points 0, 2, 3:
MadLoop's quadruple-precision stage takes CutTools (return code 329, accuracy
0.0) and misses the universal double pole by 3.5e-13 .. 1.1e-12; mq-validate's
double-double differs from it by 3.5e-12 or more. Rule 1 (i) fails at all
three points (an accuracy of 0.0 covers no nonzero difference, so every rule 1
failure at a quadruple-precision point with accuracy 0.0 needs a ruling); (ii)
holds at point 0 only (OpenLoops `ppjjjj` = DD to 5.5e-13; 1.2e-12 and 2.6e-12
at points 2, 3). Recola, run as a third value, differs from both MadLoop and
OpenLoops by 1.7e-12 .. 5.6e-11 at every point, point 1 included, where MadLoop
(Ninja) and OpenLoops agree to 1e-12: its binary64 COLLIER values decide no
point. The ruling on points 0, 2, 3 is the user's (via the coordinator). A
point whose quadruple-precision stability test failed (return code 4xx) is
refused by the merge unless declared (status `none` or an outlier). The
integrity tests recompute `max_sector_double_pole_relative_error` from every
sector's printed values and refuse an ok regular point (not a declared
outlier) above max(10 x MadLoop's largest sector accuracy, 2e-13); at regular
points the printed Born and the Born the double pole implies agree to
<= 1.1e-13 over the campaign (u u~ > w+ w-, binary64 W momenta).

Schemes added for the campaign (`required_processes.json`; every scheme names
its MG5 `restriction`): `qcd-4fs` (loop_sm default restriction: MB = ymb = 4.7,
MTA = 1.777, widths 0 = no_widths, four active flavours), `qcd-cmass`
(`c_mass`: MC = 1.55, three active flavours), `qcd-ckm` (`zeromass_ckm`,
Wolfenstein card values), `qcd-ckm4` (`ckm`, massive b), `qcd-lmass`
(`lepton_masses`), `qcd-widths` (`no_b_mass` with WZ, WW, WH at the card
values, WT = 0). External masses come from the scheme for c, b, t, e, mu, tau,
Z, H and W (MW derived at tree level to 30 digits in `required_spec.derived_mw`,
the value Recola, OpenLoops and the point construction share); Recola's charm,
muon and electron masses and OpenLoops' `mass(4)`, `mass(11)`, `mass(13)` are
the scheme's (C08/C09: MadLoop = Recola to 2.6e-13 / 2.6e-14 with MC = 1.55).

MadLoop driver output (`madloop_driver.f90`): besides the requested sector
(`ROW`), every point prints the complete `ANS(0:3,0:nanswer)` and MadLoop's
accuracy `ACC(0:nloop)` of every loop squared split order (`SECTORS`; index
table `LOOP_SO`). The Born split orders are read from the export's
`born_matrix.f` DATA statement: MG5 3.7.0's
`GET_SQUARED_ORDERS_FOR_SOINDEX` reads the common block `/SQPLITORDERS/`,
which is never initialised (its DATA fills a local array `SQSPLITORDERS`), and
returns zeros. Per-helicity mode (`references.py run --tag hel --helicities
all|h1,h2,...;...`): one `HEL_ROW` per HelConfigs.dat tuple from
`SLOOPMATRIXHEL_THRES`, in MadLoop's per-helicity normalisation (colour
average and identical-particle factor, no helicity average; the sum over all
configurations is HELAVGFACTOR (4 for two fermion or massless vector beams) times the summed value, checked by
`tests/unit/test_loop_reference_mqcd.py`). Multiparticle requests
(`"multiparticle": true`) export every subprocess; `--subprocess P*` and
`--pdgs` run one `SubProcesses/P*` directory (M01: `P0_uux_ttx`, which MadLoop
uses for u, c, d, s, b, and `P2_gg_ttx`).

Limit points. MadLoop reads binary64 momenta: in double precision it evaluates
the rounded point as it is, in quadruple precision the point its
`ImprovePSPoint = 2` (ORIG) method projects on shell; its Born (`ANS(0)`) is
always the double-precision value at the rounded point. At ill-conditioned
points this input rounding, not MadLoop's reduction, limits the reference
(collinear theta = 1e-3: MadLoop's double-precision Born differs from its
quadruple-precision one by 1.6e-9). The limit-point runs (S1 threshold, S2
soft/collinear, S3 radiation zero) therefore publish MadLoop's own
quadruple-precision point (`supplied_points.py --madloop-qp-point`, the ORIG
formulas replicated at 60 digits), evaluated like every run (quadruple
precision; the collinear run of batch 2 requested 1e-20). At those (`madloop_qp_point`) points the
merge makes the Born at the published point, MadLoop's quadruple-precision
double pole over the universal factor, the reference `born` of the row and of
its sectors (`reference.born_source`), keeping MadLoop's printed value as
`born_madloop_binary64_input` / `born_binary64_input`. Findings: soft E/sqrt(s) = 1e-3, 1e-5: MadLoop =
OpenLoops to 1.5e-14, 2.5e-13 (Recola's double-precision COLLIER is off by
4.6e-9 and 6e-3 and is excluded); collinear theta = 1e-4 and 1e-5: MadLoop's
quadruple-precision evaluation is unstable (return code 420, own accuracy
1.3e-6 and 28; OneLOop "input does not seem to represent hard kinematics") and
no provider agrees with another, so these points carry no provider reference
(`point_status` / `reference.status` = `none`). The S3 Born-zero points compare
absolutely (`reference.comparison` = `absolute`, scale = the Born at the
regular neighbour row). Per-point reference record (`rows[i].reference`): `status` (`ok` / `none`),
`outlier` (None or the declared rule 1 outlier), `comparison` (`relative` /
`absolute` with `absolute_scale_row` and `absolute_scale`), `born_source`,
`madloop_point` (published point, its binary64 rounding, or MadLoop's
quadruple-precision repair of that rounding, ~1e-16 away),
`born_double_pole_relative_mismatch` (MadLoop's printed Born against the Born
its quadruple-precision double pole implies: at a regular point the printed
Born's binary64 rounding, <= 1.1e-13; above that a loop defect of the
reference, e.g. C01 point 1 of batch 2 at 4.8e-13 or the A18 outliers; at
limit points the binary64 condition of the point, bounded per family by the
integrity tests) and `max_sector_double_pole_relative_error`. Per-helicity
runs (`per_helicity.rows[point][configuration].reference`; the manifest's
`helicity_reference` names the row's run): at quadruple-precision entries the
Born is the entry's double pole over the universal factor (the IR double pole
is helicity-diagonal; the printed value is kept as `born_binary64_input`).
Only a vanishing configuration (Born <= 1e-12 of the point's summed |Born|)
compares absolutely against that sum (§1.4: absolute only for what vanishes
identically); every other one is strictly relative. An entry whose
quadruple-precision test failed (4xx) is no reference (status `none`), and so
is, at points that are not MadLoop's own quadruple-precision points, one whose
printed binary64 Born misses its quadruple-precision Born by more than 1e-13:
its value then depends on MadLoop's ~1e-16 repair of the binary64 rounding of
the point (g g > g g g's configurations suppressed to 1e-11 .. 1e-4 of the
sum at the exact points of `gg_ggg`). The A08 per-helicity reference is
therefore `gg_ggg_hel` at MadLoop's own quadruple-precision points
(`--madloop-qp-point`), where every non-vanishing configuration, down to
2.7e-9 of the sum, is a relative reference. The merge refuses a point whose
MadLoop squared split orders violate the universal double pole beyond its
tolerance unless `--point-status` declares it, and the MadLoop run refuses
non-finite values anywhere in its output (sectors and helicities included).

MG5_aMC 3.7.0 Born defect. `born_matrix.f`'s `JAMP(colour, amplitude split
order)` is a local array that is never zeroed; a colour flow without an
amplitude of some split order (u u~ > t t~ QCD<=2 QED<=2: the colour-singlet
flow has no QED amplitude) keeps uninitialised stack memory, which entered
MadLoop's Born sectors (G02 point 2: QED^4 Born 3.6e9 instead of 9.6e-3, Inf in
other runs). `build_madloop` compiles a copy with `JAMP(:,:) = 0` into the run
directory (`references.fix_unassigned_jamps`; only incomplete subroutines are
touched, recorded as `mg5_born_matrix_repairs`); of the 93 Born matrix elements
under `runs/` only that export needs it, and its loop sectors are unchanged.

Light massive pairs (b, c, mu) cannot reach sqrt(s) >=
800 GeV with terminating parameters: `exact_points.py` now refuses them
instead of searching forever, and those rows use `supplied_points.py`.

## M-SM reference campaign (`msm_campaign.json`)

The MadLoop references of the M-SM milestone (`workspace/reports/engine-v2/m-sm/PLAN.md` §4, package MS-REF),
driven by the M-QCD runner with the campaign's layout:

```bash
source workspace/reference/env.sh
export LOOP_REFERENCE_ROOT=workspace/reference LOOP_REFERENCE_PYTHON=python
C="python tools/loop_reference/mqcd_campaign.py --campaign tools/loop_reference/msm_campaign.json"
$C export uux_emep_ew && $C points uux_emep_ew && $C run uux_emep_ew && $C merge uux_emep_ew && \
$C fixture uux_emep_ew && $C manifest
```

| File | Role |
|---|---|
| `make_msm_campaign.py` -> `msm_campaign.json` | the 70 core rows of §4.2 (the decay rows wait for the user's Q3) and SC10 (z z > h h: the R2 vertices of the coupling R2_ZZHH, MS-UFODB) with their model codes (`restriction_codes`: G0, Ga, Gb, Gm, Gk, Gt, Gc, Gca, Lc, Az, L5) and 71 MadLoop runs; `layout` puts work directories under `runs/msm/`, fixtures under `tests/fixtures/loop/required/msm/` and the manifest at `required/msm_references.json` (`msm-references/1`) |
| `required_processes.json` | new schemes `ew-gmu-a0`, `ew-gmu-cms`, `ew-gmu-a0-cms`, `qcd-cms`, `ew-gmu-ckm`, `ew-gmu-mm`, `ew-gmu-tech` and the `role: msm` processes (new keys only) |
| `madloop_ct_couplings.py` | the UFO counterterm couplings behind an export's calls (`<export>.ct_couplings.json`; madloop_export.py writes it for new exports) |
| `madloop_parameters.py` | model parameters of an export at a run's card per mu_R (`<work>/export_parameters.json`, copied into the fixture of a run listing `export_parameters`: CM09's complex photon conversion parameter) |
| `madloop_components.py` | rule-5 components per loop sector (bare / R2 / UV-CT, via `madloop_ct_selection.py`, classified by the UFO couplings of the calls) on one row per class: `required/msm/components/<run>.json` |
| `required/msm/existing_r2_couplings.json` | the UFO R2 couplings the exports of the existing EW references insert, written by `$C existing-r2` (`runs/required/<name>/madloop-export` of `required/<name>.json`, else the row's `existing_r2_exports`: the LL01/LL02/SC01/CM01 controls have `--no-compile` exports of their MadLoop commands, `runs/msm/*_ctl/`, whose attached CT vertices, UV CT and loop counts equal the legacy generation's); `without_r2_list` names the QCD-only fixtures; the manifest links each existing reference to its entries |

Evaluation as M-QCD: every point in MadLoop's quadruple-precision stage, `HelicityFilterLevel = 0`, every
squared split order printed. What M-SM adds:

* **Joint requests.** A `[virt=QCD QED]` request over several loop sectors lists `corrections` (primary first);
  `correction` stays the ROW sector. Each loop sector names its Born sector per correction (`born_sectors`), and
  its universal double pole is the sum over corrections of factor x Born (`universal_double_pole_factors`; a mixed
  sector of a mixed Born gets both). Explicit squared orders on every job (`QCD^2<=99 QED^2<=99`): without them
  MG5 drops the highest-alpha sector of mixed-Born requests (u u~ > t t~, u u~ > d d~ g).
* **CMS.** `complex_mass_scheme True` exports with the card widths of the default restriction; an external unstable
  multiplet has width 0 per process (`parameter_overrides`); the merge's loop alpha is the complex-mass G_mu one
  (`sqrt(2) Gf |mu_W^2 (1 - mu_W^2/mu_Z^2)| / pi`, GfRedefinitionChoice = 1); fixtures record `complex_mass_scheme`
  and `scheme_conventions` (CMSParam, LogSwitch, GfRedefinitionChoice). MG5 3.7.0 refuses loop_sm under CMS
  unless its electroweak inputs switch (`sminputs (2,) not define` whenever no W width is set at import, also on
  the stock `no_widths` restriction), so `qcd-cms` uses `loop_sm-no_b_mass` with MG5's switch to (aEWM1, MZ, MW)
  and MW = the tree-level value of the alpha_fixed scheme (identical couplings), WW = WZ = WH = 0 at run time.
* **R2 name lists.** Every fixture records the UFO R2 couplings its export inserts (`madloop_r2_couplings.called`,
  per subprocess directory), the input of the rule-1 R2 correction (MadLoop inserts an R2 coupling only for loops
  whose propagators match its label: `R2_G0tt_b` is absent from every massless-b export of the unpatched models; the
  patched ones split it by loop content and their exports call `R2_G0tt_b_WG`). The export's call names
  do not give them: MG5 renames couplings with identical expressions at the UFO conversion and merges couplings of
  equal value at the restriction point, up to a sign (`R2_uuA2Cp` is called as `R2_ccA2Cp`, `R2_GTT2Cpb` as
  `R2_GCC2Cps`, the UV coupling `c_UVvexveA1EW_1eps` as `R2_AWWcs`). `madloop_ct_couplings.py` regenerates the
  export's amplitudes with its own MG5 settings, records both renamings and the R2 vertices attached to the loops
  (`<export>.ct_couplings.json`, checked against the export's sources); `called_as` lists the merged call names.
* **Photons.** Processes with tagged photons record `tagged_photon_legs` (0-based legs of MG5's alpha(0) formula,
  Q1 (a): final-state photons); MadLoop standalone converts none, so the values are raw.
* **Multiparticle.** `p p > e- e+` / `p p > t t~` exports include MG5's photon-initiated members and a loop-squared
  `g g > e- e+ [sqrvirt]` member, recorded as skipped (Q2 (a)); one run per Born subprocess directory.
* **Special points.** `supplied_points.py --sqrt-s` (one point per listed sqrt(s), no resonance exclusion: CM02/CM03
  at M_Z and M_W, VV01 at 4 TeV). The VV05 radiation-zero run evaluates one point per job: after MadLoop's
  initialisation at a Born-zero point, the regular neighbour's QCD double pole missed the universal one by 2.9e-5 in
  a three-point job (alone: 1e-15).
* **Long one-point jobs.** CM07 (g g > t t~ e- e+ g under CMS) runs one job per point (`split_points`, ~27 min
  each).
* **IR single pole.** `test_loop_reference_msm.py` checks the single pole of every EW sector photon exchange alone
  reaches (lowest QCD order of the Borns) against the QED IR anomalous dimension with massive legs (2e-8 (alpha/2pi)
  Born). It caught SC02: MadLoop's quadruple-precision Ninja stage had the e^6 sector of u u~ > mu- mu+ (massive
  muon, m^2/s ~ 1e-9) wrong at 3 of 4 points with its own test passed; the run uses CutTools
  (`madloop_params: MLReductionLib = 1`, a run's own parameters over the campaign's). Model properties the check
  records (the engine on the same UFO reproduces them; MS-VALIDATE's rule 4 sees them): `ew-gmu-mm` keeps the
  massless muon's counterterms (`massless_field_counterterms`: +3/2 Q^2 (alpha/2pi) Born per muon leg, up to
  O(m_mu^2/M_W^2)); `ew-gmu-ckm` keeps the tau-mass residual of the patched models (their EW counterterms omit
  MTA; `ir_single_pole_remnant`); before the UFOmodeldb issue-1 patch its O(lambda^3) Wolfenstein CKM was not
  unitary and the EW single pole missed by -2.1e-2, -8.1e-4, -5.0e-5 (alpha/2pi) Born at lamWS = 0.2253, 0.1, 0.05.
* **Double-pole summary.** The merge now leaves absolutely compared rows out of
  `maximum_universal_double_pole_relative_error` and lists them in `universal_double_pole_absolute_rows`; M-QCD
  fixtures merged before (`mqcd/udx_wpa_zero.json` has absolute rows) keep the old maximum over all rows (no test
  reads it; a re-merge would change only that field).
* **ST04** commits ew-validate's workspace run `udx_tbx_ew_mb` as `required/udx_tbx_ew_mb.json`, re-merged with
  Recola excluded (it differs by 9.48e-5 x Born: the G_mu UFO's CT couplings omit `dMB_eCoup_UV_EW`, the b-mass term
  of the charge counterterm, a UFO defect found by MS-UFODB; MadLoop and pyAmpliCol read the UFO).
* **Patched models (MS-UFO-PATCH).** Every EW scheme but the `ew-gmu-mg5` control reads
  `models/ufodb-6ca4b120-patched/` (UFOmodeldb with the issue-1 model patch, README.txt there). The rows the patch
  changes have new runs on it with Recola as second provider: LL10 `emep_ttxh_ew`, TT04 `ttx_ttx_ew`, SC09
  `ttx_zh_ew`, ST04 `udx_tbx_ew_mb` (at the existing fixtures' points, which they supersede), TT05 `gt_tttx_ew`, TT06
  `gb_ttxb_ew_mb`, SC04 `bbx_wpwm_ew_mb` (+ its e^6 control `bbx_wpwm_ew_mb_qed`, MadLoop and Recola) and SC03
  `udx_epve_ew_ckm` (Recola's SM model has no CKM); MadLoop = Recola to <= 5.3e-11 on all of them. The runs of the
  unpatched model that were regenerated in place are under `runs/msm-ufodb-6ca4b120/`. `ew-gmu-ckm`'s single-pole
  remnant is now the tau-mass residual MTA^2/(2 sw^2 (s - MW^2)) (alpha/2pi) Born (`tau_mass_counterterms_omitted`,
  checked exactly by `test_loop_reference_msm.py`).

## NJet: the all-gluon ladder up to g g -> g g g g g (`njet/`)

NJet ([arXiv:1209.0100](https://arxiv.org/abs/1209.0100); home
<https://bitbucket.org/njet/njet>) is an independent reference for
g g -> (n-2) g, n = 4..7, in massless QCD. It is used because MadLoop and Recola
cannot generate g g > g g g g g within MASTER_PLAN 0.1 and OpenLoops has no
library for it. NJet needs no per-process generation: its colour sums are
compiled into the library.

| File | Role |
|---|---|
| `njet/build_njet.sh` | Release build of QD and NJet out of tree into a new build directory, with `--enable-5jet` (the 2->5 channels) and double-double (`--enable-f128`, NJet 3; NJet 2 always builds it with its bundled QD). It writes `build-info.txt` with the compiler, configure lines and the flags actually used. |
| `njet/njet_driver.cpp` | Driver. `blha` mode goes through NJet's BLHA2 interface (`OLP_Start`/`OLP_EvalSubProcess2`, contract signed by the build's own `njet.py`). `direct` mode uses `NJetAccuracy` with the standard (`Amp0q<n-2>g`) or de-symmetrised (`..._ds<n-2>`) sum, with (`virt`, two evaluations) or without (`virt_single`, one evaluation) the scaling test, in `double` or `dd` (`dd_real`). It applies the BLHA normalisation of `njet_olp.cpp` verbatim and the same leg order and axis handling. |
| `njet/run_njet.py` | `points` (exact points: `exact_points.generate` in pyAmpliCol's order, or a fixture's points); `run` (pinned CPU, result JSON with provenance); `openloops` (the matching OpenLoops 2 values with `nf` 6 (top loops, as the fixtures), 5 or 0); `compare`; `calibration`; `timing` (Markdown table). |
| `njet/run_njet.py run --nc N` / `nc-entry` | MQ-NC's N_c oracle (`tests/fixtures/loop/nc/njet_nc_scan.json`): NJet at N_c = N (`NJetNc`). Direct mode (all-gluon channels) keeps the N_c = 3 colour average of its normalisation; `--mode blha --process '2 -2 -> 21 21 21'` (any massless QCD channel NJet's `njet.py` maps, legs in the points' order) writes `Extra NJetNc N` into the order file, so NJet divides by its colour average at N_c (N_c per quark, N_c^2-1 per gluon), and the result multiplies born and Laurent coefficients by avg(N_c)/avg(3) (`colour_average`, raw values under `njet`). `--multiprec 1 --precision 1e-30` re-evaluates every point in double-double. On g g > g g and g g > g g g the corrected BLHA values equal the direct double-double ones within 3.2e-15. `nc-entry` writes one fixture entry from runs at several N_c. |
| `njet/njet_fixture.py` | `build` writes `tests/fixtures/loop/required/gg_ggggg_njet.json`; `compare` compares a pyAmpliCol record (`campaign.py` `virtual` or `loop_v2_generate.py poles` `bare`) with it. |

Versions. NJet 3.1.2 (latest release, `njet-3.1.2.tar.gz`, sha256 `b1d49355...`)
with QD 2.3.24, and NJet 2.1.1 (`njet-2.1.1.tar.gz`, sha256 `3858ad37...`, bundled
QD). Both use gcc/gfortran 15.2.0 (workspace `env.sh`) and NJet's own flags
`-std=c++17 -O2 -march=native -mtune=native` (host-tuned; the shipped Makefiles
lower the 2->5 colour sums to `-O1` in double and `-O0` in double-double).
NJet 2.1.1's bundled QCDLoop needs `FFLAGS=-std=legacy` with gfortran >= 10.
Sources are under `workspace/reference/sources/njet-<version>`, builds under
`workspace/builds/njet-<version>-release`.

NJet defects and limits found here (the first is visible in NJet's own
`examples/runtest.py`):

* NJet 3.1.2's numerical five-gluon channel (`Amp0q5g`, used when the analytic
  `--enable-an0q5g` is off) returns the one-loop interference exactly 9/2 too
  large in all three Laurent coefficients (`runtest.py -r NJ_3j`: A1_2 = -135
  instead of -2 n N_c = -30; Born correct). NJet 2.1.1 is correct there, so
  g g -> g g g uses NJet 2.1.1. The four-, six- and seven-gluon channels of
  3.1.2 pass (`NJ_2j`, `NJ_4j`, `NJ_5j`).
* Exactly planar 2->2 points whose scattering plane contains NJet's spinor axis
  (y; e.g. all p_y = 0 or all p_x = 0) give wrong values or NaN in double and
  double-double. The scaling test flags them. The g g -> g g calibration set
  therefore uses the six exact points with generic orientation plus four
  exactly rotated copies.
* More generally NJet's numerics depend on the event orientation. At the seven
  gluon `exact_points` points as generated (beams along +-z), NJet 3.1.2 and
  2.1.1 keep only 4-6 digits in double precision (single pole against the
  Catani prediction: 3e-6 to 1e-4) and return NaN at 3 of 10 points; the
  double-double mode with QCDLoop's double-only integrals is not better (1e-5
  to 1.5e-2). At exactly rotated copies (`run --rotation R1|R2`) the same code
  agrees with the Catani poles to <= 3e-9 and the two orientations agree in the
  finite part to <= 7e-9. The seven-gluon reference therefore uses rotated
  points; the virtual is a Lorentz scalar, so the values belong to the points
  as given. For a double-double reference NJet is built `--with-oneloop`
  (OneLOop's double-double integrals; QD built with its Fortran module).
* NJet 3.1.2 returns zero colour-correlated Borns for six and seven gluons;
  `run_njet.py catani` uses NJet 2.1.1's (colour conservation to 1e-15).

Conventions (derived, no fitted factor). NJet's BLHA output with
`IRregularisation CDR` and `NJetRenormalize yes` is 2 Re<M0|M1> with physical
couplings: `born * g_s^(2(n-2)) / rfactor`, loop times `g_s^2/(16 pi^2)`, where
`rfactor = 4 * 64 * (n-2)!` is the initial helicity and colour average times
the final symmetry factor (`njet.py`). Its primitives are FDH, unrenormalised,
normalised with c_Gamma; `NJetRenorm` adds the FDH->HV conversion
`-(n_g N_c/3 + n_q C_F)` plus `(n-2) N_c/3` and the MS-bar counterterm
`-(n-2) beta_0/eps` with `beta_0 = (11 N_c - 2 N_f)/3`, in units of
`alpha_s/(4 pi) B`. Since `c_Gamma = 1/Gamma(1-eps) + O(eps^3)` this is the
MadLoop/BLHA `C_eps=(4pi)^eps/Gamma(1-eps)` convention of the required fixtures.
The calibration confirms it with no conversion: NJet (CDR, `N_f`) equals
OpenLoops with the same quark content. OpenLoops' libraries ship separate
process variants with `nf=6` (massive top in the loops, the fixtures), `nf=5`
(massless five-flavour QCD, available for g g -> g g and g g -> g g g g) and
`nf=0` (no quark loops).

NJet has no massive quark: the fixtures' and pyAmpliCol's `loop_sm` (MT=173,
top decoupled from alpha_s) differ from NJet's five-flavour QCD by the
top-loop contribution T, which changes only the finite part. The
`gg_gggg` fixture is reproduced as NJet + T with T = OpenLoops(nf=6) -
OpenLoops(nf=5); the decoupled top shifts no pole. For a bare (no counterterm,
no R2) `loop_sm` virtual, the single pole is shifted by
`(alpha_s/4pi) B [(n-2) beta_0(5) + (8/3) T_F]` (`njet_fixture.py` derives it).

Typical use (`LOOP_REFERENCE_ROOT=workspace/reference`, any directory):

```bash
tools/loop_reference/njet/build_njet.sh $SRC/njet-3.1.2 $SRC/qd-2.3.24 workspace/builds/njet-3.1.2-release 48
python tools/loop_reference/njet/run_njet.py points --legs 7 --count 10 --mu-r 1000 --output gg_5g.json
python tools/loop_reference/njet/run_njet.py run --njet-build workspace/builds/njet-3.1.2-release \
  --driver-dir $LOOP_REFERENCE_ROOT/runs/njet/drivers --points gg_5g.json --prec dd --cpu 230 --output dd.json
python tools/loop_reference/njet/njet_fixture.py compare tests/fixtures/loop/required/gg_ggggg_njet.json <pyAmpliCol record>
```

Runs, calibration and timings are under `workspace/reference/runs/njet/`; the
report is `workspace/reports/engine-v2/njet-benchmark.md`.

## Legacy-engine oracles for the v2 engine (WP0.1)

The legacy per-diagram engine was removed (user ruling 2026-10-28, M-QCD Q3);
its outputs are frozen. `legacy_capture.py` captured them before the v2 engine
replaced it (its capture code is in the git history; the module keeps the
control set and conventions the fixtures are read with) (oracles O1 and O2 of `docs/development/loop_v2/DESIGN.md` section
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
  at the first point;
* `tests/fixtures/loop/legacy/<name>.<accuracy>.json` (projection only,
  `--projection lc|nlc`, `PROJECTION_CONTROLS`): one colour projection of a
  control whose full capture is out of reach, at its first point, with its
  colour degrees. uu~->uu~uu~ (three identical-flavour lines) takes about
  75 min and 22.5 GB per accuracy on one thread (program 3987 s, 200-bit
  evaluation 543 s; 2026-10-27).

It uses the generic source compiler on MG5_aMC `loop_sm` with `MB=0` (the
providers' `loop_sm-no_b_mass` scheme), the points of the committed provider
references, and stores the engine's own decimal strings, so a rerun reproduces
the files byte for byte:

(The capture command, `legacy_capture.py --ufo <MG5>/models/loop_sm
[--process ...] [--check]`, no longer exists: the engine it ran was removed.
The last captures, for the former live comparisons of the v2 tests, are
`tests/fixtures/loop/legacy/reduction/`, `ew_families_*.json.gz`,
`gg_gg_non_default_parameters.json`, `gg_ttx_model_defaults.json` and
`gg_gg_qcd_qed_sm.json`, each with a one-line provenance.)

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
