# Host-side scripts

Everything in `bin/`. Run them from the repo root.

| Script | Purpose |
|---|---|
| `csi-checkup` | **Full rig + CSI health check.** Run this first, always. |
| `csi-capture` | Collect CSI: router transmits, a client drives it, the Pi listens |
| `csi-record` | Timed activity/motion run with on-screen cues, metadata and a plot |
| `csi-audit` | What a capture ACTUALLY contains — records vs real measurements |
| `csi-plot` | Overview of one capture: |H| over time, mean CFR, single subcarriers |
| `csi-regress` | Regression check of the decode pipeline against `data/reference/` |
| `csi-sniff` | Pi-side receiver only; `csi-capture` calls it, use it directly for an external client |
| `csi-plot-activity` | Amplitude + spectrogram with activity windows shaded |
| `csi-plot-streams` | Per-stream amplitude plot |
| `restore-pc-network` | Revert this PC's wired link from NAT/shared back to plain static |

## csi-audit — run this on every capture

A nexmon_csi pcap is a stream of CSI *records*, not measurements. A
retransmission reuses its 802.11 sequence number, so the extractor reports the
same transmission again; counting records overstates the sampling rate,
sometimes by 37x. `csi-audit` counts distinct sequence numbers instead:

```bash
bin/csi-audit capture.pcap --hz 30
```

```
  frame type    recs distinct     x  real Hz  covers
  Data          3347     3347  1.0x    177.8     99%
  Beacon         171      171  1.0x      9.0    100%
  sound: one transmitter, one record per transmission, full coverage
```

`x` is the inflation factor; anything above ~1.0 means the records are not
independent samples. `covers` is how much of the capture that frame type
spans — well under 100 % means the source stopped or the extractor stalled.
Exit status is non-zero when a capture has problems, so it can gate a script.

Control frames (BlockAck, ACK, RTS/CTS) carry no sequence number and are
reported as `n/a` rather than given a meaningless inflation figure.

## csi-plot

```bash
bin/csi-plot capture.pcap -o out.png [--normalize] [--trace -21,-7,7,21]
```

Three panels: `|H|` over time × subcarrier, the mean channel frequency
response with ±1σ, and a few individual subcarriers over time.

Two things it deliberately does not hide:

- **Real gaps are painted beige**, not interpolated across and not left to
  blend into the light end of the colour ramp. A solid block of colour where
  nothing was received is a lie the eye cannot catch.
- **The bottom panel is per-frame**, so discrete level switching shows up as
  the square steps it is rather than being averaged into a smooth line.

## csi-record / csi-plot-activity

`csi-record` runs a timed activity experiment with on-screen cues and writes
`<label>.pcap`, `.json`, `.png` and `-overlay.png`.

Its motion metric is a **1-8 Hz band-pass envelope**, not frame-to-frame
differencing. At ~160 Hz adjacent frames are 6 ms apart, so a difference is
mostly measurement noise while hand motion lives at 1-3 Hz. Measured on the
wave/still test, median energy in the waving windows over the still windows:

| metric | separation |
|---|---|
| frame-to-frame difference | 1.9x |
| **1-8 Hz band-pass envelope** | **9.0x** |

Expect motion to run 1-2 s past the end of each cued window — that is human
reaction time, not a timing fault.

## csi-checkup

```bash
bin/csi-checkup            # full, includes a live 15 s CSI capture
bin/csi-checkup --quick    # skip the capture (and the Wi-Fi outage)
```

Six stages: physical link → PC addressing + NAT → Pi reachable → Pi firmware
and tools → router broadcasting → live CSI capture with quality metrics.

The full run borrows this PC's Wi-Fi for the capture, so eduroam drops for
~20 s and is restored automatically. `--quick` avoids that.

### Reading the CSI quality metrics

The design point: **it separates rig faults from the environment.**

| metric | good | meaning if bad |
|---|---|---|
| single source | 1 MAC | MAC filter not working; other transmitters leaking in |
| inflation | **~1.0x** | above 1.5x: records are repeats, not measurements |
| real rate | **>100 Hz** | reference 169–180 Hz; low means the client is not driving the AP, or the AP is sending frames the 1x1 Pi cannot decode |
| coverage | **~100 %** | the source stopped, or extraction stalled mid-capture |
| dead | **<5 %** | fraction of the timeline in gaps over 250 ms |
| chopped up | **absent** | interruptions of 20-250 ms. A competing client on the AP produced 2.1/s of these, losing 31 % of the timeline, while every other metric stayed clean |
| adjacent-SC corr | **>0.7** | below: not smooth in frequency — suspect frame-type mixing |
| 0.5 s autocorr | **<0.3** | **above means SOMETHING IS MOVING near the path** |

**A high 0.5 s autocorrelation is not a fault.** It is the correct measurement
of a non-static room. Stand clear and re-run before concluding anything is
broken.

Note the motion test uses a fixed **time** lag, not a fixed sample lag. At
166 Hz consecutive samples are 6 ms apart and a genuinely static channel is
still ~+0.9 correlated there; a sample-lag test would flag every good capture.
A quiet room decorrelates by roughly 200 ms.

### What it cannot check

- Whether the jug/sample is positioned correctly (no way to sense that)
- Whether anything is moving in the room *during* your experiment rather than
  during the 15 s health check
