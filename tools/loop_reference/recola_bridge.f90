! Use the public Fortran API: Recola 2.3.0's C++ header has unrelated missing
! declarations, and the reference library itself need not be patched.
subroutine reference_recola_init(alpha_s, mu, mt, mb) bind(C)
  use iso_c_binding
  use recola
  implicit none
  real(c_double), value :: alpha_s, mu, mt, mb
  call set_pole_mass_top_rcl(mt, 0d0)
  call set_pole_mass_bottom_rcl(mb, 0d0)
  call set_alphas_rcl(alpha_s, mu, 5)
  call set_mu_uv_rcl(mu)
  call set_mu_ir_rcl(mu)
  call set_delta_uv_rcl(0d0)
  call set_delta_ir_rcl(0d0, 0d0)
  call set_dynamic_settings_rcl(1)
  call set_compute_ir_poles_rcl(1)
  call define_process_rcl(1, 'u u~ -> d d~', 'NLO')
  call unselect_all_gs_powers_BornAmpl_rcl(1)
  call select_gs_power_BornAmpl_rcl(1, 2)
  call unselect_all_gs_powers_LoopAmpl_rcl(1)
  call select_gs_power_LoopAmpl_rcl(1, 4)
  call generate_processes_rcl()
end subroutine

subroutine reference_recola_evaluate(p, answer) bind(C)
  use iso_c_binding
  use recola
  implicit none
  real(c_double), intent(in) :: p(0:3,4)
  real(c_double), intent(out) :: answer(4)
  call compute_process_rcl(1, p, 'NLO')
  call get_squared_amplitude_rcl(1, 2, 'LO', answer(1))
  call get_squared_amplitude_rcl(1, 3, 'NLO', answer(2))
  call get_squared_amplitude_rcl(1, 3, 'NLO-IR1', answer(3))
  call get_squared_amplitude_rcl(1, 3, 'NLO-IR2', answer(4))
end subroutine

subroutine reference_recola_finish() bind(C)
  use recola
  implicit none
  call reset_recola_rcl()
end subroutine
