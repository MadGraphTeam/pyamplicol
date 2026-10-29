! SPDX-License-Identifier: 0BSD
! Generic MadLoop standalone reference driver. Compile with -I pointing to the
! export's SubProcesses/P* directory (for nexternal.inc); the Python runner
! substitutes the export's routine prefix for ML5_0_ and the path of the
! export's helicity table for HELCONFIGS_FILE.
! Input on stdin:
!   born_qcd born_qed loop_qcd loop_qed alpha_s target_accuracy force_check
!   count
!   count lines: mu E1 px1 py1 pz1 ... En pxn pyn pzn
!   [nhel                      optional per-helicity mode: nhel tuples follow
!    nhel lines: h1 ... hn]    (MadLoop helicity labels, one per external leg)
! target_accuracy > 0 overrides MLStabThres (quadruple-precision rescue when the
! estimated accuracy is worse); target_accuracy <= 0 keeps MadLoop's own
! MLStabThres (production setting). force_check /= 0 forces the stability test
! on every call, including the initialization phase.
! Run in a directory holding Cards/param_card.dat and
! SubProcesses/MadLoop5_resources. Born and Laurent coefficients are selected
! by squared split orders [QCD, QED]; physical couplings, no alpha extraction.
! Point 1 is evaluated untimed until MadLoop leaves its initialization phase
! (return-code tens digit 3 or 4; MadLoop ends it after a fixed number of
! calls set in MadLoopParams.dat), then points 2..n,1 are timed once each.
! Output: SPLIT_ORDER_INDICES, LOOP_SO (index -> squared orders of every loop
! split order; the Born ones are read from born_matrix.f by the runner, since
! MG5 3.7.0's GET_SQUARED_ORDERS_FOR_SOINDEX reads a common block it never
! initialises), INITIAL_CALL_SECONDS, then per point a ROW line (the
! requested sector and the all-orders sum, unchanged format) and a SECTORS line
! with the complete answer array ANS(0:3, 0:nanswer) (column-major: Born and
! the three Laurent coefficients per index; Born indices follow the Born split
! orders, loop indices LOOP_SO, index 0 = sum over orders) and MadLoop's accuracy estimate
! ACC(0:nloop) of every loop split order. In per-helicity mode each point is
! followed by one HEL_ROW line per requested tuple (SLOOPMATRIXHEL_THRES): the
! same arrays for that helicity configuration alone, in MadLoop's per-helicity
! normalisation (colour average and identical-particle factor, no helicity
! average: the sum over all tuples is HELAVGFACTOR times the summed value).
program madloop_reference
  implicit none
  include 'nexternal.inc'
  integer, parameter :: dp = kind(1d0)
  integer :: nanswer, nloop, born_orders(2), loop_orders(2), born_index, loop_index
  integer :: count, i, k, j, h, status, attempt, force_check, ios, nhel, ncomb, unit_hel
  integer :: orders(2)
  integer :: ML5_0_soindex_for_squared_orders, ML5_0_ml5soindex_for_squared_orders
  integer(8) :: c0, c1, rate
  real(dp) :: alpha_s, target, seconds
  real(dp), allocatable :: answer(:,:), accuracy(:), p(:,:,:), scales(:)
  integer, allocatable :: tuples(:,:), table(:,:), hel_index(:)
  integer :: row(nexternal)
  character(512) :: card_path, resource_path
  read(*, *) born_orders, loop_orders, alpha_s, target, force_check
  read(*, *) count
  allocate(p(0:3, nexternal, count), scales(count))
  do i = 1, count
    read(*, *) scales(i), p(:, :, i)
  end do
  read(*, *, iostat=ios) nhel
  if (ios /= 0) nhel = 0
  allocate(tuples(nexternal, max(nhel, 1)), hel_index(max(nhel, 1)))
  do h = 1, nhel
    read(*, *) tuples(:, h)
  end do
  if (target <= 0d0) target = -1d0
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
  do i = 1, nloop
    call ML5_0_ml5get_squared_orders_for_soindex(i, orders)
    write(*, '(A,3I6)') 'LOOP_SO ', i, orders
  end do
  if (nhel > 0) then
    ! MadLoop numbers helicity configurations by their line in HelConfigs.dat.
    open(newunit=unit_hel, file='HELCONFIGS_FILE', status='old', action='read')
    ncomb = 0
    do
      read(unit_hel, *, iostat=ios) row
      if (ios /= 0) exit
      ncomb = ncomb + 1
    end do
    allocate(table(nexternal, ncomb))
    rewind(unit_hel)
    do j = 1, ncomb
      read(unit_hel, *) table(:, j)
    end do
    close(unit_hel)
    do h = 1, nhel
      hel_index(h) = 0
      do j = 1, ncomb
        if (all(table(:, j) == tuples(:, h))) hel_index(h) = j
      end do
      if (hel_index(h) == 0) then
        write(*, '(A,I6)') 'ERROR helicity tuple not in HelConfigs.dat: ', h
        stop 3
      end if
      write(*, '(A,2I6,*(I3))') 'HEL_INDEX ', h, hel_index(h), tuples(:, h)
    end do
  end if
  call system_clock(c0, rate)
  attempt = 0
  do
    attempt = attempt + 1
    call ML5_0_force_stability_check(force_check /= 0)
    call ML5_0_sloopmatrix_thres(p(:, :, 1), answer, target, accuracy, status)
    if (mod(status / 10, 10) /= 3 .and. mod(status / 10, 10) /= 4) exit
  end do
  call system_clock(c1)
  write(*, '(A,ES16.8,2I8)') 'INITIAL_CALL_SECONDS ', real(c1 - c0, dp) / rate, attempt, status
  do k = 2, count + 1
    i = merge(1, k, k > count)
    call update_as_param2(scales(i)**2, alpha_s)
    call ML5_0_force_stability_check(force_check /= 0)
    call system_clock(c0)
    call ML5_0_sloopmatrix_thres(p(:, :, i), answer, target, accuracy, status)
    call system_clock(c1)
    seconds = real(c1 - c0, dp) / rate
    write(*, '(A,I6,I6,ES16.8,5ES26.17E3,4ES26.17E3)') 'ROW ', i, status, seconds, &
      answer(0, born_index), answer(1:3, loop_index), accuracy(loop_index), answer(0:3, 0)
    write(*, '(A,I6,I6,*(ES26.17E3))') 'SECTORS ', i, status, answer, accuracy
    do h = 1, nhel
      call ML5_0_force_stability_check(force_check /= 0)
      call system_clock(c0)
      call ML5_0_sloopmatrixhel_thres(p(:, :, i), hel_index(h), answer, target, accuracy, status)
      call system_clock(c1)
      seconds = real(c1 - c0, dp) / rate
      write(*, '(A,3I6,ES16.8,*(ES26.17E3))') 'HEL_ROW ', i, h, status, seconds, answer, accuracy
    end do
  end do
end program
