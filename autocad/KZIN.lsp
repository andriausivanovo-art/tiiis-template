;;; =====================================================================
;;; KZIN.lsp - Koordinačių žiniaraščio formavimas
;;;
;;; AutoLISP funkcijos PZIN ("Koordinačių žiniaraštis") iš
;;; "Matininkas 2015 for AutoCAD" (mati2004.arx) atitikmuo.
;;;
;;; Komanda: KZIN
;;;
;;; Atkurta pagal originalo elgseną:
;;;   - blokas "koordinate" (apskritimas R=1 + atributai Koordinate/KM/TYPE),
;;;     sluoksnis "Koordinate";
;;;   - ribos linija (R, TYPE=1): polilinija uždaroma, taškai numeruojami
;;;     nuo pažymėtos viršūnės pagal laikrodžio rodyklę, linija -> sl. "riba";
;;;   - ašinė linija (A, TYPE=2): pradedama nuo pradžios arba pabaigos,
;;;     KM = pradinis km + atstumas išilgai linijos / 1000 (%.3f),
;;;     linija -> sl. "asis";
;;;   - centro taškas / taškinis objektas (O, TYPE=3);
;;;   - numeracija "1.1" -> 1.1, 1.2, ...; "5" -> 5, 6, ...;
;;;   - besidubliuojančios koordinatės (X, Y 0.01 tikslumu) neįterpiamos
;;;     antrą kartą ir pažymimos sąraše;
;;;   - koordinatės išnaša ir linijos išnaša (blokas "isnasa",
;;;     atributai Koordinate_x / Koordinate_y, sluoksnis "Išnaša");
;;;   - taško bloko nustatymai: žymėjimo aukštis, V/H pozicija, taško dydis.
;;;
;;; X - šiaurės koordinatė (AutoCAD Y), Y - rytų koordinatė (AutoCAD X),
;;; kaip LKS-94 ir originaliame žiniaraštyje.
;;;
;;; Failas UTF-8 koduotės. Reikalingas AutoCAD 2021+ (LISPSYS = 1).
;;; =====================================================================

(vl-load-com)

(setq *kz-set* nil   ; nustatymai (alist)
      *kz-pts* nil   ; taškų sąrašas: (ename nr pt km type owner key)
      *kz-sel* nil)  ; pažymėta eilutė sąraše

;;; ---------------------------------------------------------------------
;;; Lietuviškos raidės
;;; Faile tekstai rašomi tik ASCII simboliais: {a}=ą {c}=č {e}=ę {ee}=ė
;;; {i}=į {s}=š {u}=ų {uu}=ū {z}=ž (didžiosios: {A} {C} ...). Raidės
;;; sukuriamos vykdymo metu, todėl failo koduotė nesvarbi.
;;; ---------------------------------------------------------------------

;; (žymė unicode ANSI-1257 hex)
(setq *kz-lt*
  '(("{a}" 261 224 "0105") ("{A}" 260 192 "0104")
    ("{c}" 269 232 "010D") ("{C}" 268 200 "010C")
    ("{e}" 281 230 "0119") ("{E}" 280 198 "0118")
    ("{ee}" 279 235 "0117") ("{EE}" 278 203 "0116")
    ("{i}" 303 225 "012F") ("{I}" 302 193 "012E")
    ("{s}" 353 240 "0161") ("{S}" 352 208 "0160")
    ("{u}" 371 248 "0173") ("{U}" 370 216 "0172")
    ("{uu}" 363 251 "016B") ("{UU}" 362 219 "016A")
    ("{z}" 382 254 "017E") ("{Z}" 381 222 "017D")))

;; ar AutoLISP dirba Unicode režimu (LISPSYS = 1)
(setq *kz-uni*
  (and (= (getvar "LISPSYS") 1)
       (not (vl-catch-all-error-p (setq *kz-tmp* (vl-catch-all-apply 'chr '(353)))))
       (= (ascii *kz-tmp*) 353)))

(defun kz:subst-all (new old s)
  (while (vl-string-search old s)
    (setq s (vl-string-subst new old s))
  )
  s
)

;; tekstas su lietuviškomis raidėmis (pranešimams, sluoksniams, atributams)
(defun kz:t (s)
  (foreach m *kz-lt*
    (setq s (kz:subst-all (chr (if *kz-uni* (cadr m) (caddr m))) (car m) s))
  )
  s
)

;; tas pats DCL failui: \U+XXXX kodai, failas lieka ASCII
(defun kz:td (s)
  (foreach m *kz-lt*
    (setq s (kz:subst-all (strcat "\\U+" (cadddr m)) (car m) s))
  )
  s
)

(setq *kz-isn* (kz:t "I{s}na{s}a")) ; išnašų sluoksnis

;;; ---------------------------------------------------------------------
;;; Bendros pagalbinės funkcijos
;;; ---------------------------------------------------------------------

;; DIMZIN komandos metu = 0, todėl nuliai po kablelio nenukerpami
(defun kz:fmt (v prec) (rtos v 2 prec))

;; koordinačių raktas 0.01 tikslumu (dublikatų paieškai)
(defun kz:key (p) (strcat (kz:fmt (car p) 2) "," (kz:fmt (cadr p) 2)))

(defun kz:eq2 (a b) (= (kz:key a) (kz:key b)))

(defun kz:pt3 (p) (list (car p) (cadr p) 0.0))

(defun kz:pad (s n)
  (while (< (strlen s) n) (setq s (strcat s " ")))
  s
)

(defun kz:num (s) (atof (vl-string-translate "," "." s)))

(defun kz:taip (msg / r)
  (initget "Taip Ne")
  (setq r (getkword (strcat "\n" msg " [Taip/Ne] <Taip>: ")))
  (/= r "Ne")
)

(defun kz:hex (s / n)
  (setq n 0.0)
  (foreach c (vl-string->list (strcase s))
    (setq n (+ (* n 16.0) (if (> c 57) (- c 55) (- c 48))))
  )
  n
)

(defun kz:list-insert (l i x / r k)
  (setq k 0)
  (foreach a l
    (if (= k i) (setq r (cons x r)))
    (setq r (cons a r) k (1+ k))
  )
  (if (>= i (length l)) (setq r (cons x r)))
  (reverse r)
)

