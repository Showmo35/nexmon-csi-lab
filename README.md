# csitools — Nexmon CSI on the Raspberry Pi 4B

A working rig for collecting Wi-Fi Channel State Information with
[nexmon_csi](https://github.com/seemoo-lab/nexmon_csi) on a Raspberry Pi 4B,
plus the tooling that makes the results trustworthy.

**Decoding is delegated to [nexcsi](https://github.com/nexmonster/nexcsi)**,
vendored unmodified in `vendor/`. Nothing here reimplements pcap parsing or
CSI decoding — see `docs/11-validation.md`.

## Quickstart

```bash
bin/csi-checkup                  # full rig + CSI health check, run this first
bin/csi-capture out.pcap 30      # collect 30 s  (~200 Hz, see below)
bin/csi-audit out.pcap --hz 100  # what did you ACTUALLY get?
bin/csi-plot out.pcap            # |H| over time, mean CFR, one subcarrier

bin/csi-record runs/ wave -p 10:10x3   # timed activity run with cues + plots
bin/csi-regress                        # decode pipeline vs data/reference/
```

```python
import sys; sys.path.insert(0, "/path/to/this/repo")
import csitools, numpy as np

ts, csi, rssi, macs = csitools.load("out.pcap")   # one frame type, beacons dropped
idx, sc = csitools.subcarrier_axis()              # 55 usable subcarriers
db = 20*np.log10(np.abs(csi[:, idx]))
db = csitools.normalize_per_packet(db)            # remove AGC
db = csitools.despike(db)                         # nexmon_csi #100 outliers
```

The tools resolve their own location, so they work from any directory.

## Record count is not sampling rate

**This is the one thing to take away.** A nexmon_csi pcap is a stream of CSI
*records*, not measurements. A retransmission reuses its 802.11 sequence
number, so the extractor reports the same transmission again, and counting
records can overstate the rate by 37x.

Run `bin/csi-audit` on every capture. It counts **distinct transmissions**:

```
  frame type    recs distinct     x  real Hz  covers   dead
  QoS Data      3792     3791  1.0x    199.8    100%     0%
  sound: one transmitter, one record per transmission, full coverage
```

`x` is the inflation factor — anything above ~1.0 means the records are not
independent samples. It also reports dead time, arrival clustering, and
whether the stream is chopped up by a competing client. Non-zero exit on
problems, so it can gate a script.

An earlier version of this rig had the Pi acting as both the AP's client and
the CSI receiver, and reported "44 Hz" from captures whose data frames were 27
real transmissions repeated ~24x inside half a second.

## The four rules

All measured, all in `docs/10-collection-method.md`:

1. **Three roles, three devices.** The AP transmits, a *separate* client
   drives it, and the Pi only listens in monitor mode. The Pi must never be
   the client — with CSI extraction armed it stops acknowledging, the AP
   retransmits each frame dozens of times, and the capture fills with
   duplicates and `Disassoc` frames.
2. **Pin the router to one transmit antenna chain.** DD-WRT's default
   `TX Antenna Chains = 1+2+3` cycles antennas per frame, so consecutive
   frames present a *different channel*. Setting it to `1` took the
   frequency-response shape variation from 4.72 dB to 1.55 dB and the
   5-apart subcarrier correlation from +0.28 to **+0.86**.
3. **Force single-stream (`Wireless Network Mode = A-Only`).** The Pi is 1×1
   and cannot decode a 2-stream transmission at all, so a 2×2 client leaves
   the capture nearly empty of data frames — 1.9 Hz against a 200 Hz ping,
   while the link itself was perfect.
4. **Keep every other client off the AP.** One idle phone, associated to a
   network with no internet, cost 31 % of the timeline in 20–250 ms
   interruptions while every other metric still read clean.

## Measured performance

Three consecutive 20 s runs, in `data/reference/` and pinned by
`bin/csi-regress`:

| capture | records | distinct | inflation | real Hz | dead | per-SC std |
|---|---|---|---|---|---|---|
| `reference_r1` | 3792 | 3791 | 1.0x | 199.8 | 0 % | 1.12 dB |
| `reference_r2` | 3776 | 3776 | 1.0x | 198.9 | 0 % | 2.56 dB |
| `reference_r3` | 3750 | 3749 | 1.0x | 197.5 | 0 % | 2.87 dB |

199.8 of 200 offered pings per second arrive as CSI, evenly spaced at a 5 ms
cadence. The ceiling without root is ~483 pings/s (`ping -i` clamps at a 2 ms
floor), giving ~480 Hz and a Nyquist of ~240 Hz.

## Known limitations — NOT fixable in this toolkit

1. **The Pi is 1×1.** `-N 7` returns three copies of ONE spatial stream, and
   frames the AP sends with two spatial streams cannot be decoded at all.
   Rule 3 above is the workaround.
2. **Subcarrier sign inversion**
   ([#100](https://github.com/seemoo-lab/nexmon_csi/issues/100)), unresolved
   upstream: 1.2 % of samples, touching 21 % of frames. Impulses are
   broadband and wreck spectral work — `csitools.despike()` removes them.
3. **Absolute level is not trustworthy** — CSI is delivered post-AGC and the
   AGC restages even at fixed distance
   ([#93](https://github.com/seemoo-lab/nexmon_csi/issues/93),
   [#196](https://github.com/seemoo-lab/nexmon_csi/issues/196)). Use the CFR
   *shape*, not the level.

## Two claims this project got wrong, and retracted

Both were believed, documented, and acted on before measurement overturned
them. `docs/12-findings.md` keeps the full diagnostic path, dead ends included.

- **"Data-frame CSI arrives as a ~0.5 s burst then stops (nexmon_csi #177)."**
  It was the Pi's own association collapsing, not a firmware quirk.
- **"Beacons are ~10× more variable than data frames (4.26 vs 0.45 dB)."**
  Not a like-for-like comparison — the 0.45 dB came from 27 real
  transmissions inside a 0.49 s window. Beacons and broadcast data behaved
  identically; the real cause of both was antenna cycling (rule 2).

## Layout

```
csitools/         the package — io.py (nexcsi wrapper), clean.py, audit.py
bin/              csi-capture (collect), csi-record (timed activity runs),
                  csi-sniff (Pi side), csi-audit, csi-regress, csi-checkup,
                  csi-plot, csi-plot-activity, csi-plot-streams,
                  restore-pc-network
vendor/nexcsi/    nexcsi 0.5.2, unmodified
data/reference/   three captures + expected.json, the regression set
docs/             rig setup (01-06), method + validation + findings (10-13),
                  RF transmitters (20-22)
config/           cloud-init files as flashed and as corrected
```

Per-application work (`projects/`) is deliberately not published.

## Docs

| | |
|---|---|
| `docs/10-collection-method.md` | **how to collect correctly** — read first |
| `docs/11-validation.md` | decoder checked against nexcsi and CSIKit |
| `docs/12-findings.md` | the diagnostic path, including the wrong turns |
| `docs/13-tools.md` | what each tool checks and how to read it |
| `docs/01-06` | Pi provisioning, network, firmware install, troubleshooting |
| `docs/20-22` | lab router inventory and configuration |

## Rig

Three roles, on three devices:

- **transmitter** TL-WDR4300 on DD-WRT, `nexmon-lab-5g`, ch161 fixed,
  A-Only, one TX antenna chain
- **client** drives the transmitter so it has something to send. Currently
  the host PC's Wi-Fi, borrowed for the length of a capture; a dedicated 1×1
  client would avoid the brief loss of internet.
- **receiver** Pi 4B, monitor mode only, on a direct Ethernet cable
  (`10.0.0.100` ← `10.0.0.250`) NAT'd to the internet through the PC

Details in `docs/02-network-topology.md`, `docs/21-tl-wdr4300.md` and
`docs/10-collection-method.md`.

## Security notes

- Password hashes are redacted from everything in `config/`; only SSH
  **public** keys are present.
- The Pi has passwordless sudo (`/etc/sudoers.d/010_nexmon-nopasswd`), enabled
  for unattended builds. Anyone holding the SSH key therefore has root.
  Remove with `sudo rm /etc/sudoers.d/010_nexmon-nopasswd`.
- `~/.ssh/pi4b_nexmon` has no passphrase and is not in this repo.
