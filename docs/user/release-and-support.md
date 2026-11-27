---
title: "Release and Support"
nav_order: 5
parent: "Profiling and Benchmarking"
---
<!-- SPDX-License-Identifier: 0BSD -->

# Release and Support

pyAmpliCol 1.0.0 is the software release accompanying the official arXiv
publication, *pyAmpliCol: fast tree-level matrix elements*. Binary wheels and a
source distribution are available on [PyPI](https://pypi.org/project/pyamplicol/).
This page records the supported release boundary and explains how to report a
problem.

## Current release boundary

Version `1.0.1` is represented by the immutable
[`v1.0.1` source snapshot](https://github.com/MadGraphTeam/pyamplicol/tree/v1.0.1),
the [GitHub release](https://github.com/MadGraphTeam/pyamplicol/releases/tag/v1.0.1),
and [PyPI release](https://pypi.org/project/pyamplicol/1.0.1/). Its validated
inventory is one source distribution and three `cp311-abi3` wheels:

- macOS 11 or newer on Apple silicon;
- macOS 11 or newer on x86-64;
- manylinux 2.28 on x86-64.

The [release-artifacts workflow](https://github.com/MadGraphTeam/pyamplicol/actions/workflows/release-artifacts.yml)
installs each wheel into a clean CPython 3.11 environment and exercises the
Python, C11, C++17, Fortran 2008, and Rust 2021 APIs. It also runs a CPython
3.14 abi3 smoke test, source preflight, and independent Fortran physics oracle.
Publication uploads these already validated files without rebuilding them.

Version 1.0.1 uses published Symbolica 3.0.0, SymJIT 2.26.4 and
ufo-model-loader 1.0.0, as recorded in the dependency lockfiles. No local
dependency source patches or unpublished wheels are needed.

## 1.0.3 release

The 1.0.3 tag was moved to the main that combines the
multi-threaded runtime, the check verdicts and the changes below; "the earlier
1.0.3 tag" is its first position.

**The one-loop runtime uses its threads.** Until now the reduction, most of
a one-loop call's time, ran on one thread whatever `threads` allowed: 8
threads gained x1.0 to x1.1 on loop-induced processes with NinjaRS and at most
x2.9 elsewhere. Both reductions now run in parallel on the runtime's own pool
(NinjaRS in binary64 over slices of lanes, TIRust in every carrier over
slices of kinematic rows; the check frames, the cancellation rescue and the
lane rescue included), and so do the tree programs (with a faster state
layout), the tree interferences and the scatter of numerators into lanes;
more of the result's assembly is native, and NinjaRS's master-integral cache
looks rows up faster (also on one thread). One 16-point call on 8 cores
(binary64, unchecked) is about 5.5 times faster than on one on
`g g > g g g g` with either reduction, 3.5 on `g g > h g g` with NinjaRS (2.3
with TIRust), 3.3 on `g g > z z` and `g g > g g g`, 2.2 on `g g > t t~ g` and
`u u~ > e+ e- g g` ([Configuration](configuration.md#threads): what runs in
parallel and what does not scale).

Compatibility: results do not depend on the thread count, bit for bit (every
value, diagnostic, rescue and uncertified record, checked and unchecked, every
carrier and batch size, both reductions). One thread gives the values it gave
before this change, bit for bit, with one exception: TIRust's workspaces are
now lane-independent (a lane starts from the plan's base variant instead of
the variant the lane before it selected), so where a TIRust result depended on
the lanes reduced before it in the same workspace, it is now the value the lane
has in a fresh workspace. Such a dependence needs nearly degenerate rows: on
the earlier 1.0.3 tag a checked double-double rank-1 box evaluated after an
exactly dependent box differs from its fresh-workspace value by about 1.4e-9
relative; no value of the shipped and profiled processes changes. Also on one
thread: a failed master integral counts once per reduction call (no longer once
per failing row); a reduction call that fails leaves no master integral cached
(the next call starts as after a clear) and no template it built; a binary64
NinjaRS reducer given a vanishing reason before its first routed lane now
applies it to that lane (before, the reason reached only an exact engine that
already existed). For direct Rust users of the reduction crate, the new
`MasterCache::begin_call` opens a grouped call and returns its handle: inside
it a failed row is evaluated and counted once, and an ordinary `evaluate` asks
the provider again for a failed row, as before. On a cache shared by several
engines, a failure is remembered only by the grouped call open when it is
recorded: a late failure from an ended call no longer clears or replaces the
open call's failed rows. A reduction call that fails returns the outcome of the
serial call (the error or panic of its first failing step) at any thread count.
For direct Rust users, the refinement callback (`GroupRefinementSource`) can be
asked for a lane concurrently, speculatively and more than once: the outcome
equals the serial one when a lane's answer or panic is the same whenever it is
asked (a callback that panics only once, next to a failure in a later bucket,
can make a parallel call return the other failure); a caller that needs ordered
effects can use one thread. The one-core cost is unchanged or lower with
NinjaRS and up to about 1.5 % higher with TIRust from lane independence alone
(with the faster assembly, lower overall).

Limits: NinjaRS in double-double and arbitrary precision stays at about
one-thread speed (parallel over buckets only, on one set of built templates),
and so do tree programs with exact (double-double, arbitrary-precision, or
binary64 without the compiled kernels) evaluators (one built evaluator, never
copied per worker); the Python assembly of the result runs under the
interpreter lock; the dressing of a small process has few families to share
out; a TIRust row refused by its gates has its method choice as one serial
computation; very small calls (a few milliseconds) do not gain from threads and
can be slower on several than on one. Memory: with TIRust each extra worker
holds TIRust's own per-thread method-choice state (about 120 MB on
`g g > g g g g`, a few MB to 75 MB on smaller processes), bounded by the plans
and not growing with the calls; with NinjaRS a checked call that reaches
arbitrary precision holds up to about 50 MB per extra worker during the call.

**TIRust, NinjaRS and oneloopmaster re-pinned.** TIRust moves to its main
(`c20d0be2`), which carries the lane-independent workspaces above
(huashengshao/TIRust#63) and, since `1c130a81`, decides degenerate
kinematics at the inputs' rounding, leaves rank-0 triangles at degenerate
invariants to MPFR (#61), gates triangles near a vanishing Källén function
by their Passarino-Veltman error growth, with a fixed-precision floor that
refuses them in binary64 and double-double whatever the gate (#64), and
sends a triangle refused that way to a higher precision instead of its
affine-relation variants, which could serve it O(1) off as a success (#72).
It holds a relation's constant denominator identity to the inputs' rounding,
so a nearly dependent triangle with a small relation constant no longer
takes the relation (#76), and keeps exactly dependent triangles on their
relation at a stability threshold of 0 (#77). pyAmpliCol re-reduces a lane
TIRust refuses in binary64 in double-double, then 500 digits (the lane
rescue, in the checked and the unchecked mode alike); on the tested
processes and points, with the lane rescue enabled, no point that was served
before was observed to fail. With the lane rescue off (`lane_rescue=False`),
the floor also refuses such triangles at the unchecked reduction's gate-0
last resort, so an unchecked evaluation can fail where the earlier pin
served it (on `u u~ > t t~ g g`, 6 of 16 flat points, which the earlier pin
served within 4.2e-6 of double-double); with the rescue on (the default)
they are served from double-double. A refused point whose best-effort
evaluation fails only in the rows of its uncertainty's checks keeps its
unchecked value, as best-effort without an uncertainty. TIRust-reduced
values move where a lane changes route: in the regression suite by at most
3.5e-11 relative, and by 2.6e-9 on one `u u~ > e+ e- g g` point whose own
binary64 error is 7e-9. On recorded stability points no point below 10.5
digits loses more than half a digit, and some `d d~ > d d~ z z` and
`g g > g g g` points gain a digit. A 16-point call with TIRust costs up to
about 7 % more on one core where NinjaRS is the default reduction
(`g g > g g g`, `g g > t t~ g`, `u u~ > e+ e- g g`) and up to about 2.7 %
elsewhere. oneloopmaster moves to `cdbc912` (#21: a cancellation-free series
of the native binary64 and double-double C0 at small external momenta, the
revision TIRust pins), and NinjaRS with it: NinjaRS-reduced values (the
default for Born-interfered processes) are unchanged bit for bit except
where that series acts (one `g g > t t~ g` point of the regression suite,
its resolved entries by at most 9e-14 relative and its checked stability
estimate by 1e-7 of itself). All three then move to oneloopmaster `a4b16f70`
(#25: a scalar box with a massless line soft between two on-shell massive
lines at a vanishing channel returned NaN or an unrelated value, one of which
the 512-bit tier served as a success; #23: the small-momentum C0 series at
extreme mass ratios); NinjaRS and TIRust change only their oneloop pin. No
value, diagnostic or executor counter moves in the regression suite (at 1
and 8 threads) or on 7,100 evaluations of recorded stability points, and the
instructions a one-core TIRust call retires are unchanged (within 0.3 % per
16-point call on `g g > g g g`, `g g > t t~ g` and `u u~ > e+ e- g g`): the
fixed box needs kinematics none of these points reach.

Dependencies: TIRust `c9c4d126` (main: `c20d0be2` with oneloopmaster
`a4b16f70`), NinjaRS `41e21234` (main: `1f3d9d0e` with oneloopmaster
`a4b16f70`), oneloopmaster `a4b16f70`; the other pins are unchanged.

**Check verdicts: one rule, R < K P, for every check row.** Every verdict of
`pyamplicol check` and of the generation-time loop-induced probes is one
relative test per independently required row (a point, a squared-order
sector or loop order and helicity row, a leg and factor, a Laurent
coefficient): the row passes when its residue R is below K times its physical
reference P, the size of the physical quantities whose difference or
vanishing the identity tests. K is `check.tolerance` (`--tolerance`), by
default the requested accuracy `evaluation.reduction_target` (1e-5). A
known-zero reference is judged against the row's term scale T
(term-relative); a row with no contributing term is vacuous (skipped and
counted); a row whose P may be noise is evaluated at the next carrier at the
same point, where P either reproduces, collapses with the carriers' noise
(then judged term-relative) or leaves the row inconclusive (exit code 4,
never a pass); a loop-induced row below the numerical resolution of its
helicities is deferred to the next carrier. Carriers per row: binary64, then
double-double for the rows binary64 does not decide, then (Born-interfered)
arbitrary precision. The error estimate is still reported but decides
nothing; "undecided" is no longer produced. The generation-time probes read
the same K, the campaign manifest and the stored-process harness judge with
the same rule and record it, and non-finite, refused or missing operands are
inconclusive instead of raising. Behaviour changes: g g > Z generates (its
forbidden helicity rows are below numerical resolution: inconclusive with a
warning, `check` exits 4); g g > h a and g g > h settle in double-double;
c c~ > h h has nothing to test (vacuous, with a warning); the
`loop_gg_epemmpmm` example passes `check`. Evaluation values are unchanged.

**Fixed parameters now define the masses of the generated points.** In 1.0.2
and the earlier 1.0.3 tag (every one-loop artifact), a card's `[loop.preparation]
fixed_parameters` were bound by the amplitude but ignored by the kinematics:
the artifact's validation point, the points of `check` and of the
generation's probes and, in the earlier 1.0.3 tag, the flat phase-space points of `evaluate`
and `profile` (which took their masses from the validation point) were drawn
on the model's own masses, and `model/parameters.json` stated the model's
values. Where a fixed parameter changes an external mass, every such point was
off the shells the amplitude binds and its value was returned as `success`
although it is no amplitude: `g g > t t~ h` with `MT = ymt = 173`, `MH = 125`
on `loop_qcd_qed_sm_Gmu` / `with_b_mass_no_width` (174.3 / 120) was profiled
with tops 1.5 % and the Higgs 7.8 % off shell in p^2, its double pole up to
0.2 off -2 C_A (alpha_s / 2 pi) Born and the two reduction backends up to an
order apart (on shell: Catani's pole to 1e-10, the backends to 1e-24,
MadLoop and Recola agree). `check` was not affected (it re-shells its points
on the masses it binds). Now one evaluator gives the bound external masses
(from the exact parameter texts, on the effective binding, a derived mass
rounded once) to every generated point; the flat points of `evaluate` follow
the parameters given at evaluation (`--model-parameters`), `profile`, the
benchmark runner and the Python profiling functions (`benchmarking.
profile_virtual`, `profile_points`) refuse such parameters, and draw on the
masses the runtime they load binds, in the selected process's leg order; a
`profile --samples-output` file now also records the `selector` the profile
loaded and its legs' PDG codes (`external_pdgs`), with which its samples
are replayed (its `process`, the representative's id, does not give the leg
order of a selector that permutes the final state); the validation record states the
bound masses and `model/parameters.json` the bound values. In the checked
mode a shell-consistency screen marks a point off the bound shells beyond the
call's target as `uncertified` (its value still served; [Configuration](configuration.md#kinematics-improvement-of-the-input-points),
"The shell-consistency screen"); the unchecked mode is unchanged.

Compatibility: the values at given points (the same supplied momenta and
parameters) are those of the earlier 1.0.3 tag; the screen adds a diagnostic only. Newly
generated stored validation points are bit for bit those of the earlier 1.0.3 tag when every
external mass is an input parameter of the model and none is moved by a
fixed parameter; an external mass that is DERIVED (loop_sm's W) is now the
amplitude's own binary64 binding, which can differ from the former value in
its last bits (u d~ > w+ on loop_sm defaults: beam energy 40.209501222878089
became 40.209501222878082, MW 80.419002445756178 became 80.419002445756163);
no shipped example and none of the profiling campaign's processes has a
derived external mass. The flat phase-space SAMPLE drawn for a given seed changes
at rounding level for every process with a massive external leg (the masses
are now the exact bound ones, no longer re-derived from the stored point:
173.00000000000003 became 173): a profile's points before and after this
change are not the same bits, so the shards of one profiled row must all be
drawn by the same version. **Artifacts with an external mass fixed to another
value than the model's must be regenerated**: the Python runtime refuses to
load one (its stored validation point is measured against the masses it
binds) and the standalone flat-point drawer refuses its record; the native
SDKs' open does not check (a known gap, to follow), and stream files of the
stored benchmark tool keep their own momenta and parameters.

**NinjaRS no longer loses a lane's digits silently.** At ordinary phase-space
points a few NinjaRS reduction lanes lost most of their binary64 digits to
cancellation at a nearly degenerate cut (a triangle with two massive legs of
nearly equal virtuality) while reporting success: 122 of 10,000
`g g > g g g` points had fewer than 5 correct digits (the original Ninja
behaves the same; TIRust does not). In the checked reduction (the default of
`evaluate`, `check`, the SDKs, `profile --stability` and `profile --checked`)
NinjaRS now measures each lane's cancellation and reduces a lane whose
estimated error misses its target again, alone, in a higher precision: the
fast binary64 engine re-reduces the whole lane in double-double at the point
pyAmpliCol improved to exact energy-momentum conservation and exact on-shell
legs (callers that hold their momenta in a higher precision can supply them:
C `rusticol_virtual_evaluate_refined`, C++ `evaluate_refined`, Fortran
`evaluate(..., corrections=)`, Rust SDK `evaluate_refined`; the Python API
and the CLI read exact decimal momenta), and the generic engine (routed
binary64 lanes, double-double, arbitrary precision) climbs a precision ladder
chosen from the measured loss. The target is the existing
`evaluation.reduction_target` (default 1e-5 relative per point in every
arithmetic; `--reduction-target`; Python `reduction_target=`; SDK
`set_reduction_target`), held per lane at `reduction_target / 64`: a point's
error is at most its largest lane error times the cross-lane condition
number, measured at most 12 at five gluons, with a margin for higher
multiplicities ([Python API](python-api.md), "NinjaRS's cancellation
rescue").

A lane whose rescue misses its target is refused (`cancellation rescue:
estimated error ... target <= ...`) and goes to the lane rescue as before;
under the default `on_failure="best-effort"` a point left without a value is
returned `"best-effort"` with the better of its binary64 and re-reduced
values. Lanes served without accuracy evidence (below the resolution of their
own terms at the highest precision tried, vanishing within their own bound at
every carrier, or outside the rescue's domain without refined kinematics)
keep their value and status `"success"`, but are marked: Python
`VirtualLaneDiagnostic.uncertified` and `accuracy_established` false,
`profile`'s `uncertified` column and `uncertified_points` total, the CLI's
`evaluate --json` diagnostics and the native SDKs' diagnostics record
"uncertified" (per point id, its reasons). A binary64 lane the rescue refuses
whose re-reduced value is consistent with zero within the re-reduction's own
bound is served that way by the reduction itself, without the lane rescue (a
configuration that vanishes identically needs no Symbolica state, as in
the earlier 1.0.3 tag); given up: a lane that loses more than about 100 bits and is in truth
not zero comes back ~0 uncertified instead of being recovered at arbitrary
precision; a rescue policy (never met on an uncertified result) escalates
such a point to a higher carrier or returns it uncertified with the reason
(its stall rule can keep an uncertified level). The checks that read such
lanes (`pyamplicol check`'s Ward and pole rows and probes, the stored-process
checks) test their residue together with the lanes' reducer-stated absolute
bounds: a row the bounds cannot decide is `inconclusive` (exit code 4), never
a pass. Each point records what the
reduction rescued (`VirtualLaneDiagnostic.reduction_rescue`; `profile`'s
`reduction_rescue_lanes`, `reduction_rescue_carrier` and the backend totals
`reduction_rescued_*`).

**The switch.** The unchecked reduction (`evaluation.reduction_unchecked`,
`--reduction-unchecked`, the default of `profile --runtime`) has no trigger
and no rescue: its values are those of the earlier 1.0.3 tag bit for bit (1,322 of 1,322
points compared), at the same cost.

Measured (checked, binary64, default target, against double-double
references): `g g > g g g` (10,000 points) worst -4.88 -> 6.85 digits, below
5 digits 122 -> 0, below 8 491 -> 21; `g g > g g g g` (300) -2.34 -> 7.45;
`u u~ > e- e+ g g g` (500) -0.26 -> 7.44; `g g > t t~ g` (2,000) 4.47 -> 9.47.
Points without a re-reduced lane are unchanged bit for bit. Cost of the
checked evaluation (one core): +24 % on `g g > g g g`, +89 % on
`g g > g g g g`; the unchecked one is unchanged. Limits: a rescued binary64
lane keeps the binary64 numerator coefficients (about 8 digits where the
cancellation was catastrophic); some re-reduced points end a few tenths of a
digit worse than before (none below 7.7 digits measured); losses inside the
box mu-expansion and box Gram of the generic engine are not measured by its
trigger; double-double evaluations at the default target are unchanged (the
ladder acts at smaller targets); subnormal lane results of the binary64 fast engine
are outside the rescue's coverage; the Python reference executor has no
rescue and its NinjaRS-reduced points are marked uncertified.

Fixed: the UMAMI one-loop provider aborted a whole bulk call when one row was
returned best-effort.

Dependencies: NinjaRS `e1d94412` (main after alphal00p/ninjars#23); the other
pins and the Python dependencies are those of the earlier 1.0.3 tag.

**Changed default: a refused point no longer interrupts a run.** A one-loop
evaluation now returns, by default (`on_failure="best-effort"`; CLI
`--on-failure best-effort`; SDK `set_on_failure("best-effort")`), every point
of the batch: a point that no configured alternative accepts (the reduction
backend's own acceptance checks, `"auto"`'s per-point fallback, the last
rescue level) is evaluated again without the backends' own acceptance checks
(the `reduction_unchecked` machinery) and, where that yields a finite value,
returned with lane status `"best-effort"` (SDK `RUSTICOL_VIRTUAL_BEST_EFFORT`
= 5): never a success, with its refusal and an uncertainty (the stability
estimate of the call's checks together with the recommended checks, a
rotation and the rescaled reduction-direction check, run on the refused
points only: one rotation alone under-states the error of an unchecked TIRust
value; if none can be formed the record says so). A point with no value at all is a failed lane.
Nothing is printed, logged or raised for such points: the result carries it
as data (`result.statuses`, `result.warnings`, `result.has_warnings`; the
SDKs' statuses, `uncertainties` and the diagnostics' `"best_effort"` and
`"warnings"`), so Monte-Carlo logs cannot be swamped. Points the configured
alternatives accept are evaluated exactly as before (bitwise, same cost).
`on_failure="return"` keeps such points as failed lanes without computing a
best-effort value; `on_failure="raise"` is the previous behaviour (raise at
the first such point; the SDKs return `RUSTICOL_VIRTUAL_RUNTIME_ERROR`);
`result.emit_warnings()` turns a result's warnings into one filterable
`NumericalAccuracyWarning`. Failure reasons are bounded to one message per
reason class with the count of the others. Known, benign dependency log
events of `generate` and `check` (Symbolica's "Created infinity by raising 0
to the power of -1" from loop_qcd_qed_sm's unused `aEW0` conditional, the UFO
loader's exact float-to-rational notice) are returned in the result's
`warnings` instead of printed. See
[Python API](python-api.md#best-effort-values-of-refused-points),
[Command-line interface](command-line-interface.md) and
[Native APIs](native-apis.md#runtime-and-precision-boundary).

Version `1.0.3` adds loop-induced one-loop processes: processes without a
Born amplitude within their coupling-order limits (`g g > h`, `g g > z z`,
`h > g g`), served as |A_loop|^2 at full colour and evaluated as
`VirtualEvaluation` results with `contribution = "loop-induced"` (empty Born
fields, poles `"all"` or `"none"`, which vanish; zeros are reported within
their absolute estimate), see
[Configuration](configuration.md#processes-and-multiparticles) and the
[Python API](python-api.md#one-loop-virtuals-and-loop-induced-processes).
`process.loop_induced` routes them (`"include"` serves both kinds of a mixed
multiparticle request as separate contributions). Leading and next-to-leading
colour are refused for loop-induced processes. The native SDKs (C, C++,
Fortran, Rust, UMAMI) open loop-induced processes directly with empty Born
counts and the Python API's values, including the helicity-resolved and the
colour- and spin-correlated outputs (the correlated history `"born"` is
|A|^2 itself).

The one-loop numerators are reduced by one of two backends, selected by
`[loop] reduction` (the generation default) and `evaluation.reduction` (CLI
`--loop-reduction`, Python `reduction=`, the SDKs' `set_reduction`):
NinjaRS (integrand reduction) and TIRust (tensor-integral reduction, built
into the native extension by default). `"auto"`, the default, takes TIRust
for loop-induced and NinjaRS for Born-interfered processes; on TIRust a point
it refuses or fails is evaluated again on NinjaRS and recorded per point. In
double-double and arbitrary precision each point this fallback serves is
guarded by a rotation re-test of the promoted, improved point. The guard's
estimate is an estimate, not a bound: strongly suppressed helicity rows near
exactly forward kinematics can be served beyond their own 1e-5 (see
[Python API](python-api.md), "Near-forward accuracy"). An explicitly
requested backend that cannot serve a call is refused, never switched; every
lane records the requested and effective backend and the reason. TIRust's
target accuracy is `evaluation.reduction_target` (default 1e-5 relative per
point). `evaluation.reduction_unchecked = true` (Python
`reduction_unchecked=`, CLI `--reduction-unchecked`) is a timing mode
without the backends' acceptance and refusal checks and without an accuracy
certificate; it is off by default, so the backends' own checks stay on.

The input kinematics of double-double and arbitrary-precision evaluations are
improved to exact energy-momentum conservation and exact on-shell external
momenta in the working arithmetic with MadLoop's algorithms
(`evaluation.kinematics_improvement`: `"z-shift"`, the default, MadLoop's
variant 2 with its fallback to variant 1, finished by a frame-independent
projection only when the produced point is not exact; `"rescaling"`,
`"projection"` or `"off"`). Binary64 evaluations are improved only with
`kinematics_improvement_binary64 = true` (default false). Points whose beams
lie along the z axis keep MadLoop's values bit for bit. Leave the
improvement on above binary64: switched off there, near-forward points can be
served far off without a flag. See
[Configuration](configuration.md#kinematics-improvement-of-the-input-points).

Binary64 stability checks (rotations, the reduction-direction and rescaled
checks, the cross-backend check) are available in the Python API and every
native SDK (`rusticol_virtual_set_stability_checks`), off by default; the
recommended checks are one rotation with the reduction-direction and
rescaled checks. The Python API's stability rescue is a stack of
(precision, backend) levels: by default binary64, double-double, 57 digits
and 500 digits (for loop-induced processes TIRust then NinjaRS in binary64
first); a point whose estimate grows from one level to the next (a
numerical zero) is not escalated further. An explicit
`arithmetic="arbitrary"` without digits runs at 500 digits. Where
pyAmpliCol chooses the checks (the rescue levels, `profile --stability`),
TIRust's points also get the rescaled reduction-direction check.

A reduction lane that a backend refuses is rescued: only that lane is
reduced again in double-double, then at 500 digits, with its kinematics
rebuilt in that precision. The lane rescue is on by default, in the checked
and the unchecked mode (`evaluation.lane_rescue`, CLI `--no-lane-rescue`,
Python `lane_rescue=False`, SDK `rusticol_virtual_set_lane_rescue`).
Refusal texts name their cause (for example "box mu-expansion conditioning:
predicted error ..., allowed <= ..."). In arbitrary precision a NinjaRS
point whose lanes kept too few tracked bits fails. How these safeguards fit
together: [Python API](python-api.md#the-stability-machinery-end-to-end).
Evaluations no longer depend on what the process did before: after an
in-process generation or a state import they equal a fresh process bit for
bit. Large artifacts load much faster: the 8-gluon g g > g g g g g g loads
in 1.5 to 3 minutes and 10 to 15 GiB, against about 20 minutes and 23 GiB
before.
Full-colour and next-to-leading-colour Born-interfered virtuals take a
run-time helicity selection (`helicities=`) in the Python API and the native
SDKs.

The runtime settings of a one-loop runtime are supplied the same way in
every interface: one by one (keywords, flags, SDK setters) or together in a
runtime-options TOML, the run card's `[evaluation]` table (`evaluate
--card`, `Runtime.load(..., options=)`, `rusticol_virtual_set_options`;
a full run card is accepted). `evaluation.threads` (`--threads`,
`Runtime.load(threads=)`, `rusticol_virtual_set_threads`) bounds the native
threads of a runtime's load and evaluations; unset, `RAYON_NUM_THREADS` or
every core as before. See [Configuration](configuration.md#runtime-options).

`pyamplicol check` runs the pole (Catani; finiteness for loop-induced
processes), Ward and Goldstone checks of a one-loop run card or artifact,
regenerated in memory, escalating undecided rows to double-double and
arbitrary precision. Ward rows of a request with electroweak loop
corrections and an on-shell zero-width external massive quark read "not
applicable": the identity of that check is not guaranteed there. See
[Command-line interface](command-line-interface.md#check). Four one-loop
examples ship with the package (`loop_uux_ttxgg`, `loop_uux_ddxepem`,
`loop_gg_zgg` and `loop_gg_epemmpmm`, the last two loop-induced), see
[Examples](../../examples/README.md#one-loop-examples) and
[Build a wheel from a checkout and run the loop examples](installation.md#build-a-wheel-from-a-checkout-and-run-the-loop-examples).

In 1.0.2, storing a one-loop request whose Born couplings, as its scaleless
companion evaluates them, read a model helper function (e.g. `u u~ > d d~ g`
with QCD corrections and explicit coupling-order caps that keep both Born
orders, QCD^3 and QCD QED^2) failed with `Could not create evaluator: function
value_N(..) is not in a parameter map`, so nothing was stored and no value was
wrong; such requests now store.

**Built-in SM: a Higgs propagator attached to a top-quark line.** Earlier
versions of the built-in Standard Model had the top Yukawa vertex in one
orientation only, so the tree recursion could not build every diagram with a
Higgs propagator attached to a top-quark line. The top is the only fermion
of the built-in SM with a Yukawa coupling; its line ends on external tops or,
through W vertices, on b quarks.

- **Affected processes:** every built-in SM process with a tree diagram in
  which an internal Higgs is attached to a top line. The Higgs's other end
  can be a second top line (`t t~ > t t~`, `t t > t t`, `t t~ > t t~ h`), or
  a W, Z or Higgs vertex on a process with a single top line
  (`t w- > t w- d d~`, `t a > t z u u~`).
- **Which values were wrong:** whether such a diagram was dropped depended on
  the order in which the recursion built it. Some of these processes were
  right (`t t~ > h h`, `t t~ > z z`). The others were wrong in either
  direction, without a message:
  - `t t~ > t t~` at `{ QCD = 0, QED = 2 }` gave 0.633 instead of 1.563;
  - `t w- > t w- d d~` was 48 % too large at a test point;
  - `t a > t z u u~` was too small.
- **Fix:** the built-in SM now has the fermion pair fusing into the Higgs and
  the Higgs absorbed in either orientation, and equals the UFO `sm` and
  MadGraph for these processes. Processes with no internal Higgs on a top
  line are unchanged.

Artifacts of affected processes generated by earlier releases or
development builds keep their old values: regenerate them. When in doubt,
regenerate every built-in SM artifact with a top-quark line. The Python
`Runtime.load` warns that such an artifact "was generated with another
built-in SM source" and still loads it with its old values, for
reproducibility. The C, C++, Fortran and Rust clients print no warning: they
load and evaluate it silently with the old values (see
[Native APIs](native-apis.md#built-in-sm-artifacts-from-earlier-releases)).

**Built-in SM + HEFT: an internal Higgs at the effective gluon vertex.**

- Gluons fusing into an internal Higgs that decays into colour singlets
  (`g g > z z`, `g g > h h`) were refused by the compiled and eager modes;
  they are now served in every mode and equal MadGraph's `heft`.
- A colour singlet exchanged between a pure-gluon part of a tree and a quark
  line (`g g > t t~`, `t g > t g g` with `HIG >= 1`, and the default orders
  of `t g > t g g`, which admitted two effective vertices) was served with
  wrong values and no message:
  - the compiled and eager modes projected its colour, an open line times a
    closed gluon trace, onto the open-line flows (the squared Higgs term of
    `g g > t t~` was 14/9 of MadGraph's);
  - the recurrence and on-the-fly modes dropped it.

  Every mode now refuses it with a typed error; `HIG = 0` serves these
  processes without the effective vertex. The same holds for a Higgs between
  two groups of gluons (`g g > g g` at `HIG = 2`).
- A Higgs that the effective vertex joins, through gluons of quark lines, to
  another quark line (`d d~ > t t~ g`; with no external gluon,
  `u u~ > d d~ t t~`, where the compiled value was half MadGraph's) was
  dropped by the compiled and eager modes, giving a wrong value without a
  message. These modes now refuse
  it, and the recurrence and on-the-fly modes serve it, equal to MadGraph.
- The default (minimal) coupling-order policy now works within each order's
  UFO `expansion_order`, as MadGraph does: an amplitude carries at most that
  power of the order unless the request names a higher limit. Of the shipped
  and packaged models only the HEFT order `HIG` (expansion order 1) declares
  one; a default `t g > t g g` on `built-in-sm-heft` is now its QCD tree.
- Artifacts of such requests generated by earlier releases keep their wrong
  values: regenerate them. The model itself is unchanged, so neither the
  Python reader nor the native clients warn about them.

**Command-line output: tables only, progress everywhere, Ctrl-C safe.**
Every command prints its tables and short status lines only (the table
titles keep what changes the numbers' meaning: leading colour, finite only,
UV or IR poles); `--fields-description-help` adds a plain-words description
of every table and column. The CLI shows no logger-format lines by default (`--log-level`
defaults to `warning`; a few short notice lines say what is being done) and
`--progress log` writes plain lines. `check`, `evaluate`, `profile` and
`self-test` show their progress like `generate`, and Ctrl-C ends any command
cleanly (exit code 130): `profile`, `evaluate` and `check` report what was
measured, evaluated or checked so far, an interrupted `generate` writes
nothing. Value tables print
an explicit `+` on positive values. `profile`: one-line backend names (`*`:
the default), a lean runtime table that times best-effort points as served,
the distribution of failure causes under the tables (`failure_causes` in
`--json`), and `--stability` over 1000 points by default on `--n_core`
worker processes (default 10; `benchmark.n_core`) with an estimated time to
completion.

Version `1.0.3` uses the Python dependencies of 1.0.2 (Symbolica 3.0.3
from PyPI, SymJIT 2.28.3, ufo-model-loader 1.0.1). The native code builds
Symbolica from symbolica-dev/symbolica's `community` branch (`d0424f9e`),
NinjaRS and oneloopmaster at newer commits of their `main` branches (their
sources pinned on that revision), and TIRust
([huashengshao/TIRust](https://github.com/huashengshao/TIRust)) at a pinned
commit, linked by the default cargo feature `tir`; see
[dependencies/README.md](../../dependencies/README.md). With Python Symbolica
3.0.3 from PyPI, results of the Python API can depend on what else was
generated in the same Python process (about 1e-30 relative normally, amplified
at nearly degenerate 2 -> 2 kinematics): generate each artifact in a fresh
process where that matters. The Community build of the pinned `community` revision (`d0424f9e`) shows the
same in double-double and arbitrary precision (about 5e-29 relative). Saved Symbolica evaluator states are stored in the envelope every Python
Symbolica since 3.0.3 reads. Process artifacts load only in the version that wrote them:
artifacts written by 1.0.2 are refused by 1.0.3, regenerate them. The model
compiler version is unchanged (17), so prepared `.pyamplicol-model` bundles
written by 1.0.2 still load.

Version `1.0.2` was not published on PyPI and has no tag; its content is part
of 1.0.3.

## 1.0.2 release

Version `1.0.2` adds one-loop virtual matrix elements on the v2 engine:
QCD corrections on MG5_aMC's `loop_sm`, and QCD, electroweak and joint
corrections on the shipped `loop_qcd_qed_sm` and `loop_qcd_qed_sm_Gmu`
models, with finite parts and poles per squared coupling order, in binary64,
double-double or arbitrary precision. They load through `Runtime.load` and the
C, C++, Fortran and Rust SDKs. See
[One-loop QCD on loop_sm](loop-sm-and-madloop.md),
[One-loop QCD+QED](electroweak-and-madloop.md) and
[virtual artifacts](runtime-and-selectors.md#virtual-one-loop-artifacts).

The built-in Standard Model now equals the UFO `sm` (`no_masses`
restriction) at tree level. Processes without coloured legs (`e+ e- > a a`,
`e+ e- > mu+ mu-`) were too small by 1/(8 π α)² ≈ 27.8; massive vector and
Higgs initial states are averaged over their own spin states; the recurrence
mode counted every W W photon and W W Z vertex twice; and the lepton and
neutrino currents, the electroweak exchange between quark lines and the
H H V V and four-Higgs contacts were incomplete. Artifacts written by 1.0.1
are refused by 1.0.2, whose runtime admits only artifacts of its own package
version: regenerate them. A 1.0.2 artifact generated with a built-in SM
source from before these fixes (a development build) loads with a warning
and keeps the old values. See
[Built-in Standard Model](models-and-processes.md#built-in-standard-model).

Four-quark HEFT trees on `built-in-sm-heft` and on UFO HEFT models were too
large, because the H g g vertex did not subtract the U(1) part of its
internal gluons: 9/8 times for `q q~ > H q' q'~` and its crossings, other
factors with identical quark flavours or more gluons (1.36 for
`u u~ > H d d~ g`); fixed in
[#40](https://github.com/MadGraphTeam/pyamplicol/pull/40).

Processes with one initial particle (1 -> n decays, `t > b w+`) are served
at tree level on UFO models and on the built-in SM (`z > e+ e-`), and at one
loop on the loop models; decay chains and loop-induced decays are refused.
Mechanical hard-coded limits were lifted: the loop rank is the reduction
backend's; the colour-FFT degree, grouping factors and flavour mappings,
charges (now exact rationals) and full-colour N_c powers are uncapped; and
the native C++ compile has no default timeout. The remaining tuning bounds are
settings
(`color.adjoint_dense_max_gluons`, `color.fused_selector_max_sectors`,
`generation.validation.max_resolved_components`).

Version `1.0.2` uses Python Symbolica 3.0.3 from PyPI (or a Symbolica
Community build of symbolica-dev's `community` branch with
symbolica-dev/symbolica#163), and the native code builds Symbolica from that
branch and pull request at a pinned revision. It also uses SymJIT 2.28.3,
ufo-model-loader 1.0.1, and NinjaRS and oneloopmaster from their `main`
branches for the one-loop reduction. Tree and one-loop process artifacts
load only in the version that wrote them, and the model compiler version is
now 17: regenerate artifacts, compiled models and prepared
`.pyamplicol-model` bundles written by an earlier version.

## 1.0.1 release

Version `1.0.1` adds process grouping for multiprocess outputs. Subprocesses
with equal matrix elements are recorded in a new `process-groups.json`
artifact payload, with their leg permutation, rational factor, and charge
conjugation. `--flavor-blind` generates one representative per flavour
class, optionally including charge conjugation, and every other flavour
remains selectable from Python, the CLI, and the native SDKs, which route it
to its representative. `--analyze-process-groups numerical` and
`pyamplicol group-processes` find further relations numerically.
`pyamplicol inspect` and the generation summary display the groups, and UMAMI
exports flavour-blind members through their representative. UFO multiparticle
expansion now enumerates multisets and drops candidates that violate a charge
conserved by every vertex, which renumbers the process IDs of compiled-model
multiprocess requests. Artifacts written by 1.0.1 declare the new payload and
require a 1.0.1 runtime. See [Process Grouping](process-grouping.md).

## 1.0.0 release

Version `1.0.0` preserves exact model constants, colour weights, and
normalization factors through higher-precision evaluation. It also corrects
native evaluation and retains the exact next-to-leading-colour generation
shortcut. The release keeps the same supported platforms and Python versions.
Tensor algebra and prepared models have been updated for the published
Symbolica 3.0.0 API, including exact complex constants in the SymJIT bridge.
Equivalent exact and floating-point coefficients are again recognized when
selecting optimized recurrence kernels, including in the bundled SM and HEFT models.
Batched recurrence evaluations now fill the already allocated SIMD-aligned
workspace, avoiding unnecessarily small batches at higher multiplicities.
Completed on-the-fly caches can be saved and restored through Python and every
native SDK, without reconstructing the retained currents. See
[saving an OTF warm cache](runtime-and-selectors.md#saving-an-otf-warm-cache).
Symbolica's package license removes the need for a personal key for pyAmpliCol
use; personal-license and restricted-mode fallbacks remain available.
Compiled JIT O2 generation selects compressed code by default.

## 0.2.0 release

Version `0.2.0` adds exact symmetric-group FFT full-colour contraction,
helicity-parametric recurrence and on-the-fly scheduling, built-in SM+HEFT and
trusted UFO HEFT support, and the resumable fixed-helicity/helicity-sum FFT
profiling workflow with its final comparison reports.
See the runnable [scalar HEFT workflow](models-and-processes.md#built-in-scalar-heft-model)
and the [FullColor FFT profiling guide](fullcolor-fft-profiling.md).

## 0.1.4 release

Version `0.1.4` adds on-the-fly generation and its explicit one-point
`warm_up(...)` lifecycle, while retaining compiled, eager, and recurrence
generation. It also ships progress-aware warm-up entry points for the Python,
C, C++, Fortran, and Rust APIs and the packaged `p p > Z j j` OTF example.

## Install a release

```console
python -m venv .venv
. .venv/bin/activate
python -m pip install pyamplicol
```

Binary wheels include the Rust runtime and native SDK. Wheel users do not need
a Rust compiler. A C, C++, Fortran, or Rust compiler is required only when
compiling a consumer in that language against the included SDK.

Verify the environment with:

```console
pyamplicol doctor
pyamplicol self-test
```

Then run the primary example from an editable copy:

```console
pyamplicol examples copy ./pyamplicol-examples --force
cd pyamplicol-examples
pyamplicol generate_pp_zjj_from_ufo_sm.toml
pyamplicol evaluate_total.toml
```

See [Installation](installation.md) and [Quick Start](quick-start.md).

## What a release contains

The release set consists of:

- one source distribution;
- supported-platform `cp311-abi3` wheels;
- the Python extension and target-specific static Rusticol SDK in each wheel;
- packaged model resources, examples, profiling-campaign templates, and user
  documentation required by installed workflows.

Source installation may work elsewhere, but a platform is not advertised as
supported until its installed Python and native API matrix has passed.

Rendered performance reports are not PyPI wheel payloads or release-CI
benchmarks; the one-loop benchmark report lives under
[docs/performance_reports/loop](../performance_reports/loop/README.md).

## How artifacts are validated and published

The authoritative release workflow builds and tests the source distribution
and platform wheels. Deployment tests install each wheel into a clean
environment and exercise the installed Python runtime and native SDK consumers.

Publication then selects that already validated artifact run and uploads its
exact files through PyPI Trusted Publishing. Upload does not rebuild packages.
This keeps the tested and published bytes identical without adding a second
release build.

GitHub workflow history is available under
[Actions](https://github.com/MadGraphTeam/pyamplicol/actions), and tagged source
snapshots under [Releases](https://github.com/MadGraphTeam/pyamplicol/releases).

## Compatibility promises

- The public Python API is versioned and documented in the repository's API
  contract.
- The native public boundary is C ABI version 1; C++, Fortran, and safe Rust
  wrappers sit on that ABI.
- Run cards use schema version 1 and reject unknown fields.
- Current process artifacts use schema version 3 and the current runtime
  identity/ABI contract.
- Internal generated-artifact formats are not automatically migrated. An old
  artifact that lacks the current contract fails with regeneration guidance.

Regenerate process artifacts with the installed version when upgrading across
an artifact-contract change. Do not edit a manifest or executable payload by
hand.

## Supported and intentionally separate components

- pyAmpliCol has no LHAPDF dependency.
- Symbolica is required for model compilation, generation, and Python exact
  paths; the default compatible f64 JIT runtime executes through SymJIT without
  importing Symbolica.
- Original AmpliCol is optional campaign/developer comparison infrastructure,
  not an installed-package runtime dependency.
- Source contributor builds and release builds have separate dependency
  boundaries. Contributor candidate wheels are deliberately non-publishable.

See [Symbolica and Licensing](symbolica-and-licensing.md),
[Profiling Campaigns](profiling-campaigns.md), and
[Artifacts and Portability](artifacts-and-portability.md).

## Report a problem

Use [GitHub Issues](https://github.com/MadGraphTeam/pyamplicol/issues) for a
reproducible bug, compatibility failure, or documentation gap. Search existing
issues first.

Include the smallest information that distinguishes the failure:

1. exact pyAmpliCol version and installation method;
2. operating system, architecture, and Python version;
3. the command or short Python snippet;
4. the complete error message;
5. whether the model is built-in, JSON, compiled, prepared, or trusted UFO;
6. execution mode, backend, color accuracy, and process expression;
7. output from `pyamplicol doctor` when installation or SDK discovery is
   involved.

Useful read-only captures are:

```console
pyamplicol doctor --json > doctor.json
pyamplicol inspect ARTIFACT --json > inspect.json
pyamplicol config resolve RUN_CARD.toml --json > config.json
```

Review these files before attaching them. Do not publish private model data,
license keys, cluster paths, credentials, or an artifact you are not permitted
to redistribute.

For a generated native-driver failure, also include:

```console
rusticol-config --version
rusticol-config --target
rusticol-config --json
```

For a numerical report, provide the smallest kinematic point and parameter card
that reproduces it, the selected stable ID or process expression, precision,
and selectors. State whether the optimized total and explicit resolved sum
disagree.

## Triage checklist

Before filing, try the focused check matching the symptom:

| Symptom | First check |
| --- | --- |
| CLI/import failure | `pyamplicol doctor` |
| Installation/runtime smoke | `pyamplicol self-test` |
| Native headers or linker flags missing | Activate the environment, then `rusticol-config --json` |
| Artifact target/ABI rejection | `pyamplicol inspect ARTIFACT` and regenerate with the current release |
| Process expression not found | Inspect stable IDs; see [Process Selection and Permutations](process-selection-and-permutations.md) |
| Selector rejected | Inspect the selected process's helicity/color capabilities |
| Raw UFO/JSON fails in recurrence/eager/OTF | Prepare a compatible `.pyamplicol-model` bundle, or choose compiled mode |
| High-precision Python failure | Confirm Symbolica availability and license; f64 is `--precision 16` |
| Profiling result is surprising | Keep process, layout, selectors, batch, and precision fixed; see [Profiling and Benchmarking](profiling-and-benchmarking.md) |

More symptom-specific help is in [Troubleshooting](troubleshooting.md).

## Feature requests

A useful feature request explains:

- the physics or deployment workflow;
- why existing model, generation, runtime, or selector APIs are insufficient;
- the smallest representative process/model;
- expected public behavior, including error behavior;
- platform or performance constraints.

Avoid attaching a complete private project when a small public model/process
can demonstrate the need.

## Contributing a fix

Contributor setup is documented in [Installation](installation.md).
The repository policy favors focused tests for a demonstrated failure plus one
authoritative CI path. Changes should not add redundant manifests, repeated
hashing, dependency revalidation, or unrelated release ceremony.

Public API changes require corresponding documentation and typing coverage.
Runtime or artifact changes require proportionate native tests; documentation-
only changes do not justify rebuilding the platform release matrix.

## Security and artifact trust

Process artifacts are executable inputs. JIT applications are lowered to
native code at load time, and C++/ASM artifacts may contain native libraries.
Manifest validation establishes internal consistency and path confinement, not
publisher identity. Generate artifacts yourself or obtain them through a
trusted channel.

Do not post a suspected security vulnerability publicly before maintainers can
assess it. Use the repository's available private security-reporting channel if
enabled; otherwise contact the maintainers through the organization channels
without including exploit details in a public issue.

## Links

- [PyPI](https://pypi.org/project/pyamplicol/)
- [GitHub releases](https://github.com/MadGraphTeam/pyamplicol/releases)
- [Issue tracker](https://github.com/MadGraphTeam/pyamplicol/issues)
- [License](https://github.com/MadGraphTeam/pyamplicol/blob/main/LICENSE)
- [Third-party notices](https://github.com/MadGraphTeam/pyamplicol/blob/main/THIRD_PARTY_NOTICES.md)
