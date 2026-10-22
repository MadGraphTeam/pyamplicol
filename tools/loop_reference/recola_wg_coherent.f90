! SPDX-License-Identifier: 0BSD
! Reference-only three-state contraction using Recola's own states,
! coherent matrix, colour coefficients and averaging factors.
module wg_source_reference
  use globals_rcl, only: dp,prs,newleg,cfTot,csTot,he,factor
  use amplitude_rcl, only: matrix,momenta
  use order_rcl, only: oiSize,compoi
  use wave_functions_rcl, only: definewp
  implicit none
contains
  subroutine wg_states(prin,j,m,w)
    integer,intent(in)::prin,j
    real(dp),intent(in)::m
    complex(dp),intent(out)::w(0:3,-1:1)
    complex(dp)::p(0:3),pl(4)
    integer::h
    p=cmplx(momenta(:,j),kind=dp)
    if(j>prs(prin)%legsIn)p=-p
    pl=[p(0)+p(3),p(0)-p(3),p(1)+cmplx(0d0,1d0,dp)*p(2),p(1)-cmplx(0d0,1d0,dp)*p(2)]
    do h=-1,1
      call definewp(prs(prin)%par(j),p,pl,m,h,w(:,h))
    enddo
  end subroutine

  subroutine wg_project(prin,j,m,v,answer)
    integer,intent(in)::prin,j
    real(dp),intent(in)::m
    complex(dp),intent(in)::v(0:3)
    real(dp),intent(out)::answer(2)
    integer::pr,jj,n,k,h,oi,c1,c2,legs,indices(-1:1)
    complex(dp)::w(0:3,-1:1),a(-1:1)
    complex(dp),allocatable::b(:),l(:)
    pr=prin
    if(prs(prin)%crosspr/=0)then
      pr=prs(prin)%crosspr
      jj=newleg(prs(prin)%relperm(j),pr)
    else
      jj=newleg(j,pr)
    endif
    legs=prs(pr)%legs
    call wg_states(prin,j,m,w)
    do h=-1,1
      a(h)=v(0)*conjg(w(0,h))-sum(v(1:3)*conjg(w(1:3,h)))
    enddo
    allocate(b(csTot(pr)),l(csTot(pr)))
    answer=0d0
    do n=1,cfTot(pr)
      if(he(jj,n,pr)/=-1)cycle
      indices=0
      do k=1,cfTot(pr)
        if(all(he(1:jj-1,k,pr)==he(1:jj-1,n,pr)).and. &
           all(he(jj+1:legs,k,pr)==he(jj+1:legs,n,pr)))then
          h=he(jj,k,pr)
          if(h< -1.or.h>1.or.indices(h)/=0)error stop 'invalid Recola vector states'
          indices(h)=k
        endif
      enddo
      if(any(indices==0))error stop 'missing Recola longitudinal state'
      b=0;l=0
      do h=-1,1
        do oi=1,oiSize(pr)
          if(compoi(oi,0,pr)) b=b+a(h)*matrix(1:csTot(pr),oi,indices(h),0,prin)
          if(compoi(oi,1,pr)) l=l+a(h)*matrix(1:csTot(pr),oi,indices(h),4,prin)
        enddo
      enddo
      do c1=1,csTot(pr)
        do c2=1,csTot(pr)
          answer(1)=answer(1)+prs(pr)%colcoef(c1,c2)*real(conjg(b(c1))*b(c2),dp)
          answer(2)=answer(2)+2*prs(pr)%colcoef(c1,c2)*real(conjg(b(c1))*l(c2),dp)
        enddo
      enddo
    enddo
    answer=answer*factor(prin)
  end subroutine
end module
