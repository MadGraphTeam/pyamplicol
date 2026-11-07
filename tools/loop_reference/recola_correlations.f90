! SPDX-License-Identifier: 0BSD
! Generic Recola2 colour- and spin-correlation driver: an independent oracle
! for correlated Borns and Born-virtual interferences (no timing). It reads
! the scheme and process commands of recola_driver.f90 (mass, alpha0, alphaz,
! gfermi, alphas, onshell, complex_mass, cache, legs, born_gs, loop_gs,
! pow_lo, pow_nlo, process, generate), then
!   points <n>    followed by n lines "mu E1 px1 py1 pz1 ... En pxn pyn pzn"
!   requests <m>  followed by m lines "kind i j point vr0 vi0 vr1 vi1 vr2 vi2 vr3 vi3"
! with kind
!   born  plain squared amplitude (compute_process_rcl; i, j, v unused)
!   cc    compute_colour_correlation_rcl(i, j)            (v unused)
!   sc    compute_spin_correlation_rcl(leg i, vector v)    (j unused)
!   scc   compute_spin_colour_correlation_rcl(spin leg i, colour partner j, v)
! and prints per request "CORR k ok LO F IR1 IR2 RES": ok = Recola's momenta
! check, LO the correlated Born, F the NLO interference at Delta_IR = (0,0)
! (Recola's normalisation), IR1/IR2 its Delta_IR coefficients from
! (1,0)/(0,1) and RES the linearity residual at (2,3). For born, F/IR1/IR2 are
! the public NLO/NLO-IR1/NLO-IR2 getters and RES = 0.
! With the command loop_induced (a process without a Born: no born_gs/pow_lo)
! the correlations are Recola's loop-induced ones (order 'NLO' without a LO:
! |A1|^2 correlated), LO = 0; switchoff3 a b c switches a coupling off as in
! recola_driver.f90.
program recola_correlations
  use recola
  implicit none
  integer, parameter :: dp = kind(1d0)
  character(len=8192) :: line, keyword, process
  character(len=8) :: kind_
  integer :: legs = -1, born_gs = -1, loop_gs = -1, pow_lo = -1, pow_nlo = -1
  integer :: count, nreq, i, k, ios, nf, i1, i2, ip
  real(dp) :: mass, width, value, mu, vr(0:3), vi(0:3), out(5)
  real(dp), allocatable :: p(:,:,:), scales(:)
  real(dp) :: stored_alpha_s = -1d0
  integer :: stored_nf = -1
  logical :: ok, loop_induced = .false.
  complex(dp) :: v(0:3)
  process = ''
  do
    read(*, '(A)', iostat=ios) line
    if (ios /= 0) exit
    line = adjustl(line)
    if (len_trim(line) == 0) cycle
    read(line, *) keyword
    select case (trim(keyword))
    case ('mass')
      call mass_command(line)
    case ('alpha0')
      read(line, *) keyword, value
      call use_alpha0_scheme_rcl(value)
    case ('alphaz')
      read(line, *) keyword, value
      call use_alphaZ_scheme_rcl(value)
    case ('gfermi')
      read(line, *) keyword, value
      call use_gfermi_scheme_rcl(g=value)
    case ('alphas')
      read(line, *) keyword, value, mu, nf
      stored_alpha_s = value
      stored_nf = nf
      call set_alphas_rcl(value, mu, nf)
      call set_mu_uv_rcl(mu)
      call set_mu_ir_rcl(mu)
    case ('onshell')
      call set_on_shell_scheme_rcl()
    case ('complex_mass')
      call set_complex_mass_scheme_rcl()
    case ('cache')
      read(line, *) keyword, k
      call set_cache_mode_rcl(k)
    case ('loop_induced')
      loop_induced = .true.
    case ('switchoff3')
      call switchoff_command(line)
    case ('legs')
      read(line, *) keyword, legs
    case ('born_gs')
      read(line, *) keyword, born_gs
    case ('loop_gs')
      read(line, *) keyword, loop_gs
    case ('pow_lo')
      read(line, *) keyword, pow_lo
    case ('pow_nlo')
      read(line, *) keyword, pow_nlo
    case ('process')
      process = adjustl(line(len_trim('process') + 1:))
    case ('generate')
      if (stored_nf < 0 .or. legs < 3 .or. loop_gs < 0 .or. pow_nlo < 0 .or. len_trim(process) == 0 &
          .or. (.not. loop_induced .and. (born_gs < 0 .or. pow_lo < 0))) &
        stop 'recola correlations: incomplete process definition'
      call set_delta_uv_rcl(0d0)
      call set_delta_ir_rcl(0d0, 0d0)
      call set_dynamic_settings_rcl(1)
      call set_compute_ir_poles_rcl(1)
      call define_process_rcl(1, trim(process), 'NLO')
      if (.not. loop_induced) then
        call unselect_all_gs_powers_BornAmpl_rcl(1)
        call select_gs_power_BornAmpl_rcl(1, born_gs)
      end if
      call unselect_all_gs_powers_LoopAmpl_rcl(1)
      call select_gs_power_LoopAmpl_rcl(1, loop_gs)
      call generate_processes_rcl()
    case ('points')
      read(line, *) keyword, count
      allocate(p(0:3, legs, count), scales(count))
      do i = 1, count
        read(*, *) scales(i), p(:, :, i)
      end do
    case ('requests')
      read(line, *) keyword, nreq
      do k = 1, nreq
        read(*, *) kind_, i1, i2, ip, (vr(i), vi(i), i = 0, 3)
        v = cmplx(vr, vi, kind=dp)
        call request(trim(kind_), i1, i2, ip, v, ok, out)
        write(*, '(A,I8,L2,5ES26.17E3)') 'CORR ', k, ok, out
      end do
    case default
      write(*, *) 'recola correlations: unknown command ', trim(keyword)
      stop 1
    end select
  end do
  call reset_recola_rcl()

