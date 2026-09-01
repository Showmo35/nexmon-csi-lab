# Reliable Nexmon CSI collection

**Superseded 2026-08-31.** The previous version of this file described a
method in which the Pi associated to the AP and pinged it. That method was
wrong, and the rates it reported were not measurements. What follows is the
standard configuration and the evidence for it.

## The three roles must live on three different things

| role | device | what it does |
|---|---|---|
| transmitter | TL-WDR4300, fixed channel | puts frames in the air |
| **client** | **a separate device** | associates and generates traffic so the AP transmits |
| receiver | the Pi | monitor mode only, never associates |

This is what nexmon_csi is built for and what the published work uses (e.g.
*Motion Detection using CSI from Raspberry Pi 4*, arXiv:2111.09091). Run it
with `bin/csi-capture`.

## What was wrong before: the Pi was client and receiver at once

`bin/csi-collect` associated the Pi, pinged the AP, and extracted CSI from the
replies. Auditing its own reference captures with `bin/csi-audit` gave the
table below. The script and every capture made with it have since been deleted
(`data/reference/` now holds captures made the correct way); the numbers are
kept here because they are the evidence for the change.

```
reliability_r1.pcap  (deleted)
  frame type    recs distinct     x  real Hz  covers
  QoS Data       661       27 24.5x     54.8      2%
  Beacon         259      259  1.0x      9.6    100%
  BlockAckReq    259      n/a     -     10.0      2%
  Disassoc        10        1 10.0x    342.8      0%
```

661 QoS Data **records** carrying **27 distinct sequence numbers**, all inside
a 0.49 s window of a 26.9 s capture. The channel was sampled 27 times. The
reported "44 Hz" was `total records / total seconds`, which is not a sampling
rate. An 82 s activity capture was worse: 929 records, 25 distinct
transmissions, a real rate of **0.3 Hz** — against hand motion at 1-3 Hz that
it was supposed to measure.

The `BlockAckReq` and `Disassoc` frames name the mechanism. With CSI
extraction armed the Pi stops acknowledging reliably; the AP retransmits each
frame many times and finally drops the client. **A retransmission reuses its
sequence number**, so those repeats are the AP shouting the same frame, not
the channel being measured again.

Everything the old file attributed to firmware quirks follows from this:

- "data-frame CSI arrives as a ~0.5 s burst then stops" — that is the
  association collapsing, not nexmon_csi #177.
- "the extractor emits a quota of ~900 records at ~40 per ping" — that is
  ~40 retransmissions per ping.
- the fixed, trial-derived ordering (associate first, apply params once,
  never re-apply) — all of it existed to keep an association alive that
  should not have been there.

None of it survives once the Pi only receives. `bin/csi-sniff` has no
ordering constraints because there is no association to destabilise.

## The second problem: the Pi is 1x1 and cannot decode 2-stream frames

With the Pi correctly receive-only, a 200 Hz ping from this PC still produced
almost nothing:

```
--traffic ping     56 QoS Data records ->   1.9 Hz
```

The AP was not the bottleneck — it answered **763 of 763 pings, 152
packets/s, 0% loss**. The receiver was. `iwconfig` during the capture:

```
AP -> client link: 144.4 Mb/s      = HT20 MCS15, TWO spatial streams
```

This PC is a 2x2 client, so the AP rate-adapts up to two spatial streams. A
1x1 receiver cannot decode those, so they yield no CSI even though the link is
perfect. Beacons kept arriving at full rate throughout because beacons are
single-stream at a basic rate.

Raising the core/stream masks does not help — `-C 7 -N 7` moved it from 1.9 to
2.9 Hz. The frames are undecodable, not mis-slotted.

### The fix: make the AP transmit single-stream

Two ways. The **router setting is the right one**: `Wireless Network Mode =
A-Only` on `ath1` forces legacy single-stream OFDM for *all* traffic, so
ordinary unicast works and the receiver constraint disappears entirely.

