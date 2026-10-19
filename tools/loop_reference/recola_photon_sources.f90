! Independent ordinary/singleton source controls; no timing assertions.
program photon_sources
  use recola
  implicit none
  integer :: i,k,n,pr,j
  real(8) :: p(0:3,4),mu,born,answer(4),vre(0:3),vim(0:3),d1(4),d2(4)
  complex(8) :: v(0:3)
  d1=[0d0,1d0,0d0,2d0];d2=[0d0,0d0,1d0,3d0]
  read(*,*) n
  call set_pole_mass_top_rcl(173d0,0d0)
  call set_pole_mass_bottom_rcl(0d0,0d0)
  call use_alpha0_scheme_rcl(1d0/132.50698d0)
  call set_alphas_rcl(.118d0,1000d0,5)
  call set_mu_uv_rcl(1000d0);call set_mu_ir_rcl(1000d0)
  call set_delta_uv_rcl(0d0);call set_delta_ir_rcl(0d0,0d0)
  call set_dynamic_settings_rcl(1);call set_compute_ir_poles_rcl(1)
  call set_cache_mode_rcl(0)
  call define_process_rcl(1,'u u~ -> A g','NLO')
  call define_process_rcl(2,'u A -> u g','NLO')
  do pr=1,2
    call unselect_all_gs_powers_BornAmpl_rcl(pr);call select_gs_power_BornAmpl_rcl(pr,1)
    call unselect_all_gs_powers_LoopAmpl_rcl(pr);call select_gs_power_LoopAmpl_rcl(pr,3)
  enddo
  call generate_processes_rcl()
  do i=1,n
    read(*,*) pr,j,mu,p,vre,vim
    v=cmplx(vre,vim,kind=8)
    call set_alphas_rcl(.118d0,mu,5);call set_mu_uv_rcl(mu);call set_mu_ir_rcl(mu)
    if(j==0) then
      call compute_process_rcl(pr,p,'NLO')
      call get_squared_amplitude_rcl(pr,1,'LO',born)
      call get_squared_amplitude_rcl(pr,2,'NLO',answer(1))
      call get_squared_amplitude_rcl(pr,2,'NLO-IR1',answer(2))
      call get_squared_amplitude_rcl(pr,2,'NLO-IR2',answer(3))
      answer(4)=answer(1)+2*answer(2)+3*answer(3)
    else
      call compute_spin_correlation_rcl(pr,p,j,v,'LO',born)
      do k=1,4
        call set_delta_ir_rcl(d1(k),d2(k))
        call compute_spin_correlation_rcl(pr,p,j,v,'NLO',answer(k))
      enddo
      answer(2:3)=answer(2:3)-answer(1)
      call set_delta_ir_rcl(0d0,0d0)
    endif
    write(*,'(A,I5,5ES26.17E3)') 'PHOTON ',i,born,answer
  enddo
  call reset_recola_rcl()
end program
