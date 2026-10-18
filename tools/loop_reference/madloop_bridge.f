C SPDX-License-Identifier: 0BSD
      SUBROUTINE REFERENCE_MADLOOP_INIT(CARD,NC,RESOURCE,NR,
     $ AS_VALUE,MU_VALUE,MT_VALUE,AEW_VALUE) BIND(C)
      USE ISO_C_BINDING
      IMPLICIT NONE
      INTEGER(C_INT), VALUE :: NC,NR
      CHARACTER(KIND=C_CHAR), INTENT(IN) :: CARD(NC),RESOURCE(NR)
      REAL(C_DOUBLE), VALUE :: AS_VALUE,MU_VALUE,MT_VALUE,AEW_VALUE
      CHARACTER(512) CARD_PATH,RESOURCE_PATH
      INTEGER I
      INCLUDE 'coupl.inc'
      INCLUDE 'input.inc'
      INCLUDE 'mp_coupl.inc'
      INCLUDE 'mp_input.inc'
      CARD_PATH=' '
      RESOURCE_PATH=' '
      DO I=1,NC
        CARD_PATH(I:I)=CARD(I)
      ENDDO
      DO I=1,NR
        RESOURCE_PATH(I:I)=RESOURCE(I)
      ENDDO
      CALL SETPARA2(CARD_PATH)
      MDL_MT=MT_VALUE
      MDL_WT=0D0
      AEWM1=AEW_VALUE
C     Fixed model inputs are not synchronized by MP_UPDATE_AS_PARAM,
C     which only updates the running strong coupling and scale.
      MP__MDL_MT=REAL(MT_VALUE,KIND=16)
      MP__MDL_WT=0E0_16
      MP__AEWM1=REAL(AEW_VALUE,KIND=16)
      CALL COUP()
      CALL UPDATE_AS_PARAM2(MU_VALUE**2,AS_VALUE)
      CALL SETMADLOOPPATH(RESOURCE_PATH)
      END

      SUBROUTINE REFERENCE_MADLOOP_EVALUATE(P,ANSWER,ACCURACY,
     $ STATUS) BIND(C)
      USE ISO_C_BINDING
      IMPLICIT NONE
      REAL(C_DOUBLE), INTENT(IN) :: P(0:3,4)
      REAL(C_DOUBLE), INTENT(OUT) :: ANSWER(4),ACCURACY
      INTEGER(C_INT), INTENT(OUT) :: STATUS
      REAL(C_DOUBLE) RESULT(0:3,0:1),PRECISION(0:1)
C     The default MadLoop card asks for only 1D-3. These correctness
C     controls compare at 2D-9, so request enough digits for that check.
C     Any provider precision rescue remains inside the native timer.
      CALL ML5_0_SLOOPMATRIX_THRES(P,RESULT,1D-11,PRECISION,STATUS)
      ANSWER=RESULT(:,0)
      ACCURACY=PRECISION(0)
      END
