# What went wrong, and how it was found

A record of the diagnostic path, kept because the dead ends are as useful as
the answer. **Several conclusions reached along the way were wrong and were
later overturned by measurement.** They are kept here, marked, rather than
quietly deleted — the pattern of how they were wrong is the useful part.

## The symptom

In a static room, a single subcarrier's |CSI| wandered by ~4 dB, with sudden
level steps correlated across subcarriers. A static environment should give a
static magnitude.

## Hypotheses tested and rejected

| # | Hypothesis | Test | Verdict |
|---|---|---|---|
| 1 | AGC common-mode gain | variance explained by per-packet mean | **rejected on beacons** — R² = 0.082, removing it cut std 2.9 % |
| 2 | Measurement noise | lag-1 autocorrelation | **rejected** — +0.85; consecutive beacons agree to 0.25 dB |
| 3 | A fan in the room | captured fan on vs off | **rejected** — 3.80 vs 3.89 dB |
| 4 | Phase / timing drift | correlation with CFR derivative | **rejected** — \|corr\| 0.10; a phase rotation cannot change \|H\| at all |
| 5 | Transmit-antenna diversity | per-stream std with `-N 7` | rejected — but the **test was invalid and the hypothesis was correct**; see below |
| 6 | Low-pass filtering would fix it | PSD of the fluctuation | **rejected** — 73 % of energy below 0.5 Hz; a 2 Hz low-pass bought 3 % |

## The answer that was wrong: frame type

The conclusion drawn at the time was that beacons are ~10x more variable than
data frames (4.26 dB vs 0.45 dB per-subcarrier std), and that every earlier
anomaly followed from having captured beacons.

**It does not hold.** The comparison was not like-for-like. Those "0.45 dB
data frames" were 27 real transmissions inside a 0.49 s window, each reported
~24 times by the extractor — half a second of a static channel is stable by
construction. Measured properly, over a full capture with the Pi
receive-only, broadcast data frames and beacons are indistinguishable:

| source | n | per-SC std | adj-SC corr |
|---|---|---|---|
| broadcast Data @166 Hz | 3156 | 5.00 dB | +0.923 |
| beacons, same capture | 173 | 5.04 dB | +0.919 |

## The answer that holds: the collection method

The Pi was acting as both the AP's client and the CSI receiver. With CSI
extraction armed it stopped acknowledging reliably, so the AP retransmitted
each frame many times — a retry reuses its sequence number — and eventually
disassociated it. The captures contain the evidence directly, as
`BlockAckReq` and `Disassoc` frames.

So the "data frames" being compared against beacons were mostly the AP
shouting the same 27 frames, and the reported rates were record counts rather
than measurements. See `10-collection-method.md` for the fix and the numbers.

Two things previously filed as firmware quirks are explained by this and are
no longer open:

- "Data-frame CSI arrives as a ~0.5 s burst then stops" — the association
  collapsing, not nexmon_csi issue #177.
- "Arrivals are bursty, ~39 clusters of ~11 frames" — retry bursts.

## Wrong turns worth recording

- **Predicted the fan was the cause. It was not** — fan off changed nothing.
- **Claimed transmit-antenna selection explained it**, from k-means finding 3
  discrete states with 1.43 s dwell. The per-stream test contradicted it.
- **Reported "44 Hz sustained" collection.** It was total records over total
  time, mixing a 0.5 s burst of data frames with 27 s of beacons.
- **Briefly diagnosed record duplication** from 39 % identical consecutive
  vectors, then dismissed it as an artifact of pooling three stream slots.
  Duplication was real and much larger; dismissing it cost months of analysis
  built on 27 measurements.
- **Computed a 0.94 MHz coherence bandwidth** implying a 320 m delay spread
  and treated it as a real anomaly.
- **Concluded "beacons are unusable, use data frames"** — see above.

The common thread: every one of these was a physical explanation invented for
an artifact of the measurement, and each survived because nothing counted how
many independent measurements a capture actually held. `bin/csi-audit` now
does, and `bin/csi-checkup` fails on it.

## The third cause, found from a plot: transmit antenna cycling

Plotting a capture with `bin/csi-plot` showed individual subcarriers sitting
on flat plateaus and jumping between them in square steps, dwelling 1-2
frames. Splitting the variance showed it was not a level effect:

```
per-SC std total  4.94 dB
per-packet level  1.55 dB     <- common-mode, AGC-like
shape-only        4.72 dB     <- the frequency response itself
```

Clustering the per-frame responses gave cluster means differing by up to 20 dB
across subcarriers. The router's DD-WRT default is **TX Antenna Chains =
1+2+3**: consecutive frames left by different antennas, each presenting a
different channel. Setting it to **1** (with Wireless Network Mode = A-Only)
took the shape variation from 4.72 dB to 1.55 dB and the 5-apart subcarrier
correlation from +0.277 to **+0.857**.

Note what this means for hypothesis 5 above: transmit-antenna diversity was
**right**, and was rejected on a bad test. `-N 7` is a *receive*-side stream
mask and cannot observe transmit-side antenna selection.

The plot found in one look what months of summary statistics had missed. That
is the lesson worth keeping from this whole file.

## Hardware limits established

- **The Pi is 1x1.** Per the nexmon maintainer in
  [issue #152](https://github.com/seemoo-lab/nexmon_csi/issues/152), "core"
  means antenna, so `-N 7` returns three copies of one estimate. Confirmed a
  second way: frames the AP sends with **two spatial streams cannot be
  decoded at all** and yield no CSI. A 2x2 client will rate-adapt into that
  region and leave the capture nearly empty of data frames — measured, 1.9 Hz
  against a 200 Hz offered load while the AP answered 763 of 763 pings.
- **AGC runs before CSI is delivered** —
  [#93](https://github.com/seemoo-lab/nexmon_csi/issues/93),
  [#196](https://github.com/seemoo-lab/nexmon_csi/issues/196).
  [#125](https://github.com/seemoo-lab/nexmon_csi/issues/125) asks for direct
  AGC access and is unresolved.

## Still open

- **The residual ~1.55 dB of shape variation.** Plausibly real room motion,
  but not yet separated from AGC gain-stepping. (The ~5 dB that stood here
  before was **resolved**: it was the router cycling its three transmit
  antennas. See below.)
- **Whether RSSI rescaling helps.** It measured 28 % *worse* than raw, but that
  was on the 27-measurement captures and should be re-tested.
- **Subcarrier sign inversion** —
  [#100](https://github.com/seemoo-lab/nexmon_csi/issues/100), unresolved
  upstream; users treat inversions as outliers.
