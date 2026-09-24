# S-Log MetaRaw Detail: recupero locale, Texture, Clarity, Dehaze

Il secondo nodo del bundle. Fa quello che un nodo puntuale non può fare: **recuperare luci e
ombre per aree, conservando la texture**. È la parte "alla Lightroom" dei toni. Lavora in luce
lineare: decodifica quello che riceve e lo riscrive nella stessa codifica, cambiando solo un
guadagno per pixel (uguale su R, G e B, quindi la tinta non cambia).

## Dove metterlo, e in che spazio colore

```
S-Log MetaRaw  →  S-Log MetaRaw Detail  →  resto del grade  →  CST / LUT / DRT d'uscita
```

**In e Out sono lo stesso spazio.** Il nodo decodifica in luce lineare quello che riceve e lo
riscrive nella stessa codifica, cambiando solo un guadagno per pixel. Per questo vuole in
ingresso una codifica **log di scena**: S-Gamut3.Cine/S-Log3, S-Gamut3/S-Log3, S-Gamut/S-Log2,
DaVinci WG/Intermediate o ACES AP1/ACEScct (le scelte di Avanzate › Ingresso nodo). Rec.709,
Gamma 2.4 o sRGB non sono fra queste: sono già immagini per il monitor, con le alte luci tagliate
al bianco, e non resta niente da recuperare.

| Configurazione | Nodo principale (Color Space · Gamma) | Detail (Ingresso nodo) | Uscita |
|---|---|---|---|
| **Consigliata**, timeline YRGB non gestita | DaVinci WG · DaVinci Intermediate | **DaVinci WG/Intermediate**, da dichiarare: in una timeline non gestita Automatico non la vede | grade in DWG, poi per ultimo un CST DaVinci WG/Intermediate → Rec.709 · Gamma 2.4 con tone mapping DaVinci |
| Tutto in log | Timeline | Automatico (usa la codifica di camera della clip) | CST S-Gamut3.Cine/S-Log3 → Rec.709 o DWG |
| Progetto color managed (timeline DWG) | Timeline | Automatico (lo spazio lo dice Resolve) | la fa il progetto |
| **Da evitare** | Rec.709 | — | Automatico non sa della conversione e decodifica il Rec.709 come S-Log3 (o come la timeline): il risultato è sbagliato, e le luci sono comunque già tagliate |

- Con un tone mapping dopo (CST con tone mapping, DRT ACES/AgX/DaVinci) porta il **Bianco** a
  4-5 stop, nel nodo principale e nel Detail: 2,5 è il bianco Rec.709 di un CST senza tone mapping.
- Il Rec.709 del nodo principale è un CST senza tone mapping: va bene per un risultato veloce, non
  come base per il Detail né per un grade spinto.
- È **spaziale**: guarda i pixel vicini. Per questo Generate LUT lo esclude, e con lui tutte
  le altre correzioni del suo nodo (manuale di Resolve: gli OFX non compatibili con i LUT
  saltano tutto il nodo). Se esporti LUT, tienilo in un **nodo dedicato**.
- Ingresso **Automatico**: chiede lo spazio colore a Resolve. In una timeline YRGB senza gestione
  del colore Resolve non lo dice: il nodo usa allora la codifica di camera della clip (dal
  record di S-Log MetaRaw), o in mancanza S-Gamut3.Cine/S-Log3 "presunto". La riga in cima dice
  sempre quale ha scelto e perché: se il nodo principale converte, controllala.

## I controlli

