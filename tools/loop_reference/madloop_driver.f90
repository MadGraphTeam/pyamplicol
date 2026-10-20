! SPDX-License-Identifier: 0BSD
! Generic MadLoop standalone reference driver. Compile with -I pointing to the
! export's single SubProcesses/P* directory (for nexternal.inc); the Python
! runner substitutes the export's routine prefix for ML5_0_.
! Input on stdin:
!   born_qcd born_qed loop_qcd loop_qed alpha_s target_accuracy max_init_calls
!   count
!   count lines: mu E1 px1 py1 pz1 ... En pxn pyn pzn
! Run in a directory holding Cards/param_card.dat and
! SubProcesses/MadLoop5_resources. Born and Laurent coefficients are selected
! by squared split orders [QCD, QED]; physical couplings, no alpha extraction.
! Point 1 is evaluated untimed until initialization finishes, then points
! 2..n,1 are timed with the stability check forced (correctness priority).
program madloop_reference
  implicit none
  include 'nexternal.inc'
  integer, parameter :: dp = kind(1d0)
  integer :: nanswer, nloop, born_orders(2), loop_orders(2), born_index, loop_index
  integer :: count, i, k, status, attempt, max_init
  integer :: ML5_0_soindex_for_squared_orders, ML5_0_ml5soindex_for_squared_orders
  integer(8) :: c0, c1, rate
  real(dp) :: alpha_s, target, seconds
  real(dp), allocatable :: answer(:,:), accuracy(:), p(:,:,:), scales(:)
  character(512) :: card_path, resource_path
  read(*, *) born_orders, loop_orders, alpha_s, target, max_init
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
  born_index = ML5_0_soindex_for_squared_orders(born_orders)
  loop_index = ML5_0_ml5soindex_for_squared_orders(loop_orders)
  write(*, '(A,4I6)') 'SPLIT_ORDER_INDICES ', born_index, loop_index, nanswer, nloop
  call system_clock(c0, rate)
  do attempt = 1, max_init
    call ML5_0_force_stability_check(.true.)
    call ML5_0_sloopmatrix_thres(p(:, :, 1), answer, target, accuracy, status)
    if (mod(status / 10, 10) /= 3 .and. mod(status / 10, 10) /= 4) exit
  end do
  call system_clock(c1)
  write(*, '(A,ES16.8,2I8)') 'INITIAL_CALL_SECONDS ', real(c1 - c0, dp) / rate, attempt, status
  do k = 2, count + 1
    i = merge(1, k, k > count)
    call update_as_param2(scales(i)**2, alpha_s)
    call ML5_0_force_stability_check(.true.)
    call system_clock(c0)
    call ML5_0_sloopmatrix_thres(p(:, :, i), answer, target, accuracy, status)
    call system_clock(c1)
    seconds = real(c1 - c0, dp) / rate
    write(*, '(A,I6,I6,ES16.8,5ES26.17E3,4ES26.17E3)') 'ROW ', i, status, seconds, &
      answer(0, born_index), answer(1:3, loop_index), accuracy(loop_index), answer(0:3, 0)
  end do
end program
