! SPDX-License-Identifier: 0BSD
! Generic Recola2 reference driver. Reads a small command stream on stdin:
!   mass <W|Z|H|top|bottom|charm|strange|up|down|tau|muon|electron> <m> <width>
!   alpha0 <alpha> | alphaz <alpha> | gfermi <G_F>      (EW input/renormalization scheme)
!   alphas <alpha_s> <mu> <nf>                           (alpha_s at mu, nf light flavours)
!   cache <mode>                                         (set_cache_mode_rcl)
!   onshell | complex_mass                               (mass renormalization scheme)
!   legs <n>    born_gs <n>    loop_gs <n>    pow_lo <n>    pow_nlo <n>
!   process <Recola process string>
!   generate
!   points <count>  followed by <count> lines "mu E1 px1 py1 pz1 ... En pxn pyn pzn"
! Point 1 is evaluated once untimed (initialization), then points 2..n,1 are
! timed. The public Fortran API is used because the 2.3.0 C++ header is
! incomplete. Values are raw Recola output (finite in Recola's convention).
program recola_reference
  use recola
  implicit none
  integer, parameter :: dp = kind(1d0)
  character(len=8192) :: line, keyword, process
  integer :: legs = -1, born_gs = -1, loop_gs = -1, pow_lo = -1, pow_nlo = -1
  integer :: count, i, k, ios, nf
  integer(8) :: c0, c1, rate
  real(dp) :: mass, width, value, mu
  real(dp), allocatable :: p(:,:,:), scales(:)
  real(dp) :: result(4), stored_alpha_s = -1d0
  integer :: stored_nf = -1
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
      if (stored_nf < 0 .or. legs < 3 .or. born_gs < 0 .or. loop_gs < 0 .or. pow_lo < 0 .or. pow_nlo < 0 &
          .or. len_trim(process) == 0) stop 'recola driver: incomplete process definition'
      call set_delta_uv_rcl(0d0)
      call set_delta_ir_rcl(0d0, 0d0)
      call set_dynamic_settings_rcl(1)
      call set_compute_ir_poles_rcl(1)
      call define_process_rcl(1, trim(process), 'NLO')
      call unselect_all_gs_powers_BornAmpl_rcl(1)
      call select_gs_power_BornAmpl_rcl(1, born_gs)
      call unselect_all_gs_powers_LoopAmpl_rcl(1)
      call select_gs_power_LoopAmpl_rcl(1, loop_gs)
      call system_clock(c0, rate)
      call generate_processes_rcl()
      call system_clock(c1)
      write(*, '(A,ES16.8)') 'GENERATION_SECONDS ', real(c1 - c0, dp) / rate
    case ('points')
      read(line, *) keyword, count
      allocate(p(0:3, legs, count), scales(count))
      do i = 1, count
        read(*, *) scales(i), p(:, :, i)
      end do
      call system_clock(c0, rate)
      call evaluate(1)
      call system_clock(c1)
      write(*, '(A,ES16.8)') 'INITIAL_CALL_SECONDS ', real(c1 - c0, dp) / rate
      do k = 2, count + 1
        i = merge(1, k, k > count)
        call system_clock(c0)
        call evaluate(i)
        call system_clock(c1)
        write(*, '(A,I6,ES16.8,4ES26.17E3)') 'ROW ', i, real(c1 - c0, dp) / rate, result
      end do
    case default
      write(*, *) 'recola driver: unknown command ', trim(keyword)
      stop 1
    end select
  end do
  call reset_recola_rcl()

contains

  subroutine evaluate(i)
    integer, intent(in) :: i
    call set_alphas_rcl(stored_alpha_s, scales(i), stored_nf)
    call set_mu_uv_rcl(scales(i))
    call set_mu_ir_rcl(scales(i))
    call compute_process_rcl(1, p(:, :, i), 'NLO')
    call get_squared_amplitude_rcl(1, pow_lo, 'LO', result(1))
    call get_squared_amplitude_rcl(1, pow_nlo, 'NLO', result(2))
    call get_squared_amplitude_rcl(1, pow_nlo, 'NLO-IR1', result(3))
    call get_squared_amplitude_rcl(1, pow_nlo, 'NLO-IR2', result(4))
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
      write(*, *) 'recola driver: unknown particle ', trim(name)
      stop 1
    end select
    if (width /= 0d0 .and. (trim(name) == 'strange' .or. trim(name) == 'up' .or. &
        trim(name) == 'down' .or. trim(name) == 'electron')) stop 'recola driver: width not settable'
  end subroutine
end program