Before that was found, the workaround was `--traffic bcast` — UDP broadcast,
which the AP re-transmits into the BSS at a basic rate on one stream. It
delivers frames at a similar rate but **not at a usable cadence**:

```
  frame type    recs distinct     x  real Hz  covers
  Data          3156     3156  1.0x    166.3    100%
  Beacon         173      173  1.0x      9.2     99%
  sound: one transmitter, one record per transmission, full coverage
```

**166 Hz, 1.0x inflation** — but an AP buffers broadcast until a DTIM beacon
and then sends the batch back to back:

| | median gap | spacing | time in gaps >50 ms |
|---|---|---|---|
| `--traffic bcast` | 0.2 ms | ~37 frames in 19 ms, then ~186 ms of nothing | 88 % |
| **`--traffic ping`** | **5.0 ms** | **even (p25 4.9, p75 5.0, p90 5.1)** | **29 %** |

Those 37 frames are 37 looks at the *same* channel instant — a channel cannot
change in 19 ms — so broadcast's effective sampling rate is the batch rate,
**~5 Hz**, whatever the frame count says. That is why published work reporting
30 Hz+ uses unicast: an echo reply is never buffered, so every frame is its
own measurement.

**With `A-Only` set, use `--traffic ping`.** It is the default.

Three consecutive runs of the final method, 20 s each, now in
`data/reference/` (with `.png` overviews from `bin/csi-plot`):

| capture | records | distinct | inflation | real Hz | dead | per-SC std |
|---|---|---|---|---|---|---|
| `reference_r1.pcap` | 3792 | 3791 | 1.0x | 199.8 | 0 % | 1.12 dB |
| `reference_r2.pcap` | 3776 | 3776 | 1.0x | 198.9 | 0 % | 2.56 dB |
| `reference_r3.pcap` | 3750 | 3749 | 1.0x | 197.5 | 0 % | 2.87 dB |

199.8 of 200 offered pings per second arrive as CSI — the stream is
continuous, not merely fast.

Unicast QoS Data, evenly spaced at a 5 ms cadence, single source, chanspec
`0xd0a1` (channel 161). `bin/csi-regress` pins them.

For scale, where this started: 0.3 Hz of real measurements, 37x duplication,
4.26 dB per-subcarrier variation.

## Usage

```bash
bin/csi-capture out.pcap 30              # 30 s, broadcast traffic, ~166 Hz
bin/csi-capture out.pcap 30 --rate 400   # offer more load
bin/csi-capture out.pcap 30 --client none    # an external client is running
bin/csi-audit out.pcap --hz 30           # ALWAYS check what you got
```

`--client self` (the default) borrows this PC's single Wi-Fi radio, so eduroam
drops for the length of the capture and is restored on every exit path,
including Ctrl-C and errors. The Pi is armed before the Wi-Fi is touched, so
the outage is the capture length plus a few seconds. The Pi link is Ethernet
and is unaffected.

## The third problem: the router was cycling its transmit antennas

With rate solved, a ~5 dB per-subcarrier variation remained, and it was NOT
the environment. Splitting it:

```
per-SC std total  4.94 dB
per-packet level  1.55 dB     <- common-mode, AGC-like
shape-only        4.72 dB     <- the frequency response itself
```

The channel's *shape* was changing, with a median dwell of 1-2 frames, between
a handful of responses whose means differed by up to 20 dB. That is a
transmitter alternating antennas, and the router's DD-WRT default
**TX Antenna Chains = 1+2+3** was doing exactly that. Consecutive frames left
by different antennas and presented a different channel to the Pi.

Setting **TX Antenna Chains = 1** and **Wireless Network Mode = A-Only** on
`ath1` (see `21-tl-wdr4300.md`):

| | 3 chains, HT | **1 chain, A-Only** |
|---|---|---|
| per-SC std | 4.94 dB | **1.82 dB** |
| shape-only std | 4.72 dB | **1.55 dB** |
| adjacent-SC corr | +0.942 | +0.976 |
| **5-apart SC corr** | **+0.277** | **+0.857** |

