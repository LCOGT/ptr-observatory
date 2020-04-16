10 REM     READIT.BAS -- PROGRAM TO DEMONSTRATE THE SIMPLEST
20 REM         POSSIBLE WAY TO READ THE SKYCAT.DAT FILE
30 REM          Copyright (c) 1989 Sky Publishing Corp.
40 REM                Version of October 21, 1989
50 REM   
60 S$=CHR$(34): REM  Symbol for arc seconds (")
70 H1$=" SAO       R.A.        Dec.     PM(a)  PM(d)"
80 H1$=H1$+"   V    B-V   Sp   RV  Dist"
90 H2$="         h  m  s      o  '  "+S$+"    s      "+S$
100 H2$=H2$+"                     km/s  pc"
110 C$="SKYCAT.DAT"
120 OPEN "R",1,C$,52
130 FIELD 1,6 AS SA$,7 AS A$,7 AS D$,5 AS A1$,4 AS D1$,4 AS V$
140 FIELD 1,33 AS X$,4 AS BV$,2 AS T$,4 AS RV$,5 AS P$,4 AS N$
150 S=1: E=45269!
160 PRINT: PRINT "Enter a starting and ending number:"
170 INPUT "    Start, end";S,E
180 IF S<1 OR E>45269! OR E<S THEN PRINT "Invalid numbers": GOTO 160
190 CLS
200 PRINT H1$: PRINT H2$
210 FOR J=S TO E
220 GET#1,J
230 S5$=SA$: T5$=T$: R5$=RV$
240 A5$=LEFT$(A$,2)+" "+MID$(A$,3,2)+" "+MID$(A$,5,2)+"."+RIGHT$(A$,1)
250 D5$=LEFT$(D$,3)+" "+MID$(D$,4,2)+" "+RIGHT$(D$,2)
260 A6$=LEFT$(A1$,2)+"."+RIGHT$(A1$,3): IF A6$="  .   " THEN A6$="      "
270 D6$=LEFT$(D1$,2)+"."+RIGHT$(D1$,2): IF D6$="  .  " THEN D6$="     "
280 V5$=LEFT$(V$,2)+"."+RIGHT$(V$,2)
290 B5$=LEFT$(BV$,2)+"."+RIGHT$(BV$,2): IF B5$="  .  " THEN B5$="     "
300 P5$=P$+" ": P1$=RIGHT$(P5$,2): P2$=""
310 IF P1$="h " THEN P2$="mx"
320 IF P1$="l " THEN P2$="mn"
330 IF P1$="c " THEN P2$="ts"
340 IF P2$<>"" THEN P5$=LEFT$(P5$,4)+P2$
350 N1$="   ": IF N$<>"    " THEN N1$="  *"
360 REM   An asterisk means the star has one or more common names.
370 REM   These names (or other notes) are stored in the NAMES.DAT file.
380 REM   The SKYCAT.BAS program illustrates how to read these names.
390 REM
400 PRINT S5$;"  ";A5$;"  ";D5$;"  ";A6$;" ";D6$;"  ";
410 PRINT V5$;" ";B5$;"  ";T5$;" "R5$;" ";P5$;N1$
420 NEXT J
430 CLOSE
440 END
