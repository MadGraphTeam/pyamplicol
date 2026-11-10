! SPDX-License-Identifier: 0BSD
! Recola 2.3.0 / SM 2.2.3 reference of tests/fixtures/loop/uux-ddxepem-recola-cms.json (built-in
! example 2, u u~ > d d~ e+ e-): the complex-mass scheme (set_complex_mass_scheme_rcl) with the example's
! widths, the G_mu scheme with alpha_Gmu = sqrt(2) G_F |mu_W^2 (1 - mu_W^2 / mu_Z^2)| / pi of the complex
! masses, massless b, c, s, u, d and leptons, alpha_s 0.118 at mu, mu_UV = mu_IR = mu_R, every gs power.
! stdin: the Recola process string ('u u~ -> d d~ e+ e-'); the number of legs; the number of points; then per
! point mu_R^2 and p(0:3, leg) (examples/data/loop_uux_ddxepem_momenta.json at mu_R^2 = s).
! stdout per point i and alpha_s power pw (0..4): 'ROW i pw LO NLO NLO-IR1 NLO-IR2 NLO-D4 NLO-CT NLO-R2'
! and 'UV1 i pw' (the Delta_UV = 1 shifts of D4, CT, R2). The fixture's sector of pw is QCD^(2 pw) (Born) and
! QCD^(2 pw) with the rest QED (virtual); virtual = [NLO + pi^2/6 NLO-IR2, NLO-IR1, NLO-IR2] (Recola's
! Gamma(1+eps) normalisation mapped to C_eps = (4 pi)^eps / Gamma(1 - eps)).
! Build: gfortran -O2 -ffree-line-length-none -I<recola>/include recola_uux_ddxepem_cms.f90 -L<recola> -lrecola
!        -L<collier> -lcollier (Recola 2.3.0, COLLIER 1.2.8).
program fa_ew6_recola
  use recola
  implicit none
  integer :: i,n,nleg,k,pw,j
  character(len=200) :: proc
  real(8), allocatable :: p(:,:)
  real(8) :: mu2, lo(0:4), nlo(0:4), ir1(0:4), ir2(0:4), comp(3), base(0:4,3), samp(0:4,3)
  real(8) :: d4(0:4), ct(0:4), r2(0:4), alpha_gmu
  complex(8) :: mw2, mz2
  read(*,'(A)') proc
  read(*,*) nleg
  allocate(p(0:3,nleg))
  call set_pole_mass_w_rcl(80.419d0,2.09291d0)
  call set_pole_mass_z_rcl(91.188d0,2.49877d0)
  call set_pole_mass_h_rcl(125d0,0.00407468d0)
  call set_pole_mass_top_rcl(173.3d0,1.37758d0)
  call set_pole_mass_bottom_rcl(0d0,0d0)
  call set_pole_mass_charm_rcl(0d0,0d0)
  call set_pole_mass_strange_rcl(0d0)
  call set_pole_mass_up_rcl(0d0)
  call set_pole_mass_down_rcl(0d0)
  call set_pole_mass_tau_rcl(0d0,0d0)
  call set_pole_mass_muon_rcl(0d0,0d0)
  call set_pole_mass_electron_rcl(0d0)
  mw2 = cmplx(80.419d0**2,-80.419d0*2.09291d0,kind=8)
  mz2 = cmplx(91.188d0**2,-91.188d0*2.49877d0,kind=8)
  alpha_gmu = sqrt(2d0)*0.0000116639d0*abs(mw2*(1d0-mw2/mz2))/acos(-1d0)
  call set_complex_mass_scheme_rcl()
  call use_gfermi_scheme_rcl(a=alpha_gmu)
  write(*,"(A,ES26.17E3)") "ALPHA_GMU ",alpha_gmu
  call set_alphas_rcl(0.118d0,1000d0,5)
  call set_mu_uv_rcl(1000d0)
  call set_mu_ir_rcl(1000d0)
  call set_delta_uv_rcl(0d0)
  call set_delta_ir_rcl(0d0,0d0)
  call set_dynamic_settings_rcl(1)
  call set_compute_ir_poles_rcl(1)
  call set_print_level_amplitude_rcl(0)
  call define_process_rcl(1,trim(proc),'NLO')
  call generate_processes_rcl()
  read(*,*) n
  do i=1,n
    read(*,*) mu2, p
    call set_alphas_rcl(0.118d0,sqrt(mu2),5)
    call set_mu_uv_rcl(sqrt(mu2))
    call set_mu_ir_rcl(sqrt(mu2))
    call set_delta_uv_rcl(0d0)
    call set_delta_ir_rcl(0d0,0d0)
    call compute_process_rcl(1,p,'NLO')
    do pw=0,4
      lo(pw)=0d0; nlo(pw)=0d0; ir1(pw)=0d0; ir2(pw)=0d0; d4(pw)=0d0; ct(pw)=0d0; r2(pw)=0d0
      call get_squared_amplitude_rcl(1,pw,'LO',lo(pw))
      call get_squared_amplitude_rcl(1,pw,'NLO',nlo(pw))
      call get_squared_amplitude_rcl(1,pw,'NLO-IR1',ir1(pw))
      call get_squared_amplitude_rcl(1,pw,'NLO-IR2',ir2(pw))
      call get_squared_amplitude_rcl(1,pw,'NLO-D4',d4(pw))
      call get_squared_amplitude_rcl(1,pw,'NLO-CT',ct(pw))
      call get_squared_amplitude_rcl(1,pw,'NLO-R2',r2(pw))
      write(*,'(A,2I5,7ES26.17E3)') 'ROW ',i,pw,lo(pw),nlo(pw),ir1(pw),ir2(pw),d4(pw),ct(pw),r2(pw)
    end do
    ! UV pole sampling: deltaUV=1 shift of the bare (D4) and CT pieces
    call set_delta_uv_rcl(1d0)
    call compute_process_rcl(1,p,'NLO')
    do pw=0,4
      samp(pw,:)=0d0
      call get_squared_amplitude_rcl(1,pw,'NLO-D4',samp(pw,1))
      call get_squared_amplitude_rcl(1,pw,'NLO-CT',samp(pw,2))
      call get_squared_amplitude_rcl(1,pw,'NLO-R2',samp(pw,3))
      write(*,'(A,2I5,3ES26.17E3)') 'UV1 ',i,pw,samp(pw,1)-d4(pw),samp(pw,2)-ct(pw),samp(pw,3)-r2(pw)
    end do
    call set_delta_uv_rcl(0d0)
  end do
  call reset_recola_rcl()
end program
