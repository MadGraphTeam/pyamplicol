! Provider capability/control preparation only; no pyAmpliCol generation.
program wg_polarizations
  use recola
  implicit none
  integer :: pr,k
  real(8) :: p(0:3,4),m,ecm,q,ew,answer(4),pi
  character(30) :: names(8)
  pi=acos(-1d0)
  m=sqrt(91.188d0**2/2+sqrt(91.188d0**4/4-pi*91.188d0**2/(132.50698d0*0.0000116639d0*sqrt(2d0))))
  ecm=1000d0;q=(ecm**2-m*m)/(2*ecm);ew=(ecm**2+m*m)/(2*ecm)
  call set_pole_mass_w_rcl(m,0d0)
  call set_pole_mass_z_rcl(91.188d0,0d0)
  call set_pole_mass_top_rcl(173d0,0d0)
  call set_pole_mass_bottom_rcl(0d0,0d0)
  call use_alpha0_scheme_rcl(1d0/132.50698d0)
  call set_alphas_rcl(.118d0,1000d0,5)
  call set_mu_uv_rcl(1000d0);call set_mu_ir_rcl(1000d0)
  call set_delta_uv_rcl(0d0);call set_delta_ir_rcl(0d0,0d0)
  call set_dynamic_settings_rcl(1);call set_compute_ir_poles_rcl(1)
  call set_cache_mode_rcl(0)
  names=[character(30)::'u d~ -> W+ g','u d~ -> W+[-] g', &
    'u d~ -> W+[0] g','u d~ -> W+[+] g', &
    'd W+ -> u g','d W+[-] -> u g','d W+[0] -> u g','d W+[+] -> u g']
  do pr=1,size(names)
    call define_process_rcl(pr,trim(names(pr)),'NLO')
    call unselect_all_gs_powers_BornAmpl_rcl(pr);call select_gs_power_BornAmpl_rcl(pr,1)
    call unselect_all_gs_powers_LoopAmpl_rcl(pr);call select_gs_power_LoopAmpl_rcl(pr,3)
  enddo
  call generate_processes_rcl()
  write(*,'(A,3ES26.17E3)') 'WGMASS ',m,q,ew
  do pr=1,size(names)
    if(pr<=4)then
      p(:,1)=[500d0,0d0,0d0,500d0];p(:,2)=[500d0,0d0,0d0,-500d0]
      p(:,3)=[ew,.6d0*q,0d0,.8d0*q];p(:,4)=[q,-.6d0*q,0d0,-.8d0*q]
    else
      p(:,1)=[q,0d0,0d0,q];p(:,2)=[ew,0d0,0d0,-q]
      p(:,3)=[500d0,300d0,0d0,400d0];p(:,4)=[500d0,-300d0,0d0,-400d0]
    endif
    call compute_process_rcl(pr,p,'NLO')
    call get_squared_amplitude_rcl(pr,1,'LO',answer(1))
    call get_squared_amplitude_rcl(pr,2,'NLO',answer(2))
    call get_squared_amplitude_rcl(pr,2,'NLO-IR1',answer(3))
    call get_squared_amplitude_rcl(pr,2,'NLO-IR2',answer(4))
    write(*,'(A,I3,4ES26.17E3)') 'WGHEL ',pr,answer
  enddo
  call reset_recola_rcl()
end program
