# csitools — Nexmon CSI on the Raspberry Pi 4B

A small, reusable toolkit for collecting and reading Wi-Fi Channel State
Information from a Raspberry Pi 4B running
[nexmon_csi](https://github.com/seemoo-lab/nexmon_csi), plus the rig setup
that produced it.

**Decoding is delegated to [nexcsi](https://github.com/nexmonster/nexcsi)**,
vendored unmodified in `vendor/`. Nothing here reimplements pcap parsing or
CSI decoding — see `docs/11-validation.md` for the comparison against nexcsi
and CSIKit.

## Quickstart

```bash
bin/csi-checkup                  # full rig + CSI health check
bin/csi-capture out.pcap 30      # collect 30 s  (~166 Hz, see below)
bin/csi-audit out.pcap --hz 30   # what did you ACTUALLY get?
bin/csi-plot out.pcap -o plot.png # |H| over time, mean CFR, traces

bin/csi-record runs/ wave -p 10:10x3   # timed activity run with cues + plot
bin/csi-regress                        # decode pipeline vs data/reference/
```

```python
import sys; sys.path.insert(0, "/path/to/this/repo")
import csitools, numpy as np

ts, csi, rssi, macs = csitools.load("out.pcap")   # one frame type, beacons dropped
idx, sc = csitools.subcarrier_axis()              # 55 usable subcarriers
db = 20*np.log10(np.abs(csi[:, idx]))
db = csitools.normalize_per_packet(db)            # remove AGC
```

The tools resolve their own location, so they work from any directory.

## Known limitations — NOT fixable in this toolkit

These are properties of the hardware and firmware. A clean folder does not
make them go away.

1. **Data-frame CSI arrives as a ~0.5 s burst, then stops.**
   ([nexmon_csi #177](https://github.com/seemoo-lab/nexmon_csi/issues/177),
   unresolved upstream.) Take repeated bursts rather than one long capture.
   ~600 frames per burst.
2. **The Pi is 1×1.** `-N 7` returns three copies of ONE spatial stream,
   because a single-antenna client is only ever sent one. Multi-stream CSI is
   impossible on this receiver.
3. **Subcarrier sign inversion**
   ([#100](https://github.com/seemoo-lab/nexmon_csi/issues/100)) is reported
   upstream and unresolved. Affects phase, not amplitude.
4. **Absolute level is not trustworthy** — CSI is delivered post-AGC and the
   AGC restages even at fixed distance. Use the CFR *shape*, not the level.

## The two rules that matter

Both measured, both counter-intuitive, both in `docs/10-collection-method.md`:

1. **Never sniff beacons.** Beacon CSI is ~10× more variable than data-frame
   CSI (4.26 dB vs 0.45 dB per-subcarrier std) and produces artifacts that look
   exactly like real signal.
2. **Keep one frame type.** Types sit at different mean levels, so mixing any
   two adds variance even after beacons are excluded.

`csitools.load()` does both by default.

## Record count is not sampling rate

A nexmon_csi pcap is a stream of CSI *records*, and one 802.11 transmission
can produce many of them — a retransmission reuses its sequence number, so
the extractor reports it again. Always check a capture with `bin/csi-audit`,
which counts **distinct transmissions** rather than records:

```
  frame type    recs distinct     x  real Hz  covers
  Data          3156     3156  1.0x    166.3    100%
```

An earlier version of this repo collected CSI with the Pi both associated to
the AP and extracting CSI, and reported "44 Hz" from captures whose data
frames were 27 real transmissions repeated ~24x inside half a second. See
`docs/10-collection-method.md`.

## Layout

```
csitools/         the package — io.py (nexcsi wrapper), clean.py (AGC, PCA)
bin/              csi-capture (collect), csi-record (timed activity runs),
                  csi-sniff (Pi side), csi-audit, csi-regress, csi-checkup,
                  csi-plot, csi-plot-activity, csi-plot-streams,
                  restore-pc-network
vendor/nexcsi/    nexcsi 0.5.2, unmodified
data/reference/   three captures used for regression checks
projects/         per-application work
  water-impurity/   protocol + scripts (data to be collected)
  sound/            tone detection: protocol, capture + analysis scripts
docs/             rig setup (01-06), method + validation + findings (10-13),
                  routers (20-22)
config/           cloud-init files as flashed and as corrected
```

## Docs

| | |
|---|---|
| `docs/10-collection-method.md` | **how to collect correctly** — read first |
| `docs/11-validation.md` | comparison against nexcsi and CSIKit |
| `docs/12-findings.md` | the diagnostic path, including the wrong turns |
| `docs/13-tools.md` | what each tool checks and how to read it |
| `docs/01-06` | Pi provisioning, network, firmware install, troubleshooting |
| `docs/20-22` | lab router inventory and configuration |

## Rig

Three roles, on three devices — the Pi must not be more than one of them:

- **transmitter** TL-WDR4300, `nexmon-lab-5g`, ch161 fixed
- **client** drives the transmitter so it has something to send. Currently
  this PC's Wi-Fi, borrowed for the length of a capture; a 1x1 phone or USB
  dongle would be better and would cost no internet.
- **receiver** Pi 4B, monitor mode only, on a direct Ethernet cable
  (`10.0.0.100` ← `10.0.0.250`) NAT'd to the internet through this PC

Details in `docs/02-network-topology.md`, `docs/21-tl-wdr4300.md` and
`docs/10-collection-method.md`.

## Security notes

- Password hashes are redacted from everything in `config/`.
- The Pi has passwordless sudo (`/etc/sudoers.d/010_nexmon-nopasswd`), enabled
  for unattended builds. Anyone holding the SSH key therefore has root.
  Remove with `sudo rm /etc/sudoers.d/010_nexmon-nopasswd`.
- `~/.ssh/pi4b_nexmon` has no passphrase and is not in this repo.