(defun kz:list-remove (l i / r k)
  (setq k 0)
  (foreach a l
    (if (/= k i) (setq r (cons a r)))
    (setq k (1+ k))
  )
  (reverse r)
)

;;; ---------------------------------------------------------------------
;;; Nustatymai
;;; ---------------------------------------------------------------------

(defun kz:get (k) (cdr (assoc k *kz-set*)))

(defun kz:put (k v)
  (if v (setq *kz-set* (subst (cons k v) (assoc k *kz-set*) *kz-set*)))
)

(defun kz:load-settings (/ d x lg)
  (setq *kz-set* (list (cons "aukstis" 1.0)
                       (cons "vpoz" 0.5)
                       (cons "hpoz" 0.5)
                       (cons "dydis" 0.3)
                       (cons "nr" "1")
                       (cons "km" "0.000")))
  (cond
    ((setq d (dictsearch (namedobjdict) "KZIN_NUSTATYMAI"))
     (kz:put "aukstis" (cdr (assoc 40 d)))
     (kz:put "vpoz" (cdr (assoc 41 d)))
     (kz:put "hpoz" (cdr (assoc 42 d)))
     (kz:put "dydis" (cdr (assoc 43 d)))
     (kz:put "nr" (cdr (assoc 300 d)))
     (kz:put "km" (cdr (assoc 301 d))))
    ;; Matininko (PZIN) nustatymai, jei brėžinys ruoštas su juo
    ((and (setq d (dictsearch (namedobjdict) "PIK_BLOCK_STYLE"))
          (setq x (assoc -3 (entget (cdr (assoc -1 d))
                                    '("ZINIARASTIS_BLOKO_NUSTATYMAI_V2"))))
          (setq lg (mapcar 'cdr
                           (vl-remove-if-not '(lambda (g) (= (car g) 1040))
                                             (cdadr x))))
          (= (length lg) 4))
     (kz:put "aukstis" (nth 0 lg))
     (kz:put "vpoz" (nth 1 lg))
     (kz:put "hpoz" (nth 2 lg))
     (kz:put "dydis" (nth 3 lg)))
  )
)

(defun kz:save-settings (/ nod)
  (setq nod (namedobjdict))
  (if (dictsearch nod "KZIN_NUSTATYMAI")
    (entdel (dictremove nod "KZIN_NUSTATYMAI"))
  )
  (dictadd nod "KZIN_NUSTATYMAI"
           (entmakex (list '(0 . "XRECORD")
                           '(100 . "AcDbXrecord")
                           (cons 40 (kz:get "aukstis"))
                           (cons 41 (kz:get "vpoz"))
                           (cons 42 (kz:get "hpoz"))
                           (cons 43 (kz:get "dydis"))
                           (cons 300 (kz:get "nr"))
                           (cons 301 (kz:get "km")))))
)

;;; ---------------------------------------------------------------------
;;; Sluoksniai ir blokai
;;; ---------------------------------------------------------------------

(defun kz:layer (nm)
  (if (not (tblsearch "LAYER" nm))
    (entmake (list '(0 . "LAYER")
                   '(100 . "AcDbSymbolTableRecord")
                   '(100 . "AcDbLayerTableRecord")
                   (cons 2 nm)
                   '(70 . 0)
                   '(62 . 7)
                   '(6 . "Continuous")))
  )
  nm
)

(defun kz:attdef (tag lay inv)
  (entmake (list '(0 . "ATTDEF")
                 (cons 8 lay)
                 '(62 . 256)
                 '(10 1.0 1.0 0.0)
                 '(40 . 1.0)
                 '(1 . "")
                 (cons 3 tag)
                 (cons 2 tag)
                 (cons 70 (if inv 1 0))
                 '(7 . "Standard")))
)

(defun kz:ensure-blocks ()
  (kz:layer "Koordinate")
  (kz:layer *kz-isn*)
  (regapp "KZIN")
  (if (not (tblsearch "BLOCK" "koordinate"))
    (progn
      (entmake '((0 . "BLOCK") (8 . "0") (2 . "koordinate") (70 . 2) (10 0.0 0.0 0.0)))
      (entmake '((0 . "CIRCLE") (8 . "Koordinate") (62 . 256) (10 0.0 0.0 0.0) (40 . 1.0)))
      (kz:attdef "Koordinate" "Koordinate" nil)
      (kz:attdef "KM" "Koordinate" T)
      (kz:attdef "TYPE" "Koordinate" T)
      (entmake '((0 . "ENDBLK") (8 . "0")))
    )
  )
  (if (not (tblsearch "BLOCK" "isnasa"))
    (progn
      (entmake '((0 . "BLOCK") (8 . "0") (2 . "isnasa") (70 . 2) (10 0.0 0.0 0.0)))
      (entmake (list '(0 . "LINE") (cons 8 *kz-isn*) '(62 . 256) '(10 0.0 0.0 0.0) '(11 9.0 0.0 0.0)))
      (kz:attdef "Koordinate_x" *kz-isn* nil)
      (kz:attdef "Koordinate_y" *kz-isn* nil)
      (entmake '((0 . "ENDBLK") (8 . "0")))
    )
  )
)

;;; ---------------------------------------------------------------------
;;; Atributai ir taškų sąrašas
;;; ---------------------------------------------------------------------

(defun kz:atts (e / a r el)
  (setq a (entnext e))
  (while (and a (= (cdr (assoc 0 (setq el (entget a)))) "ATTRIB"))
    (setq r (cons (cons (strcase (cdr (assoc 2 el))) a) r)
          a (entnext a))
  )
  r
)

(defun kz:attval (e tag / a)
  (if (setq a (cdr (assoc (strcase tag) (kz:atts e))))
    (cdr (assoc 1 (entget a)))
    ""
  )
)

(defun kz:setatt (e tag val / a el)
  (if (setq a (cdr (assoc (strcase tag) (kz:atts e))))
    (progn
      (setq el (entget a))
      (entmod (subst (cons 1 val) (assoc 1 el) el))
      (entupd e)
    )
  )
)

(defun kz:owner (el / x)
  (if (setq x (assoc -3 el))
    (cdr (assoc 1005 (cdadr x)))
  )
)

;; (ename nr pt km type owner eile raktas), surikiuota pagal sukūrimo eiliškumą
(defun kz:points (/ ss i e el l)
  (if (setq ss (ssget "_X" '((0 . "INSERT") (2 . "koordinate"))))
    (repeat (setq i (sslength ss))
      (setq e  (ssname ss (setq i (1- i)))
            el (entget e '("KZIN"))
            l  (cons (list e
                           (kz:attval e "Koordinate")
                           (cdr (assoc 10 el))
                           (kz:attval e "KM")
                           (kz:attval e "TYPE")
                           (kz:owner el)
                           (kz:hex (cdr (assoc 5 el)))
                           (kz:key (cdr (assoc 10 el))))
                     l))
    )
  )
  (vl-sort l '(lambda (a b) (< (nth 6 a) (nth 6 b))))
)

(defun kz:find-at (pt / k r)
  (setq k (kz:key pt))
  (foreach p *kz-pts*
    (if (and (not r) (= (nth 7 p) k) (entget (car p)))
      (setq r (car p))
    )
  )
  r
)

(defun kz:tipas (ty)
  (cond ((= ty "1") "R")
        ((= ty "2") "A")
        ((= ty "3") "O")
        (T "")
  )
)

(defun kz:dups (/ l r prev)
  (setq l (vl-sort (mapcar '(lambda (p) (cons (nth 7 p) (car p))) *kz-pts*)
                   '(lambda (a b) (< (car a) (car b)))))
  (foreach a l
    (if (and prev (= (car a) (car prev)))
      (setq r (cons (cdr a) (cons (cdr prev) r)))
    )
    (setq prev a)
  )
  r
)

;;; ---------------------------------------------------------------------
;;; Taško bloko įterpimas
;;; ---------------------------------------------------------------------

(defun kz:insert-point (pt nr km ty owner / e s h ip)
  (setq pt (kz:pt3 pt))
  (if (setq e (kz:find-at pt))
    e ; tokia koordinatė jau yra - antrą kartą neįterpiama
    (progn
      (setq s  (kz:get "dydis")
            h  (kz:get "aukstis")
            ip (list (+ (car pt) (kz:get "hpoz")) (+ (cadr pt) (kz:get "vpoz")) 0.0))
      (entmake
        (list '(0 . "INSERT") '(66 . 1) '(2 . "koordinate") '(8 . "Koordinate")
              '(62 . 256) (cons 10 pt) (cons 41 s) (cons 42 s) (cons 43 s) '(50 . 0.0)
              (list -3 (append (list "KZIN" '(1000 . "TASKAS"))
                               (if owner (list (cons 1005 owner)))))))
      (foreach a (list (list "Koordinate" nr 0)
                       (list "KM" (if km (kz:fmt km 3) "") 1)
                       (list "TYPE" ty 1))
        (entmake (list '(0 . "ATTRIB") '(8 . "Koordinate") '(62 . 256)
                       (cons 10 ip) (cons 40 h) (cons 1 (cadr a)) (cons 2 (car a))
                       (cons 70 (caddr a)) '(7 . "Standard") '(50 . 0.0)))
      )
      (entmake '((0 . "SEQEND") (8 . "Koordinate")))
      (setq e (entlast))
      (setq *kz-pts* (append *kz-pts*
                             (list (list e nr pt (if km (kz:fmt km 3) "") ty owner
                                         (kz:hex (cdr (assoc 5 (entget e))))
                                         (kz:key pt)))))
      e
    )
  )
)

;; "1.1" -> ("1." . 1); "1." -> ("1." . 1); "5" -> ("" . 5)
(defun kz:parse-nr (s / p)
  (setq s (vl-string-translate "," "." (vl-string-trim " " s)))
  (cond ((or (= s "") (= (atoi s) 0)) (cons "" (1+ (length *kz-pts*))))
        ((not (setq p (vl-string-position 46 s nil T))) (cons "" (atoi s)))
        ((= p (1- (strlen s))) (cons s 1))
        (T (cons (substr s 1 (1+ p)) (atoi (substr s (+ p 2)))))
  )
)

(defun kz:next-nr (s / n)
  (setq n (kz:parse-nr s))
  (strcat (car n) (itoa (1+ (cdr n))))
)

;;; ---------------------------------------------------------------------
;;; Polilinijos
;;; ---------------------------------------------------------------------

(defun kz:verts (el)
  (mapcar 'cdr (vl-remove-if-not '(lambda (g) (= (car g) 10)) el))
)

(defun kz:has-arcs (el)
  (vl-some '(lambda (g) (and (= (car g) 42) (/= (cdr g) 0.0))) el)
)

(defun kz:closed-p (el) (= 1 (logand 1 (cdr (assoc 70 el)))))

(defun kz:area2 (vs / a n i p q)
  (setq a 0.0 n (length vs) i 0)
  (repeat n
    (setq p (nth i vs)
          q (nth (rem (1+ i) n) vs)
          a (+ a (- (* (car p) (cadr q)) (* (car q) (cadr p))))
          i (1+ i))
  )
  a
)

(defun kz:vidx (vs p / i r)
  (setq i 0)
  (foreach v vs
    (if (and (not r) (kz:eq2 v p)) (setq r i))
    (setq i (1+ i))
  )
  r
)

(defun kz:pick-pline (msg / es e el p)
  (setq es (entsel msg))
  (cond
    ((null es) nil)
    ((/= (cdr (assoc 0 (setq el (entget (setq e (car es)))))) "LWPOLYLINE")
     (princ (strcat (kz:t "\nPa{z}ym{ee}tas objektas yra: ") (cdr (assoc 0 el)) "\n"))
     nil)
    ((kz:has-arcs el)
     (princ (kz:t "\nPolilinija (Polyline) turi lank{u} (Arcs)\n"))
     nil)
    ((null (setq p (osnap (cadr es) "_end")))
     (princ (kz:t "\nPa{z}ym{ee}kite linij{a} ar{c}iau jos vir{s}{uu}n{ee}s.\n"))
     nil)
    (T (list e (trans p 1 0) el))
  )
)

(defun kz:pline-at (msg / p ss)
  (if (and (setq p (getpoint msg))
           (setq p (cond ((osnap p "_near")) (p)))
           (setq ss (ssget p '((0 . "LWPOLYLINE")))))
    (list (ssname ss 0) (trans p 1 0))
  )
)

;; linijos duomenys: (tipas km0 pradzios_taskas kryptis)
(defun kz:set-line-data (e ty km0 spt dir lay / el)
  (kz:layer lay)
  (setq el (entget e))
  (setq el (subst (cons 8 lay) (assoc 8 el) el))
  (entmod (append el
                  (list (list -3 (list "KZIN" '(1000 . "LINIJA") (cons 1070 ty)
                                       (cons 1040 km0) (cons 1010 (kz:pt3 spt))
                                       (cons 1070 dir))))))
)

(defun kz:line-data (e / x i)
  (if (setq x (assoc -3 (entget e '("KZIN"))))
    (progn
      (setq x (cdadr x))
      (list (cdr (assoc 1070 x))
            (cdr (assoc 1040 x))
            (cdr (assoc 1010 x))
            (cdr (assoc 1070 (cdr (member (assoc 1070 x) x)))))
    )
  )
)

;; LWPOLYLINE -> (antraste virsuniu_sarasas pabaiga)
(defun kz:pl-split (el / hd vl cur tl mode)
  (setq mode 0)
  (foreach g el
    (cond
      ((= (car g) 10)
       (if cur (setq vl (cons (reverse cur) vl)))
       (setq cur (list g) mode 1))
      ((and (= mode 1) (member (car g) '(40 41 42 91)))
       (setq cur (cons g cur)))
      ((= mode 0) (setq hd (cons g hd)))
      (T (if cur (setq vl (cons (reverse cur) vl) cur nil))
         (setq tl (cons g tl) mode 2))
    )
  )
  (if cur (setq vl (cons (reverse cur) vl)))
  (list (reverse hd) (reverse vl) (reverse tl))
)

(defun kz:pl-join (hd vl tl)
  (entmod (append (subst (cons 90 (length vl)) (assoc 90 hd) hd)
                  (apply 'append vl)
                  tl))
)

(defun kz:dists (vs / d r p)
  (setq d 0.0)
  (foreach v vs
    (if p (setq d (+ d (distance p v))))
    (setq r (cons d r) p v)
  )
  (reverse r)
)

;;; ---------------------------------------------------------------------
;;; Veiksmai
;;; ---------------------------------------------------------------------

;; Ribos linija (R)
(defun kz:riba (/ r e p el vs n st dir nr pr num k)
  (if (setq r (kz:pick-pline (kz:t "\nPa{z}ym{ee}kite polilinij{a} (Polyline) be lank{u} (Arcs)\n")))
    (progn
      (setq e (car r) p (cadr r) el (caddr r) vs (kz:verts el) n (length vs)
            st (kz:vidx vs p))
      (if (and (null st)
               (kz:taip (kz:t "Nepavyko pasirinkti numeravimo prad{z}ios ta{s}ko. Ar prad{ee}ti numeracija nuo prad{z}ios?")))
        (setq st 0)
      )
      (if st
        (progn
          (if (not (kz:closed-p el))
            (entmod (subst (cons 70 (logior 1 (cdr (assoc 70 el)))) (assoc 70 el) el))
          )
          (setq dir (if (< (kz:area2 vs) 0.0) 1 -1) ; pagal laikrodžio rodyklę
                nr  (kz:parse-nr (kz:get "nr"))
                pr  (car nr)
                num (cdr nr)
                k   0)
          (repeat n
            (kz:insert-point (nth (rem (+ n st (* dir k)) n) vs)
                             (strcat pr (itoa num)) nil "1" (cdr (assoc 5 el)))
            (setq num (1+ num) k (1+ k))
          )
          (kz:set-line-data e 1 -1.0 (nth st vs) dir "riba")
          (kz:put "nr" (strcat pr (itoa num)))
        )
      )
    )
  )
)

;; Ašinė linija (A)
(defun kz:asis (/ r e p el vs n st dir ds km0 nr pr num k idx)
  (if (setq r (kz:pick-pline (kz:t "\nPa{z}ym{ee}kite polilinij{a} (Polyline) be lank{u} (Arcs)\n")))
    (progn
      (setq e (car r) p (cadr r) el (caddr r) vs (kz:verts el) n (length vs))
      (cond ((kz:eq2 p (car vs)) (setq st 0 dir 1))
            ((kz:eq2 p (nth (1- n) vs)) (setq st (1- n) dir -1))
            (T (alert (kz:t "Reikia pasirinkti a{s}in{ee}s linijos prad{z}i{a} arba pabaig{a}")))
      )
      (if st
        (progn
          (setq ds  (kz:dists vs)
                km0 (kz:num (kz:get "km"))
                nr  (kz:parse-nr (kz:get "nr"))
                pr  (car nr)
                num (cdr nr)
                k   0)
          (repeat n
            (setq idx (+ st (* dir k)))
            (kz:insert-point (nth idx vs) (strcat pr (itoa num))
                             (+ km0 (/ (abs (- (nth idx ds) (nth st ds))) 1000.0))
                             "2" (cdr (assoc 5 el)))
            (setq num (1+ num) k (1+ k))
          )
          (kz:set-line-data e 2 km0 (nth st vs) dir "asis")
          (kz:put "nr" (strcat pr (itoa num)))
        )
      )
    )
  )
)

;; Centro taškas / taškinis objektas (O)
(defun kz:centras (/ nr pr num p)
  (setq nr (kz:parse-nr (kz:get "nr")) pr (car nr) num (cdr nr))
  (while (setq p (getpoint (kz:t "\nPa{z}ym{ee}kit objekt{a} <Enter - baigti>: ")))
    (kz:insert-point (trans p 1 0) (strcat pr (itoa num)) nil "3" nil)
    (setq num (1+ num))
  )
  (kz:put "nr" (strcat pr (itoa num)))
)

;; Ištrinti objekto taškus
(defun kz:trinti-obj (/ es e el h)
  (if (setq es (entsel (kz:t "\nPa{z}ym{ee}kit objekt{a}: ")))
    (progn
      (setq e (car es) el (entget e))
      (if (and (= (cdr (assoc 0 el)) "INSERT")
               (= (strcase (cdr (assoc 2 el))) "KOORDINATE"))
        (entdel e)
        (progn
          (setq h (cdr (assoc 5 el)))
          (foreach p *kz-pts*
            (if (= (nth 5 p) h) (entdel (car p)))
          )
        )
      )
    )
  )
)

;; išnašos linija + blokas "isnasa"
(defun kz:isnasa (p q top bot / s h v hp w len ins e)
  (setq s  (kz:get "dydis")
        h  (kz:get "aukstis")
        v  (kz:get "vpoz")
        hp (kz:get "hpoz")
        p  (kz:pt3 p)
        q  (kz:pt3 q)
        w  (max (car (cadr (textbox (list (cons 1 top) (cons 40 h) '(7 . "Standard")))))
                (car (cadr (textbox (list (cons 1 bot) (cons 40 h) '(7 . "Standard"))))))
        len (max (* 9.0 s) (+ w hp hp))
        ins (if (< (car q) (car p)) (list (- (car q) len) (cadr q) 0.0) q))
  (entmake (list '(0 . "LINE") (cons 8 *kz-isn*) '(62 . 256) (cons 10 p) (cons 11 q)))
  (entmake (list '(0 . "INSERT") '(66 . 1) '(2 . "isnasa") (cons 8 *kz-isn*) '(62 . 256)
                 (cons 10 ins) (cons 41 (/ len 9.0)) (cons 42 s) (cons 43 s) '(50 . 0.0)))
  (foreach a (list (list "Koordinate_x" top (+ (cadr ins) v))
                   (list "Koordinate_y" bot (- (cadr ins) v h)))
    (entmake (list '(0 . "ATTRIB") (cons 8 *kz-isn*) '(62 . 256)
                   (list 10 (+ (car ins) hp) (caddr a) 0.0)
                   (cons 40 h) (cons 1 (cadr a)) (cons 2 (car a)) '(70 . 0)
                   '(7 . "Standard") '(50 . 0.0)))
  )
  (entmake (list '(0 . "SEQEND") (cons 8 *kz-isn*)))
)

;; Koordinatės išnaša
(defun kz:isn-koord (/ p q)
  (if (and (setq p (getpoint (kz:t "\nPasirinkite ta{s}k{a}")))
           (setq q (getpoint p (kz:t "\nPasirinkite i{s}na{s}os viet{a}"))))
    (progn
      (setq p (trans p 1 0) q (trans q 1 0))
      (kz:isnasa p q (kz:fmt (cadr p) 2) (kz:fmt (car p) 2))
    )
  )
)

(defun kz:eil-nr (pt / i k r)
  (setq i 1 k (kz:key pt))
  (foreach p *kz-pts*
    (if (and (not r) (= (nth 7 p) k)) (setq r i))
    (setq i (1+ i))
  )
  r
)

;; Linijos išnaša: "a-b" ir "L = ..."
(defun kz:isn-linija (/ r e q vs a b len)
  (if (and (setq r (kz:pline-at (kz:t "\nPa{z}ym{ee}kit ta{s}k{a} ant linijos\n")))
           (setq q (getpoint (trans (cadr r) 0 1) (kz:t "\nPasirinkite i{s}na{s}os viet{a}"))))
    (progn
      (setq e   (car r)
            vs  (kz:verts (entget e))
            a   (kz:eil-nr (car vs))
            b   (kz:eil-nr (nth (1- (length vs)) vs))
            len (vlax-curve-getDistAtParam e (vlax-curve-getEndParam e)))
      (kz:isnasa (cadr r) (trans q 1 0)
                 (strcat (if (and a b) (itoa (min a b)) (if a (itoa a) "?"))
                         "-"
                         (if (and a b) (itoa (max a b)) (if b (itoa b) "?")))
                 (strcat "L = " (kz:fmt len 2)))
    )
  )
)

;; Pridėti tašką į liniją
(defun kz:prideti (/ r e p el sp ld ty km nr s)
  (if (setq r (kz:pline-at (kz:t "\nPa{z}ym{ee}kit ta{s}k{a} ant linijos\n")))
    (progn
      (setq e  (car r)
            p  (vlax-curve-getClosestPointTo e (cadr r))
            sp (kz:pl-split (entget e))
            ld (kz:line-data e)
            ty (if ld (itoa (car ld)) "1"))
      (kz:pl-join (car sp)
                  (kz:list-insert (cadr sp)
                                  (1+ (fix (vlax-curve-getParamAtPoint e p)))
                                  (list (list 10 (car p) (cadr p)) '(40 . 0.0) '(41 . 0.0) '(42 . 0.0)))
                  (caddr sp))
      (if (and ld (= ty "2"))
        (setq km (+ (cadr ld)
                    (/ (abs (- (vlax-curve-getDistAtPoint e (vlax-curve-getClosestPointTo e p))
                               (vlax-curve-getDistAtPoint e (vlax-curve-getClosestPointTo e (caddr ld)))))
                       1000.0)))
      )
      (setq nr (kz:get "nr")
            s  (getstring (strcat (kz:t "\nTa{s}ko numeris <") nr ">: ")))
      (if (/= s "") (setq nr s))
      (kz:insert-point p nr km ty (cdr (assoc 5 (entget e))))
      (kz:put "nr" (kz:next-nr nr))
    )
  )
)

;; Ištrinti tašką iš linijos
(defun kz:istrinti (/ r e el sp vs i best d bi b)
  (if (setq r (kz:pline-at (kz:t "\nPa{z}ym{ee}kit ta{s}k{a} ant linijos\n")))
    (progn
      (setq e  (car r)
            el (entget e)
            vs (kz:verts el)
            i  0)
      (foreach v vs
        (setq d (distance (kz:pt3 v) (kz:pt3 (cadr r))))
        (if (or (null best) (< d best)) (setq best d bi i))
        (setq i (1+ i))
      )
      (if (<= (length vs) (if (kz:closed-p el) 3 2))
        (alert (kz:t "Linijoje turi likti bent 2 ta{s}kai (u{z}daroje - 3)."))
        (progn
          (if (setq b (kz:find-at (nth bi vs))) (entdel b))
          (setq sp (kz:pl-split el))
          (kz:pl-join (car sp) (kz:list-remove (cadr sp) bi) (caddr sp))
        )
      )
    )
  )
)

;; Pernumeruoti taškus (pvz. 1.1 -> 1.1, 1.2, ...)
(defun kz:pernumeruoti (/ s nr pr num m es e el vs n ld st dir k idx b)
  (setq s (getstring (strcat (kz:t "\nPrad{z}ios numeris (pvz. 1.1) <") (kz:get "nr") ">: ")))
  (if (= s "") (setq s (kz:get "nr")))
  (setq nr (kz:parse-nr s) pr (car nr) num (cdr nr))
  (initget "Linija Taskai")
  (setq m (getkword "\nPernumeruoti [Linija/Taskai] <Linija>: "))
  (if (= m "Taskai")
    (while (setq es (entsel (kz:t "\nPa{z}ym{ee}kite ta{s}k{a} <Enter - baigti>: ")))
      (setq e (car es) el (entget e))
      (if (and (= (cdr (assoc 0 el)) "INSERT")
               (= (strcase (cdr (assoc 2 el))) "KOORDINATE"))
        (progn
          (kz:setatt e "Koordinate" (strcat pr (itoa num)))
          (setq num (1+ num))
        )
        (princ (kz:t "\nTai ne koordinat{ee}s ta{s}kas."))
      )
    )
    (if (and (setq es (entsel (kz:t "\nPa{z}ym{ee}kite linij{a}: ")))
             (= (cdr (assoc 0 (setq el (entget (setq e (car es)))))) "LWPOLYLINE"))
      (progn
        (setq vs  (kz:verts el)
              n   (length vs)
              ld  (kz:line-data e)
              st  (cond ((and ld (caddr ld) (kz:vidx vs (caddr ld)))) (0))
              dir (cond ((and ld (cadddr ld))) (1))
              k   0)
        (repeat n
          (setq idx (if (kz:closed-p el) (rem (+ n st (* dir k)) n) (+ st (* dir k))))
          (if (and (>= idx 0) (< idx n) (setq b (kz:find-at (nth idx vs))))
            (progn
              (kz:setatt b "Koordinate" (strcat pr (itoa num)))
              (setq num (1+ num))
            )
          )
          (setq k (1+ k))
        )
      )
    )
  )
  (kz:put "nr" (strcat pr (itoa num)))
)

;; Pritaikyti bloko nustatymus visiems taškams
(defun kz:apply-settings (/ s h v hp el ins a ael)
  (setq s (kz:get "dydis") h (kz:get "aukstis") v (kz:get "vpoz") hp (kz:get "hpoz"))
  (foreach p *kz-pts*
    (if (setq el (entget (car p)))
      (progn
        (setq ins (cdr (assoc 10 el)))
        (entmod (subst (cons 41 s) (assoc 41 el)
                       (subst (cons 42 s) (assoc 42 el)
                              (subst (cons 43 s) (assoc 43 el) el))))
        (foreach a (kz:atts (car p))
          (setq ael (entget (cdr a)))
          (setq ael (subst (list 10 (+ (car ins) hp) (+ (cadr ins) v) (caddr ins))
                           (assoc 10 ael) ael))
          (setq ael (subst (cons 40 h) (assoc 40 ael) ael))
          (entmod ael)
        )
        (entupd (car p))
      )
    )
  )
  (kz:save-settings)
)

;;; ---------------------------------------------------------------------
;;; Rodymas, lentelė, CSV
;;; ---------------------------------------------------------------------

(defun kz:zoom (p1 p2)
  (vla-ZoomWindow (vlax-get-acad-object) (vlax-3d-point p1) (vlax-3d-point p2))
)

(defun kz:rodyti (kas / p m e mn mx xs ys)
  (setq m (max 5.0 (* 10.0 (kz:get "aukstis"))))
  (cond
    ((= kas "viska")
     (if *kz-pts*
       (progn
         (setq xs (mapcar '(lambda (p) (car (nth 2 p))) *kz-pts*)
               ys (mapcar '(lambda (p) (cadr (nth 2 p))) *kz-pts*))
         (kz:zoom (list (- (apply 'min xs) m) (- (apply 'min ys) m) 0.0)
                  (list (+ (apply 'max xs) m) (+ (apply 'max ys) m) 0.0))
       )
     ))
    ((null (setq p (and *kz-sel* (nth *kz-sel* *kz-pts*))))
     (alert (kz:t "Pasirinkite ta{s}k{a} s{a}ra{s}e.")))
    ((= kas "taska")
     (setq p (nth 2 p))
     (kz:zoom (list (- (car p) m) (- (cadr p) m) 0.0) (list (+ (car p) m) (+ (cadr p) m) 0.0)))
    ((and (nth 5 p) (setq e (handent (nth 5 p))) (entget e))
     (vla-GetBoundingBox (vlax-ename->vla-object e) 'mn 'mx)
     (setq mn (vlax-safearray->list mn) mx (vlax-safearray->list mx))
     (kz:zoom (list (- (car mn) m) (- (cadr mn) m) 0.0) (list (+ (car mx) m) (+ (cadr mx) m) 0.0)))
    (T (alert (kz:t "Ta{s}kas nesusietas su linija.")))
  )
)

(defun kz:rows (/ i r d)
  (setq i 1 d (kz:dups))
  (foreach p *kz-pts*
    (setq r (cons (list (itoa i)
                        (nth 1 p)
                        (kz:fmt (cadr (nth 2 p)) 2)
                        (kz:fmt (car (nth 2 p)) 2)
                        (nth 3 p)
                        (kz:tipas (nth 4 p))
                        (if (member (car p) d) "*" ""))
                  r)
          i (1+ i))
  )
  (reverse r)
)

(defun kz:lentele (/ ip rows tbl h r c ms)
  (setq rows (kz:rows))
  (cond
    ((null rows) (alert (kz:t "S{a}ra{s}e n{ee}ra ta{s}k{u}.")))
    ((setq ip (getpoint (kz:t "\nNurodykite lentel{ee}s viet{a}: ")))
     (setq h   (kz:get "aukstis")
           ms  (vla-get-ModelSpace (vla-get-ActiveDocument (vlax-get-acad-object)))
           tbl (vla-AddTable ms (vlax-3d-point (trans ip 1 0)) (+ 2 (length rows)) 6
                             (* 2.0 h) (* 8.0 h)))
     (vla-put-RegenerateTableSuppressed tbl :vlax-true)
     (vla-SetTextHeight tbl 7 h)
     (vla-SetText tbl 0 0 (kz:t "KOORDINA{C}I{U} {Z}INIARA{S}TIS"))
     (setq c 0)
     (foreach t1 (list "Eil.Nr." (kz:t "Ta{s}ko Nr.") "X" "Y" "Km" "Tipas")
       (vla-SetText tbl 1 c t1)
       (setq c (1+ c))
     )
     (setq r 2)
     (foreach row rows
       (setq c 0)
       (foreach v (reverse (cdr (reverse row)))
         (vla-SetText tbl r c v)
         (setq c (1+ c))
       )
       (setq r (1+ r))
     )
     (vla-SetColumnWidth tbl 2 (* 12.0 h))
     (vla-SetColumnWidth tbl 3 (* 12.0 h))
     (vla-put-RegenerateTableSuppressed tbl :vlax-false))
  )
)

(defun kz:open-w (fn / f)
  (setq f (vl-catch-all-apply 'open (list fn "w" "utf8")))
  (if (or (null f) (vl-catch-all-error-p f))
    (progn (setq *kz-utf8* nil) (open fn "w"))
    (progn (setq *kz-utf8* T) f)
  )
)

(defun kz:csv (/ fn f)
  (if (setq fn (getfiled (kz:t "I{s}saugoti koordina{c}i{u} {z}iniara{s}t{i}")
                         (strcat (getvar "DWGPREFIX") "ziniarastis") "csv" 1))
    (progn
      (setq f (kz:open-w fn))
      ;; BOM, kad Excel atpažintų UTF-8
      (if (and *kz-utf8* *kz-uni*) (princ (chr 65279) f))
      (write-line (kz:t "Eil.Nr.;Ta{s}ko Nr.;X;Y;Km;Tipas") f)
      (foreach row (kz:rows)
        (write-line (strcat (nth 0 row) ";" (nth 1 row) ";" (nth 2 row) ";"
                            (nth 3 row) ";" (nth 4 row) ";" (nth 5 row))
                    f)
      )
      (close f)
      (princ (strcat (kz:t "\nI{s}saugota: ") fn))
    )
  )
)

;;; ---------------------------------------------------------------------
;;; Dialogas
;;; ---------------------------------------------------------------------

(defun kz:dcl-lines ()
  '("kzin : dialog {"
    "  label = \"Koordina{c}i{u} {z}iniara{s}{c}io formavimas\";"
    "  : row {"
    "    : boxed_column {"
    "      label = \"Pradiniai duomenys\";"
    "      : edit_box { key = \"nr\"; label = \"Nr.:\"; edit_width = 10; }"
    "      : edit_box { key = \"km\"; label = \"Km:\"; edit_width = 10; }"
    "      : button { key = \"riba\"; label = \"Ribos linija\"; }"
    "      : button { key = \"asis\"; label = \"A{s}in{e} linij{a}\"; }"
    "      : button { key = \"centras\"; label = \"Centro ta{s}k{a}\"; }"
    "      : button { key = \"trinti\"; label = \"I{s}trinti objekto ta{s}kus\"; }"
    "    }"
    "    : boxed_column {"
    "      label = \"Ta{s}ko bloko nustatymai\";"
    "      : edit_box { key = \"aukstis\"; label = \"{Z}ym{ee}jimo auk{s}tis:\"; edit_width = 8; }"
    "      : edit_box { key = \"vpoz\"; label = \"V pozicija:\"; edit_width = 8; }"
    "      : edit_box { key = \"hpoz\"; label = \"H pozicija:\"; edit_width = 8; }"
    "      : edit_box { key = \"dydis\"; label = \"Ta{s}ko dydis:\"; edit_width = 8; }"
    "      : button { key = \"saugoti\"; label = \"Saugoti\"; }"
    "      : text { label = \"Legenda:\"; }"
    "      : text { label = \"A - a{s}is\"; }"
    "      : text { label = \"R - riba\"; }"
    "      : text { label = \"O - ta{s}kinis objektas\"; }"
    "      : text { label = \"* - besidubliojan{c}ios koordinat{ee}s\"; }"
    "    }"
    "    : column {"
    "      : boxed_column {"
    "        label = \"I{s}na{s}os\";"
    "        : button { key = \"isn_k\"; label = \"Koordinat{ee}s i{s}na{s}a\"; }"
    "        : button { key = \"isn_l\"; label = \"Linijos i{s}na{s}a\"; }"
    "      }"
    "      : boxed_column {"
    "        label = \"Redaguoti\";"
    "        : button { key = \"prideti\"; label = \"Prid{ee}ti ta{s}k{a} {i} linij{a}\"; }"
    "        : button { key = \"istrinti\"; label = \"I{s}trinti ta{s}k{a} i{s} linijos\"; }"
    "        : button { key = \"pernum\"; label = \"Pernumeruoti ta{s}kus\"; }"
    "        : text { label = \"Pvz: 1.1 -> 1.1,1.2,..\"; }"
    "      }"
    "    }"
    "  }"
    "  : text { key = \"antraste\"; width = 84; fixed_width_font = true; }"
    "  : list_box { key = \"sarasas\"; height = 16; width = 84; fixed_width_font = true; }"
    "  : text { key = \"info\"; }"
    "  : row {"
    "    : button { key = \"rod_t\"; label = \"Rodyti ta{s}k{a}\"; }"
    "    : button { key = \"rod_l\"; label = \"Rodyti linij{a}\"; }"
    "    : button { key = \"rod_v\"; label = \"Rodyti visk{a}\"; }"
    "    : button { key = \"lentele\"; label = \"{I}terpti lentel{e}\"; }"
    "    : button { key = \"csv\"; label = \"Eksportuoti CSV\"; }"
    "    : button { key = \"cancel\"; label = \"Baigti\"; is_cancel = true; }"
    "  }"
    "}")
)

(defun kz:write-dcl (/ fn f)
  (setq fn (vl-filename-mktemp "kzin.dcl")
        f  (open fn "w"))
  (foreach l (kz:dcl-lines) (write-line (kz:td l) f))
  (close f)
  fn
)

(defun kz:row-str (r)
  (strcat (kz:pad (strcat (nth 6 r) (nth 0 r)) 8)
          (kz:pad (nth 1 r) 12)
          (kz:pad (nth 2 r) 16)
          (kz:pad (nth 3 r) 16)
          (kz:pad (nth 4 r) 12)
          (nth 5 r))
)

(defun kz:fill-dialog (/ rows)
  (set_tile "nr" (kz:get "nr"))
  (set_tile "km" (kz:get "km"))
  (set_tile "aukstis" (kz:fmt (kz:get "aukstis") 2))
  (set_tile "vpoz" (kz:fmt (kz:get "vpoz") 2))
  (set_tile "hpoz" (kz:fmt (kz:get "hpoz") 2))
  (set_tile "dydis" (kz:fmt (kz:get "dydis") 2))
  (set_tile "antraste" (kz:row-str (list "Eil.Nr." (kz:t "Ta{s}ko Nr.") "X" "Y" "Km" "Tipas" "")))
  (setq rows (kz:rows))
  (start_list "sarasas")
  (foreach r rows (add_list (kz:row-str r)))
  (end_list)
  (if (and *kz-sel* (< *kz-sel* (length rows)))
    (set_tile "sarasas" (itoa *kz-sel*))
    (setq *kz-sel* nil)
  )
  (set_tile "info"
            (strcat (kz:t "Ta{s}k{u}: ") (itoa (length rows))
                    (if (kz:dups) (kz:t "   S{a}ra{s}e yra besidubliojanci{u} koordina{c}i{u}.") "")))
)

;; nuskaito laukus; grąžina nil, jei yra tuščių / neteisingų
(defun kz:grab (/ ok v)
  (setq ok T)
  (foreach k '("aukstis" "vpoz" "hpoz" "dydis")
    (setq v (vl-string-trim " " (get_tile k)))
    (if (or (= v "") (and (member k '("aukstis" "dydis")) (<= (kz:num v) 0.0)))
      (setq ok nil)
      (kz:put k (kz:num v))
    )
  )
  (kz:put "nr" (vl-string-trim " " (get_tile "nr")))
  (setq v (vl-string-trim " " (get_tile "km")))
  (kz:put "km" (if (= v "") "0.000" v))
  (if (not ok) (alert (kz:t "Neleistini tu{s}ti laukeliai")))
  ok
)

(defun kz:do (code)
  (cond
    ((= code 10) (kz:riba))
    ((= code 11) (kz:asis))
    ((= code 12) (kz:centras))
    ((= code 13) (kz:trinti-obj))
    ((= code 14) (kz:apply-settings))
    ((= code 20) (kz:isn-koord))
    ((= code 21) (kz:isn-linija))
    ((= code 30) (kz:prideti))
    ((= code 31) (kz:istrinti))
    ((= code 32) (kz:pernumeruoti))
    ((= code 40) (kz:rodyti "taska"))
    ((= code 41) (kz:rodyti "linija"))
    ((= code 42) (kz:rodyti "viska"))
    ((= code 50) (kz:lentele))
    ((= code 51) (kz:csv))
  )
)

(defun c:KZIN (/ *error* doc dcl id code dz)
  (setq doc (vla-get-ActiveDocument (vlax-get-acad-object))
        dz  (getvar "DIMZIN"))
  (defun *error* (msg)
    (setvar "DIMZIN" dz)
    (if id (unload_dialog id))
    (if (and dcl (findfile dcl)) (vl-file-delete dcl))
    (vla-EndUndoMark doc)
    (if (not (wcmatch (strcase msg) "*CANCEL*,*QUIT*,*BREAK*"))
      (princ (strcat "\nKlaida: " msg))
    )
    (princ)
  )
  (setvar "DIMZIN" 0)
  (kz:load-settings)
  (kz:ensure-blocks)
  (setq dcl  (kz:write-dcl)
        id   (load_dialog dcl)
        code 2)
  (while (> code 1)
    (setq *kz-pts* (kz:points))
    (if (not (new_dialog "kzin" id)) (exit))
    (kz:fill-dialog)
    (foreach a '(("riba" . 10) ("asis" . 11) ("centras" . 12) ("trinti" . 13)
                 ("saugoti" . 14) ("isn_k" . 20) ("isn_l" . 21) ("prideti" . 30)
                 ("istrinti" . 31) ("pernum" . 32) ("rod_t" . 40) ("rod_l" . 41)
                 ("rod_v" . 42) ("lentele" . 50) ("csv" . 51))
      (action_tile (car a) (strcat "(if (kz:grab) (done_dialog " (itoa (cdr a)) "))"))
    )
    (action_tile "sarasas" "(setq *kz-sel* (atoi $value))")
    (action_tile "cancel" "(kz:grab) (done_dialog 0)")
    (setq code (start_dialog))
    (if (> code 1)
      (progn
        (vla-StartUndoMark doc)
        (kz:do code)
        (vla-EndUndoMark doc)
      )
    )
  )
  (unload_dialog id)
  (setq id nil)
  (vl-file-delete dcl)
  (kz:save-settings)
  (setvar "DIMZIN" dz)
  (princ)
)

(princ (kz:t "\nKZIN {i}keltas. Komanda: KZIN - Koordina{c}i{u} {z}iniara{s}tis."))
(princ)