A 5-apart correlation of +0.86 across 3200 distinct frames is a smooth,
physically sensible frequency response — the thing every earlier version of
this document was chasing and never had.

This also settles the old "beacons are 10x worse than data frames" claim: it
was never a frame-type effect. Beacons and broadcast data behaved identically
because both were subject to the same antenna cycling, and the "good" 0.45 dB
data-frame figure came from 27 frames inside a 0.49 s window.

## What remains: arrival is bursty, not uneven quality

The AP buffers broadcast until a DTIM beacon and then sends the batch back to
back, so frames arrive in ~12 bursts/s of ~15 frames rather than evenly.
DTIM Interval is set to 1 to keep that period at one beacon interval.

For a quasi-static measurement this is irrelevant — 3200 distinct frames with
a smooth CFR is what matters. For motion sensing the effective sampling rate
is the burst rate (~12 Hz), not 180 Hz.

A further 10-17% of the timeline is genuinely dead, in gaps over 250 ms. That
is **this PC** pausing transmission to background-scan while acting as the
client; the Pi is fine, and receives 92% of the AP's beacons through those
windows. A dedicated client would remove it — see below.

## Keep every other client off the AP

This costs more than anything else on this page. An associated phone, idle,
on a network with no internet, does not sit quiet: it retries connectivity
checks and probes constantly, and the AP has to service it. Measured, same
settings, with and without one phone associated:

| | interruptions >20 ms | time lost | delivered |
|---|---|---|---|
| phone associated | 142 (2.1/s) | **31 %** | 352 Hz |
| nothing else on the AP | 1 (0.05/s) | **0 %** | 476 Hz |

It does not show up as duplication, missing coverage or dead time — the
capture looks sound by every other measure. `bin/csi-audit` now checks for it
directly and reports "stream is chopped up".

Before a run that matters: forget the network on every phone and laptop that
has ever joined it, and confirm with `bin/csi-sniff probe.pcap 8 -b any`,
which lists every transmitter on the channel. You want to see the router and
nothing else.

## The rate ceiling

`ping -i` clamps below 5 ms, which is not obvious from its output:

| requested | actual |
|---|---|
| `-i 0.0050` | 200/s exactly |
| `-i 0.0029` | **482/s** — clamped to the floor |
| `-i 0.0020` | 483/s |

So `--rate` behaves as asked at 200 and below, and anything above ~200 lands
at ~483/s. That is the non-root ceiling and yields **~480 Hz of CSI**
(Nyquist ~240 Hz), measured at 1.0x with no interruptions.

## Still open

- **A 1x1 client for unicast.** A phone or USB dongle pinging the AP gives
  single-stream *unicast* QoS Data: no DTIM buffering, evenly spaced, and no
  background-scan gaps. Attempted 2026-08-31 with a phone; the phone
  associated and was measured transmitting, but at exactly 1.0 Hz — unrooted
  `ping` will not go below 200 ms and iOS ping apps cap at 1 s. Unresolved for
  lack of a client that can be driven fast, not for any technical reason.
- **The residual 1.55 dB of shape variation.** Plausibly real room motion, but
  not yet separated from AGC gain-stepping.

## What still holds from the old analysis

- The 20 MHz null subcarriers and `csitools.subcarrier_axis()`.
- The nexcsi decoder and the real/imag fix (`docs/11-validation.md`).
- AGC operates before CSI is delivered (nexmon_csi #93, #196).
- The Pi is 1x1, so `-N 7` returns three copies of one estimate
  (nexmon_csi #152) — now confirmed a second way, since 2-stream frames from
  the AP are undecodable rather than merely mis-slotted.

## Consequence for the water task

The water-impurity baselines were collected with the old method. **Re-collect
them.** Any noise floor derived from those captures was computed over 25-27
real measurements, most of a capture's records being retransmissions.
