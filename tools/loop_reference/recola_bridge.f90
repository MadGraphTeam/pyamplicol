! SPDX-License-Identifier: 0BSD
! Use the public Fortran API: Recola 2.3.0's C++ header has unrelated missing
! declarations, and the reference library itself need not be patched.
#ifndef LOOP_REFERENCE_LEGS
#define LOOP_REFERENCE_LEGS 4
#endif
#ifndef LOOP_REFERENCE_QCD_BORN_POWER
#define LOOP_REFERENCE_QCD_BORN_POWER 2
#endif
subroutine reference_recola_init(alpha_s, mu, mt, mb, inverse_alpha_em) bind(C)
  use iso_c_binding
  use recola
  implicit none
  real(c_double), value :: alpha_s, mu, mt, mb, inverse_alpha_em
  call set_pole_mass_top_rcl(mt, 0d0)
  call set_pole_mass_bottom_rcl(mb, 0d0)
  call set_alphas_rcl(alpha_s, mu, 5)
  call set_mu_uv_rcl(mu)
  call set_mu_ir_rcl(mu)
  call set_delta_uv_rcl(0d0)
  call set_delta_ir_rcl(0d0, 0d0)
  call set_dynamic_settings_rcl(1)
  call set_compute_ir_poles_rcl(1)
#ifdef LOOP_REFERENCE_DRELL_YAN
  call use_alpha0_scheme_rcl(1d0 / inverse_alpha_em)
  call set_pole_mass_electron_rcl(0d0)
  ! The photon-only control excludes Z exchange. Removing this vertex before
  ! generation removes every Z attachment to the external lepton current.
  call switchoff_coupling3_rcl('Z', 'e-', 'e+')
  call define_process_rcl(1, 'u u~ -> e- e+', 'NLO')
#elif defined(LOOP_REFERENCE_QUARK_THREE_GLUON)
  call define_process_rcl(1, 'u u~ -> g g g', 'NLO')
#elif defined(LOOP_REFERENCE_FIVE_GLUON)
  call define_process_rcl(1, 'g g -> g g g', 'NLO')
#elif defined(LOOP_REFERENCE_TOP_PAIR)
  call define_process_rcl(1, 'u u~ -> t t~', 'NLO')
#elif defined(LOOP_REFERENCE_GLUON_SCATTERING)
  call define_process_rcl(1, 'g g -> g g', 'NLO')
#elif defined(LOOP_REFERENCE_QUARK_GLUON)
  call define_process_rcl(1, 'u u~ -> g g', 'NLO')
#else
  call define_process_rcl(1, 'u u~ -> d d~', 'NLO')
#endif
  call unselect_all_gs_powers_BornAmpl_rcl(1)
  call select_gs_power_BornAmpl_rcl(1, LOOP_REFERENCE_QCD_BORN_POWER)
  call unselect_all_gs_powers_LoopAmpl_rcl(1)
  call select_gs_power_LoopAmpl_rcl(1, LOOP_REFERENCE_QCD_BORN_POWER + 2)
  call generate_processes_rcl()
end subroutine

subroutine reference_recola_evaluate(p, answer) bind(C)
  use iso_c_binding
  use recola
  implicit none
  real(c_double), intent(in) :: p(0:3,LOOP_REFERENCE_LEGS)
  real(c_double), intent(out) :: answer(4)
  call compute_process_rcl(1, p, 'NLO')
  call get_squared_amplitude_rcl(1, LOOP_REFERENCE_QCD_BORN_POWER, 'LO', answer(1))
  call get_squared_amplitude_rcl(1, LOOP_REFERENCE_QCD_BORN_POWER + 1, 'NLO', answer(2))
  call get_squared_amplitude_rcl(1, LOOP_REFERENCE_QCD_BORN_POWER + 1, 'NLO-IR1', answer(3))
  call get_squared_amplitude_rcl(1, LOOP_REFERENCE_QCD_BORN_POWER + 1, 'NLO-IR2', answer(4))
end subroutine

subroutine reference_recola_finish() bind(C)
  use recola
  implicit none
  call reset_recola_rcl()
end subroutine
