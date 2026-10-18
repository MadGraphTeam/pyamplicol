# One-loop reference controls

These small controls compare the Born–loop interference for
`u u~ > d d~`, with pure QCD Born/loop coupling powers 2/4. They are an
independent reference harness, not a pyAmpliCol loop implementation or a
performance acceptance campaign. The initial control uses binary64; it does
not establish DoubleFloat or arbitrary-precision support.

All provider sources, downloads, builds, logs and run directories belong in
the task's `workspace`. Keep the supplied `FOR_REFERENCE_ONLY` sources read-only.
The scripts accept paths and do not depend on the original task location.

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
workspace output. Build with `--case drell-yan --madloop OUTPUT`; run with
`--fixture tools/loop_reference/drell_yan_qcd.json --providers madloop`.
The other two native drivers are specific to the four-quark control and
cannot be used for the photon-only fixture. Both controls set the inverse
electromagnetic coupling explicitly (132.507 by default).

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
average initial spins/colours. No identical-final-state factor occurs.

Results include physical couplings and UV/R2 contributions. They return
`finite`, `single_pole`, `double_pole` in the MadLoop/BLHA convention
`Cepsilon=(4*pi)^epsilon/Gamma(1-epsilon)`. Recola's finite coefficient is
translated by adding `pi^2/6 * double_pole` at matched scales.

OpenLoops explicitly sets `truepoles=1`, `polenorm=0`, `ct_on=1`, `r2_on=1`,
`iop_on=0`. Recola explicitly sets `dynamic_settings=1` and
`compute_ir_poles=1`; its `NLO-IR1/2` values come from repeated integral
evaluation. That extra work remains inside its timing. MadLoop returns its
computed Laurent coefficients directly, without Born or alpha_s division.

Alongside pairwise provider agreement, the runner checks the analytic Born
value `4/9 * g_s^4 * (t^2+u^2)/s^2` and universal double pole
`-4*C_F*alpha_s/(2*pi)*Born`, with `C_F=4/3`. Agreement uses relative
tolerance `2e-9` with a `1e-3` scale floor. This deliberately small smooth
control does not replace later threshold, cancellation, singular-region,
coupling-order, correlation, colour-expansion or precision validation.

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
