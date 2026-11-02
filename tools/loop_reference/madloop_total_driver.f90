! SPDX-License-Identifier: 0BSD
! MadLoop standalone driver for an export with one squared split order (e.g.
! a model whose orders the process fixes, HC_NLO_X0's rows): it prints the
! all-orders answer ANS(0:3, 0) = Born, finite, single and double pole, which
! is then that squared order's. Compile with -I pointing to the export's
! SubProcesses/P* directory; the runner substitutes the export's routine
! prefix for ML5_0_. Run in a directory holding Cards/param_card.dat and
! SubProcesses/MadLoop5_resources.
! Input on stdin:
!   alpha_s
!   count
!   count lines: mu E1 px1 py1 pz1 ... En pxn pyn pzn
! Point 1 is evaluated until MadLoop leaves its initialization phase
! (return-code tens digit 3 or 4), then every point once with MadLoop's own
! stability threshold. Output: DIMENSIONS nanswer nloop, then per point
! TOTAL index status born finite single double accuracy.
program madloop_total
  implicit none
  include 'nexternal.inc'
  integer, parameter :: dp = kind(1d0)
  integer :: nanswer, nloop, count, i, status, attempt
  real(dp) :: alpha_s
  real(dp), allocatable :: answer(:,:), accuracy(:), p(:,:,:), scales(:)
  character(512) :: card_path, resource_path
  read(*, *) alpha_s
  read(*, *) count
  allocate(p(0:3, nexternal, count), scales(count))
  do i = 1, count
    read(*, *) scales(i), p(:, :, i)
  end do
  card_path = 'Cards/param_card.dat'
  resource_path = 'SubProcesses/MadLoop5_resources'
  call setpara2(card_path)
  call update_as_param2(scales(1)**2, alpha_s)
  call setmadlooppath(resource_path)
  call ML5_0_get_answer_dimension(nanswer)
  call ML5_0_get_nsqso_loop(nloop)
  allocate(answer(0:3, 0:nanswer), accuracy(0:nloop))
  write(*, '(A,2I6)') 'DIMENSIONS ', nanswer, nloop
  do attempt = 1, 1000
    call ML5_0_sloopmatrix_thres(p(:, :, 1), answer, -1d0, accuracy, status)
    if (mod(status / 10, 10) /= 3 .and. mod(status / 10, 10) /= 4) exit
  end do
  do i = 1, count
    call update_as_param2(scales(i)**2, alpha_s)
    call ML5_0_sloopmatrix_thres(p(:, :, i), answer, -1d0, accuracy, status)
    write(*, '(A,2I6,5ES26.17E3)') 'TOTAL ', i, status, answer(0:3, 0), accuracy(0)
  end do
end program
