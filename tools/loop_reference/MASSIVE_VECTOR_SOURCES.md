# Stable W+ source controls

`wg_sources.json` records complete QCD Born–loop interference for
`u d~ -> W+ g` and `d W+ -> u g`. Values are Born followed by finite, single-pole
and double-pole coefficients, with physical couplings and the original incoming
spin/colour average. The common normalization is
`Cepsilon=(4*pi)^epsilon/Gamma(1-epsilon)`.

The supplied Recola 2.3.0 model/Collier build and MadLoop 3.7.0 `loop_sm-no_b_mass`
use Feynman gauge, five-flavour alpha_s renormalization, alpha(0), `mu_r=1000`,
`aS=0.118`, `aEWM1=132.50698`, `Gf=0.0000116639`, `MZ=91.188`, `MT=173`, massless
bottom and zero relevant widths. The W mass is the common derived real mass,
approximately `80.41900001766318`. Scalar inputs remain exact decimal data in
pyAmpliCol; the external provider comparison is binary64.

## Independent provider calculation

`recola_wg_polarizations.f90` checks inclusive and `[-]`, `[0]`, `[+]` processes.
The three fixed states reconstruct the inclusive result. Recola's public
spin-projection implementation calls massless `definewp` and sums only two states;
it is not used as a massive-vector oracle.

`recola_wg_coherent.f90` instead uses the supplied provider's own `definewp` at the
actual mass for all three states, coherent tree/loop matrix columns, spectator
helicity catalogue, colour matrix and external averaging factor. The contraction
follows `amplitude_rcl.f90:2607`; its outgoing helicity ordering is checked against
the provider's public mapping in `process_computation_rcl.f90`. The source basis,
complex mixture and its `(2+3i)` multiple are evaluated by
`recola_wg_sources_driver.f90`. This reference helper uses pinned provider internals
and supports the single selected coupling order exercised here. It is not a
production algebra or reduction implementation.

The supplied coherent getters use the same stored index for IR1 and IR2. Four
calls with `(delta_IR1,delta_IR2)=(0,0),(1,0),(0,1),(2,3)` therefore extract and
independently check the two actual poles. The finite coefficient is converted by
adding `pi^2/6 * double_pole`; poles are unchanged. Recola's fixed incoming-state
result removes its factor of three; coherent projections retain the original
unpolarized average, so the fixed-state comparison divides by three. There is no
implicit source conjugation or guessed relative phase.

`madloop_wg_driver.f90` uses `SET_LEG_POLARIZATION`, including `0`, and actual
`sloopmatrix_thres` outputs. Generate processes in this order with
`QCD=1 QED=1 [virt=QCD]`: outgoing W+, incoming W+, outgoing W−. The latter supplies
a retained provider reference only; pyAmpliCol W− validation remains a follow-up.
Set the matched parameters above. MadLoop's default six-digit parameter-card
writer rounds `132.50698`; twelve fractional digits retain the selected values
within its Fortran `CHARACTER*20` value parser. Driver path arguments use
`CHARACTER(512)`, matching the generated interface. `madloop_wg_sources.json`
retains values, statuses, accuracy estimates and Recola comparison results.

All builds, generated provider exports, raw logs and experimental outputs belong
under `workspace`. No provider sources were modified. These files record physics
controls, not generation or runtime benchmark measurements.

## pyAmpliCol controls

`tests/unit/test_loop_massive_vector_sources.py` loads retained actual source
artifacts using `PYAMPLICOL_MASSIVE_VECTOR_FIXTURES`. It exercises charged source
identity/state rejection; three-state and joint completeness in double,
DoubleFloat and AP70; both directed terms; exact literal input and parameter
ownership; native empty/tail/ID transport; public physical-reference agreement;
AP60/AP80 subset rescue and `clear`. `massive_vector_sdk.rs` uses the unchanged
standalone source ABI for an actual longitudinal state and verifies owned results.

No independent 70-digit accuracy or arbitrary nontransverse Recola certification
is claimed. Charge-conjugate W−, neutral axial/chiral cases, EW corrections,
complex external masses and massive-vector LC/NLC composition are separate gates.