contains

  subroutine request(what, i1, i2, ip, v, ok, out)
    character(len=*), intent(in) :: what
    integer, intent(in) :: i1, i2, ip
    complex(dp), intent(in) :: v(0:3)
    logical, intent(out) :: ok
    real(dp), intent(out) :: out(5)
    real(dp) :: a(0:3)
    real(dp), parameter :: d1(0:3) = [0d0, 1d0, 0d0, 2d0], d2(0:3) = [0d0, 0d0, 1d0, 3d0]
    integer :: n
    call set_alphas_rcl(stored_alpha_s, scales(ip), stored_nf)
    call set_mu_uv_rcl(scales(ip))
    call set_mu_ir_rcl(scales(ip))
    call set_delta_ir_rcl(0d0, 0d0)
    out = 0d0
    if (what == 'born') then
      call compute_process_rcl(1, p(:, :, ip), 'NLO', momenta_check=ok)
      if (.not. loop_induced) call get_squared_amplitude_rcl(1, pow_lo, 'LO', out(1))
      call get_squared_amplitude_rcl(1, pow_nlo, 'NLO', out(2))
      call get_squared_amplitude_rcl(1, pow_nlo, 'NLO-IR1', out(3))
      call get_squared_amplitude_rcl(1, pow_nlo, 'NLO-IR2', out(4))
      return
    end if
    if (.not. loop_induced) call correlation(what, i1, i2, ip, v, 'LO', ok, out(1))
    do n = 0, 3
      call set_delta_ir_rcl(d1(n), d2(n))
      call correlation(what, i1, i2, ip, v, 'NLO', ok, a(n))
    end do
    call set_delta_ir_rcl(0d0, 0d0)
    out(2) = a(0)
    out(3) = a(1) - a(0)
    out(4) = a(2) - a(0)
    out(5) = a(3) - (a(0) + 2d0 * out(3) + 3d0 * out(4))
  end subroutine

  subroutine correlation(what, i1, i2, ip, v, order, ok, value)
    character(len=*), intent(in) :: what, order
    integer, intent(in) :: i1, i2, ip
    complex(dp), intent(in) :: v(0:3)
    logical, intent(out) :: ok
    real(dp), intent(out) :: value
    select case (what)
    case ('cc')
      call compute_colour_correlation_rcl(1, p(:, :, ip), i1, i2, order, value, ok)
    case ('sc')
      call compute_spin_correlation_rcl(1, p(:, :, ip), i1, v, order, value, ok)
    case ('scc')
      call compute_spin_colour_correlation_rcl(1, p(:, :, ip), i1, i2, v, order, value, ok)
    case default
      write(*, *) 'recola correlations: unknown request ', what
      stop 1
    end select
  end subroutine

  subroutine switchoff_command(text)
    character(len=*), intent(in) :: text
    character(len=32) :: a, b, c
    read(text, *) keyword, a, b, c
    call switchoff_coupling3_rcl(trim(a), trim(b), trim(c))
  end subroutine

  subroutine mass_command(text)
    character(len=*), intent(in) :: text
    character(len=32) :: name
    read(text, *) keyword, name, mass, width
    select case (trim(name))
    case ('W'); call set_pole_mass_w_rcl(mass, width)
    case ('Z'); call set_pole_mass_z_rcl(mass, width)
    case ('H'); call set_pole_mass_h_rcl(mass, width)
    case ('top'); call set_pole_mass_top_rcl(mass, width)
    case ('bottom'); call set_pole_mass_bottom_rcl(mass, width)
    case ('charm'); call set_pole_mass_charm_rcl(mass, width)
    case ('tau'); call set_pole_mass_tau_rcl(mass, width)
    case ('muon'); call set_pole_mass_muon_rcl(mass, width)
    case ('strange'); call set_pole_mass_strange_rcl(mass)
    case ('up'); call set_pole_mass_up_rcl(mass)
    case ('down'); call set_pole_mass_down_rcl(mass)
    case ('electron'); call set_pole_mass_electron_rcl(mass)
    case default
      write(*, *) 'recola correlations: unknown particle ', trim(name)
      stop 1
    end select
    if (width /= 0d0 .and. (trim(name) == 'strange' .or. trim(name) == 'up' .or. &
        trim(name) == 'down' .or. trim(name) == 'electron')) stop 'recola correlations: width not settable'
  end subroutine
end program