| Gruppo | Controllo | Cosa fa |
|---|---|---|
| Gamma dinamica | **Local Contrast** (−100…+50) | contrasto delle grandi aree attorno al grigio, a dettaglio intatto |
| | **Local Highlights** | in negativo comprime le grandi aree luminose con la stessa spalla del nodo principale, ma tiene la texture e la rinforza dove la base è compressa: il cielo si scurisce, le nuvole restano definite. A −100 il massimo registrato arriva sul Bianco di Avanzate. In positivo più stacco per aree |
| | **Local Shadows** | apre (+) o chiude (−) le ombre per aree, 100 = 2 stop |
| | Vista: guadagno | quanto il nodo alza (arancio) o abbassa (blu) ogni zona; grigio = invariato |
| | Vista: base | la base edge-aware su cui lavorano i toni locali, senza dettaglio |
| Presenza | **Texture** | dettaglio fine (pelle, tessuti, foglie); in negativo leviga; la grana sotto la soglia rumore non sale |
| | **Clarity** | contrasto locale a media scala, pesato sui mezzitoni |
| | **Dehaze** | toglie (+) o aggiunge (−) velo; il velo è quello che dichiari in Avanzate › Velo |
| | Azzera dettaglio | riporta a zero tutto il nodo |
| Zone locali | Pivot, Black/Shadow/Light/Specular Exp, Range, Falloff | le stesse zone del nodo principale, applicate alla base |
| Avanzate | Preserva dettaglio (100 %) | 100 = le zone muovono solo le aree; 0 = come il nodo principale |
| | Raggio (4 % dell'altezza) | dimensione delle aree |
| | Soglia bordi (0,5 EV) | salto che conta come bordo, per la base e per Local Highlights: più bassa = meno aloni, meno recupero |
| | Soglia rumore (0,04 EV) | sotto questa ampiezza il dettaglio è rumore: Texture non lo alza |
| | Clarity: centro | il tono dove Clarity lavora di più |
| | Bianco (2,5 stop) | dove Local Highlights −100 porta il massimo registrato; con un DRT dopo, 4–5 |
| Velo | Livello (EV), Colore | luminanza e colore del velo; mai stimati fotogramma per fotogramma |

## Come funziona

1. `L = log2(N/0,18)` della norma di ogni pixel (la stessa del nodo principale).
2. Una **griglia di lavoro** alta fra 382 e 764 righe (riduzione a tenda), con i raggi relativi
   all'altezza: **lo stesso look a piena risoluzione, in proxy e nel viewer**.
3. **Base** B: guided filter auto-guidato di L sulla griglia (He et al.), applicato a piena
   risoluzione a una guida da cui è tolto il rumore a scala di pixel. B segue i bordi forti e
   ignora la grana.
4. **Toni locali**: Local Contrast, Local Shadows e le Zone locali usano la stessa curva a zone
   del nodo principale, applicata a B. Il dettaglio `L − B` passa con pendenza 1: le aree si
   spostano, la texture no. Le aperture svaniscono fra −6,5 e −9,5 stop, così il pavimento del
   rumore resta dov'era.
5. **Local Highlights** separa dettaglio e bordi per ampiezza, come i filtri Laplaciani locali di
   Lightroom. `Dt = lim(L − B)` vale `L − B` fino a 0,7 × Soglia bordi e satura entro
   1,3 × Soglia bordi: oltre, il salto è un bordo e passa per la curva. La spalla del nodo
   principale (qui parte da −0,5 stop) si applica a `X = L − Dt`; dove la base è compressa il
   dettaglio sale di `0,6 · (1 − T′) · Db`, con `Db` limitato a 0,5 × Soglia bordi (sui bordi
   spinge poco) e un cancello che lascia fuori il rumore (3 volte il rumore del codice S-Log3).
   Vicino al massimo registrato la base è il clip del sensore, senza dettaglio: lì la separazione
   sfuma e il pixel segue la curva. Dove comprime, i colori vanno verso il bianco come nel nodo
   principale (Oklab, a tinta costante): una finestra bruciata non diventa una lastra color crema.
   Local Highlights in negativo non schiarisce mai un pixel, e un pixel più chiaro resta sempre
   più chiaro.
6. **Clarity**: differenza di due guided filter (0,5 % e 2,5 % dell'altezza), pesata sui
   mezzitoni.
7. **Texture**: differenza di gaussiane (0,05 % e 0,4 % dell'altezza), con un cancello che
   lascia passare solo ciò che supera il rumore del codice S-Log3 a quella luminanza.
8. Il dettaglio aggiunto è limitato in modo morbido a ±1,5 stop.
9. **Dehaze**: canale scuro morbido rispetto al velo dichiarato, trasmissione raffinata con un
   guided filter congiunto, mai sotto 0,4; sopra il livello del velo non agisce.

Nessuna statistica per fotogramma: niente flicker.

## Limiti dichiarati

- Local Shadows e le Zone locali, a ±100: su un gradino di 1 stop l'alone arriva a circa il 12 %
  del gradino, il 4-6 % su gradini di 2-3 stop; Clarity +100 circa il 7 %.
- Local Highlights −100, Soglia bordi 0,5: sul lato scuro di un bordo l'alone resta sotto il 3 %
  del gradino (0,08 stop su 3 stop). Sul lato chiaro una fascia larga come il raggio viene
  compressa meno del resto: il 39-52 % della compressione su gradini di 2-3 stop, come nella 2.0
  di prova. Con Soglia bordi 0,25 scende al 21-32 %.
- Texture tenuta da Local Highlights −100 su un'area a +4 stop: ×1,3 per dettagli di 0,1-0,3
  stop, ×1,2 a 0,5, ×0,96 a 0,8. Il nodo principale, puntuale, a −100 ne tiene ×0,18.
- Se vedi un alone: abbassa Soglia bordi.
- Vicino ai bordi forti la grana si amplifica di 1,25-1,7 volte con le zone espansive.
- Il nodo non conosce l'EI: le soglie sono ancorate alla codifica S-Log3, e Local Highlights −100
  porta sul Bianco il massimo di un'esposizione all'EI di ripresa (+6 stop). Se nel nodo principale
  cambi molto l'EI, correggi il Bianco del Detail di conseguenza.

## Prestazioni

Su GPU (Metal) un fotogramma UHD costa 6-9 ms con toni, Clarity e zone, 15-18 ms con Texture o
Dehaze (Apple M-series). La CPU è il ripiego e costa diverse decine di millisecondi.

## Verifica

Il modello di riferimento è `tests/model/detail.py`. La pipeline CPU (`src/detail`) lo segue
entro 2e-4 EV su tutti i controlli, ed è bit-identica fra 1 e N thread; il Metal segue la CPU
entro 1e-5.
