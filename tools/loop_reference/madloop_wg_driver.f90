! SPDX-License-Identifier: 0BSD
program wg_reference
  implicit none
  integer::pr,k,j,pol,nanswer,status
  real(8)::p(0:3,4),m,q,ew,pi
  real(8),allocatable::answer(:,:),accuracy(:)
  character(512)::card_path,resource_path
  card_path='Cards/param_card.dat'
  resource_path='SubProcesses/MadLoop5_resources'
  call setpara2(card_path)
  call update_as_param2(1000000d0,.118d0)
  call setmadlooppath(resource_path)
  pi=acos(-1d0)
  m=sqrt(91.188d0**2/2+sqrt(91.188d0**4/4-pi*91.188d0**2/(132.50698d0*.0000116639d0*sqrt(2d0))))
  q=(1000000d0-m*m)/2000d0;ew=(1000000d0+m*m)/2000d0
  do pr=0,2
    if(pr==1)then
      j=2
      p(:,1)=[q,0d0,0d0,q];p(:,2)=[ew,0d0,0d0,-q]
      p(:,3)=[500d0,300d0,0d0,400d0];p(:,4)=[500d0,-300d0,0d0,-400d0]
    else
      j=3
      p(:,1)=[500d0,0d0,0d0,500d0];p(:,2)=[500d0,0d0,0d0,-500d0]
      p(:,3)=[ew,.6d0*q,0d0,.8d0*q];p(:,4)=[q,-.6d0*q,0d0,-.8d0*q]
    endif
    select case(pr)
    case(0)
      call ml5_0_get_answer_dimension(nanswer)
    case(1)
      call ml5_1_get_answer_dimension(nanswer)
    case(2)
      call ml5_2_get_answer_dimension(nanswer)
    end select
    allocate(answer(0:3,0:nanswer),accuracy(0:nanswer))
    do k=0,3
      pol=k-2
      if(k==0)pol=-10000
      select case(pr)
      case(0)
        call ml5_0_set_leg_polarization(j,pol)
        call ml5_0_force_stability_check(.true.)
        call ml5_0_sloopmatrix_thres(p,answer,1d-10,accuracy,status)
      case(1)
        call ml5_1_set_leg_polarization(j,pol)
        call ml5_1_force_stability_check(.true.)
        call ml5_1_sloopmatrix_thres(p,answer,1d-10,accuracy,status)
      case(2)
        call ml5_2_set_leg_polarization(j,pol)
        call ml5_2_force_stability_check(.true.)
        call ml5_2_sloopmatrix_thres(p,answer,1d-10,accuracy,status)
      end select
      write(*,'(A,3I5,5ES26.17E3)')'WGML ',pr,k,status,answer(:,0),accuracy(0)
    enddo
    deallocate(answer,accuracy)
  enddo
end program
