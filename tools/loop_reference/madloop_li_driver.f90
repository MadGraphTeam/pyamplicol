! SPDX-License-Identifier: 0BSD
! MadLoop standalone driver for a loop-induced (loop-squared, Born-less) export:
! no Born split-order index (a [sqrvirt=...] export has no born_matrix.f). Compile
! with -I pointing to the export's SubProcesses/P* directory; the runner
! substitutes the export's routine prefix for ML5_0_ and the path of its helicity
! table for HELCONFIGS_FILE.
! Input on stdin:
!   loop_sq_qcd loop_sq_qed alpha_s target_accuracy force_check warmup
!   count
!   count lines: mu E1 px1 py1 pz1 ... En pxn pyn pzn
!   [nhel                      optional per-helicity mode: nhel tuples follow
!    nhel lines: h1 ... hn]    (MadLoop helicity labels, one per external leg)
! loop_sq_* are the squared split orders of |A_loop|^2. target_accuracy > 0
! overrides MLStabThres (quadruple-precision rescue when the estimated accuracy
! is worse); <= 0 keeps MadLoop's own MLStabThres (production). force_check /= 0
! forces the stability test on every call.
! Warm-up (untimed): MadLoop's loop-induced zero-test scale REF is the median
! of earlier helicity-summed results and its first point never counts towards
! the filter set-up, so the initialisation phase spans CheckCycle+1 calls. The
! driver cycles through the input points until MadLoop has left its
! initialisation phase (return-code tens digit not 3 or 4) AND at least
! `warmup` calls were made (the runner passes CheckCycle+1), then times every
! point once (points 1..n in order).
! Output: SPLIT_ORDER_INDICES loop_index nanswer nloop, LOOP_SO lines,
! INITIAL_CALL_SECONDS seconds calls status, then per point
!   ROW i status seconds ans(0:3,loop_index) acc(loop_index) ans(0:3,0)
! (ans(1:3,*) = finite, 1/eps, 1/eps^2 of |A|^2; ans(0,*) = MadLoop's Born
! slot, zero for loop-induced) and, per requested helicity tuple,
!   HEL_ROW i h status seconds ans(0:3,0:nanswer) acc(0:nloop)
! from SLOOPMATRIXHEL_THRES (MadLoop's USERHEL convention: colour average and
! identical-particle factor but NO helicity average, i.e. HELAVGFACTOR times
! the |A(h)|^2/avg of the summed convention). The driver resets MadLoop's USERHEL
! (common /ML5_0_USERCHOICE/) to -1 after the helicity rows: SLOOPMATRIXHEL never
! resets it, so a later summed call would otherwise return one helicity only.
program madloop_li_reference
  implicit none
  include 'nexternal.inc'
  integer, parameter :: dp = kind(1d0)
  integer :: nanswer, nloop, loop_orders(2), loop_index
  integer :: count, i, k, j, h, status, attempt, force_check, ios, nhel, ncomb, unit_hel, warmup
  integer :: orders(2)
  integer :: ML5_0_ml5soindex_for_squared_orders
  integer(8) :: c0, c1, rate
  real(dp) :: alpha_s, target, seconds
  real(dp), allocatable :: answer(:,:), accuracy(:), p(:,:,:), scales(:)
  integer, allocatable :: tuples(:,:), table(:,:), hel_index(:)
  integer :: row(nexternal)
  integer :: userhel
  common/ML5_0_USERCHOICE/userhel
  character(512) :: card_path, resource_path
  read(*, *) loop_orders, alpha_s, target, force_check, warmup
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
  loop_index = ML5_0_ml5soindex_for_squared_orders(loop_orders)
  write(*, '(A,3I6)') 'SPLIT_ORDER_INDICES ', loop_index, nanswer, nloop
  do i = 1, nloop
    call ML5_0_ml5get_squared_orders_for_soindex(i, orders)
    write(*, '(A,3I6)') 'LOOP_SO ', i, orders
  end do
  if (nhel > 0) then
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
    i = mod(attempt, count) + 1
    attempt = attempt + 1
    call update_as_param2(scales(i)**2, alpha_s)
    call ML5_0_force_stability_check(force_check /= 0)
    call ML5_0_sloopmatrix_thres(p(:, :, i), answer, target, accuracy, status)
    if (attempt >= warmup .and. mod(status / 10, 10) /= 3 .and. mod(status / 10, 10) /= 4) exit
    if (attempt > 100000) stop 'madloop li driver: MadLoop never left its initialisation phase'
  end do
  call system_clock(c1)
  write(*, '(A,ES16.8,2I8)') 'INITIAL_CALL_SECONDS ', real(c1 - c0, dp) / rate, attempt, status
  do i = 1, count
    call update_as_param2(scales(i)**2, alpha_s)
    call ML5_0_force_stability_check(force_check /= 0)
    call system_clock(c0)
    call ML5_0_sloopmatrix_thres(p(:, :, i), answer, target, accuracy, status)
    call system_clock(c1)
    seconds = real(c1 - c0, dp) / rate
    write(*, '(A,I6,I6,ES16.8,5ES26.17E3,4ES26.17E3)') 'ROW ', i, status, seconds, &
      answer(0:3, loop_index), accuracy(loop_index), answer(0:3, 0)
    do h = 1, nhel
      call ML5_0_force_stability_check(force_check /= 0)
      call system_clock(c0)
      call ML5_0_sloopmatrixhel_thres(p(:, :, i), hel_index(h), answer, target, accuracy, status)
      call system_clock(c1)
      seconds = real(c1 - c0, dp) / rate
      write(*, '(A,3I6,ES16.8,*(ES26.17E3))') 'HEL_ROW ', i, h, status, seconds, answer, accuracy
    end do
    ! SLOOPMATRIXHEL leaves MadLoop's USERHEL at the last helicity: without this
    ! reset every later summed call would return that helicity alone (x HELAVGFACTOR).
    userhel = -1
  end do
end program
