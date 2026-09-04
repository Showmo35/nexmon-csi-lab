# csitools — Nexmon CSI on the Raspberry Pi 4B

Tooling and a documented rig for collecting Wi-Fi Channel State Information
with [nexmon_csi](https://github.com/seemoo-lab/nexmon_csi) on a Raspberry
Pi 4B, with verification built into the collection path.

Sustained output on the reference rig: **~200 Hz of independent CSI
measurements**, evenly spaced at a 5 ms cadence, one record per transmission,
zero dead time.

CSI decoding is delegated to [nexcsi](https://github.com/nexmonster/nexcsi),
vendored unmodified under `vendor/`. Nothing here reimplements pcap parsing or
CSI decoding; see `docs/11-validation.md` for the validation.

## Requirements

- Raspberry Pi 4B (BCM43455c0) with the nexmon_csi firmware patch installed —
  `docs/05-nexmon-csi-install.md` documents the build
- An 802.11 access point on a fixed channel, and a client device to drive it
- A host machine with Python 3, NumPy, SciPy and Matplotlib, reaching the Pi
  over SSH

## Usage

```bash
bin/csi-checkup                  # rig + CSI health check; run this first
bin/csi-capture out.pcap 30      # collect 30 s
bin/csi-audit out.pcap --hz 100  # verify the capture before trusting it
bin/csi-plot out.pcap            # |H| over time, mean CFR, one subcarrier

bin/csi-record runs/ wave -p 10:10x3   # timed activity run with cues + plots
bin/csi-regress                        # check the decode pipeline
```

```python
import sys; sys.path.insert(0, "/path/to/this/repo")
import csitools, numpy as np

ts, csi, rssi, macs = csitools.load("out.pcap")   # one frame type, beacons dropped
idx, sc = csitools.subcarrier_axis()              # 55 usable subcarriers
db = 20*np.log10(np.abs(csi[:, idx]))
db = csitools.normalize_per_packet(db)            # remove AGC
db = csitools.despike(db)                         # remove #100 outliers
```

The tools resolve their own location and run from any directory.

## Verification: record count is not sampling rate

A nexmon_csi pcap is a stream of CSI *records*, not measurements. A
retransmission reuses its 802.11 sequence number, so the extractor reports the
same transmission again. Counting records can therefore overstate the sampling
rate by a large factor — a documented failure mode on this hardware produced
929 records from 25 distinct transmissions, a 37× overstatement, in a capture
that looked healthy by frame count alone.

`bin/csi-audit` counts distinct transmissions and reports the arrival
structure:

```
  frame type    recs distinct     x  real Hz  covers   dead
  QoS Data      3792     3791  1.0x    199.8    100%     0%
  sound: one transmitter, one record per transmission, full coverage
```

`x` is the inflation factor; above ~1.0 the records are not independent
samples. The tool also reports dead time, arrival clustering (an AP batches
buffered broadcast at each DTIM beacon, so a high frame rate can hide a low
effective one), and interruption by competing clients. It exits non-zero on
problems so it can gate a pipeline. `bin/csi-checkup` applies the same checks
to a live capture.

## Collection requirements

Four conditions, each established by measurement on this rig and documented
with the supporting data in `docs/10-collection-method.md`.

**1. Separate the three roles.** The AP transmits, a separate client generates
traffic, and the Pi receives in monitor mode only. The Pi must not also be the
client: with CSI extraction armed it stops acknowledging reliably, so the AP
retransmits each frame repeatedly and the capture fills with duplicates.

**2. Pin the transmitter to one antenna chain.** A multi-chain AP alternates
transmit antennas between frames, so consecutive frames measure a *different*
channel. On DD-WRT, setting `TX Antenna Chains = 1` reduced frequency-response
shape variation from 4.72 dB to 1.55 dB and raised the 5-apart subcarrier
correlation from +0.28 to +0.86.

**3. Force single-stream transmission.** The Pi is 1×1 and cannot decode a
two-spatial-stream frame, so a 2×2 client causes the AP to rate-adapt out of
range: 1.9 Hz of usable CSI against a 200 Hz offered load, with the link
otherwise healthy. `Wireless Network Mode = A-Only` constrains all traffic to
legacy single-stream OFDM.

**4. Exclude other clients from the AP.** A single idle associated device cost
31 % of the timeline in 20–250 ms interruptions, while inflation, coverage and
dead time all still read clean.

## Reference measurements

Three consecutive 20 s captures, included in `data/reference/` and pinned by
`bin/csi-regress`:

| capture | records | distinct | inflation | rate | dead | per-SC std |
|---|---|---|---|---|---|---|
| `reference_r1` | 3792 | 3791 | 1.0× | 199.8 Hz | 0 % | 1.12 dB |
| `reference_r2` | 3776 | 3776 | 1.0× | 198.9 Hz | 0 % | 2.56 dB |
| `reference_r3` | 3750 | 3749 | 1.0× | 197.5 Hz | 0 % | 2.87 dB |

199.8 of 200 offered pings per second arrive as CSI. The ceiling without root
privileges is ~483 pings/s, since `ping -i` clamps to a 2 ms floor, giving
~480 Hz and a Nyquist limit of ~240 Hz.

## Hardware limitations

Properties of the receiver and firmware, not of this toolkit:

1. **The Pi is 1×1.** `-N 7` returns three copies of a single spatial stream,
   and two-stream frames cannot be decoded at all. See requirement 3 above.
2. **Subcarrier sign inversion**
   ([nexmon_csi #100](https://github.com/seemoo-lab/nexmon_csi/issues/100),
   unresolved): 1.2 % of samples, affecting 21 % of frames. The impulses are
   broadband and disrupt spectral analysis; `csitools.despike()` removes them.
3. **Absolute level is unreliable.** CSI is delivered post-AGC and the AGC
   restages at fixed distance
   ([#93](https://github.com/seemoo-lab/nexmon_csi/issues/93),
   [#196](https://github.com/seemoo-lab/nexmon_csi/issues/196)). Use the
   channel frequency response shape rather than its level.

## Repository layout

```
csitools/         package — io.py (nexcsi wrapper), clean.py, audit.py
bin/              csi-capture, csi-record, csi-sniff, csi-audit, csi-regress,
                  csi-checkup, csi-plot, csi-plot-activity, csi-plot-streams,
                  restore-pc-network
data/reference/   three captures + expected.json, the regression set
docs/             rig build (01-06), method and findings (10-13),
                  RF transmitters (20-22)
config/           cloud-init files as flashed and as corrected
vendor/nexcsi/    nexcsi 0.5.2, unmodified
```

## Documentation

| | |
|---|---|
| `docs/10-collection-method.md` | collection method and the measurements behind it |
| `docs/11-validation.md` | decoder validated against nexcsi and CSIKit |
| `docs/12-findings.md` | diagnostic record, including hypotheses that failed |
| `docs/13-tools.md` | what each tool checks and how to read its output |
| `docs/01-06` | Pi provisioning, networking, firmware build, troubleshooting |
| `docs/20-22` | RF transmitter inventory and configuration |

## Reference rig

- **Transmitter** TP-Link TL-WDR4300 on DD-WRT, `nexmon-lab-5g`, channel 161
  fixed, A-Only, one TX antenna chain
- **Client** the host PC's Wi-Fi interface, associated for the duration of a
  capture; a dedicated 1×1 client avoids interrupting the host's connectivity
- **Receiver** Pi 4B in monitor mode, on a direct Ethernet link
  (`10.0.0.100` ← `10.0.0.250`) with NAT through the host

See `docs/02-network-topology.md` and `docs/21-tl-wdr4300.md`.

## Security notes

- Password hashes are redacted from everything in `config/`; only SSH public
  keys are present.
- The Pi is configured with passwordless sudo
  (`/etc/sudoers.d/010_nexmon-nopasswd`) for unattended builds, so anyone
  holding the SSH key has root. Remove it when the build is complete.
- The SSH private key is not in this repository.

## Built on

- **[nexmon](https://github.com/seemoo-lab/nexmon)** and
  **[nexmon_csi](https://github.com/seemoo-lab/nexmon_csi)** (Secure Mobile
  Networking Lab, TU Darmstadt) — the firmware patch that makes CSI
  extraction possible at all. Built from upstream on the Pi; see
  `docs/05-nexmon-csi-install.md`.
- **[nexcsi](https://github.com/nexmonster/nexcsi)** by Aravind Reddy Voggu —
  the CSI decoder, bundled unmodified in `vendor/`. Nothing here reimplements
  pcap parsing or CSI decoding.
- **[CSIKit](https://github.com/Gi-z/CSIKit)** by Glenn Forbes — used as an
  independent reference when validating the decoder; see
  `docs/11-validation.md`.

## License

MIT — see `LICENSE`. This covers the code in this repository. The tools above
are separate projects with their own terms; nexmon_csi in particular is built
from upstream on your own Pi and is not redistributed here.
