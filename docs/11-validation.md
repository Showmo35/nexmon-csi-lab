# Pipeline validation against reference implementations

Checked against two independent, well-known decoders:

- **[nexcsi](https://github.com/nexmonster/nexcsi)** (nexmonster) — the fast
  numpy decoder for nexmon_csi
- **[CSIKit](https://github.com/Gi-z/CSIKit)** (Gi-z) — the most widely used
  Python CSI library; supports Atheros, Intel, Nexmon, ESP32, PicoScenes

## 1. Packet header layout — CONFIRMED IDENTICAL

`nexcsi`'s numpy dtype:

```python
("magic", uint16), ("rssi", int8), ("fctl", uint8), ("mac", uint8, 6),
("seq", uint16), ("css", uint16), ("csp", uint16), ("cvr", uint16),
("csi", int16, nsub*2)
```

Byte-for-byte what `csi_io.decode()` parses (`css` = core/spatial-stream,
`csp` = chanspec, `cvr` = chip version). No discrepancy.

## 2. Real/imaginary order — DISCREPANCY FOUND AND FIXED

The reference does `csi.astype(float32).view(complex64)`, and numpy's
`complex64` is **(real, imag)** — so the first int16 of each pair is REAL.

**Our decoder had the pair swapped.** Impact:

```
raw int16 pair (143, 321)
  ours (before fix)  ->  321+143j
  reference          ->  143+321j
  amplitude          ->  IDENTICAL  (|a+bi| == |b+ai|), max diff 0.00e+00
  phase              ->  WRONG, by up to 4.667 rad
```

**All analysis in this project is amplitude-based, so no previous result is
affected.** Phase-based work (AoA, ranging, permittivity from delay) would
have been wrong. Fixed in `csi_io.decode()`.

## 3. FFT ordering — CONFIRMED

`nexcsi` applies `np.fft.fftshift` to reach -32..+31 order, which confirms the
raw layout is **standard FFT order** (bin 0 = DC), as determined here
empirically from the `std == 0.0` signature of the null bins.

## 4. Usable subcarriers — THE PUBLISHED SETS DISAGREE

| source | nulls (20 MHz) | usable |
|---|---|---|
| nexmon README | ±27…±32, 0 | 52 (±1…±26) — legacy 802.11a/g |
| nexcsi | ±29…±32, 0 | 56 (±1…±28) — 802.11n HT |
| **measured here** | ±29…±32, 0, **+28** | **55** (−28…−1, +1…+27) |

Measured across four HT (QoS Data) captures, excluding bins with std exactly 0
and bins whose median is >5× typical. **On this rig `+28` is an artifact**
(median ~17000 vs ~600 typical) while `−28` is clean — an asymmetry neither
published set describes.

`subcarrier_axis()` now defaults to the measured 55.
`subcarrier_axis(conservative=True)` gives the nexmon README's 52 (a strict
subset) for matching published work.

## 5. End-to-end — our decoder reads CSIKit's own reference file

Parsing `CSIKit/data/nexmon/example_43455c0.pcap` (an independent capture from
a different device) with `csi_io`:

```
CSI frames parsed : 566
subcarriers/frame : 256        <- 80 MHz, inferred from chanspec 0x2000
chanspec          : 0xe02a     <- channel 42, 80 MHz, 5 GHz
source MAC        : 98:de:d0:48:92:66
RSSI              : -59..-58 dBm
```

Correct on a bandwidth and device we have never used.
`subcarrier_axis()` raises `NotImplementedError` for n=256 rather than silently
returning a wrong set — 80 MHz null indices are not defined here.

## 6. Decoding now DELEGATED to nexcsi, not reimplemented

`csitools/` no longer parses pcaps or decodes CSI. It calls
**nexcsi 0.5.2**, vendored unmodified in `../vendor/` (see `vendor/README.md`
for why vendored rather than pip-installed).

When the switch was made, the nexcsi-backed decoder was compared against the
corrected hand decoder on the then-current captures and was identical on all
four. Those captures have since been deleted — they were collected with a
method that produced ~27 real measurements per file (see
`10-collection-method.md`) — and the hand decoder no longer exists, so that
particular comparison cannot be re-run.

**The standing regression check is `bin/csi-regress`**, against the three
captures now in `data/reference/`, taken 2026-08-31 with `bin/csi-capture`:

```
$ bin/csi-regress
  ok   reference_r1.pcap  3040 data frames, 64 subcarriers, RSSI -41.28 dBm
  ok   reference_r2.pcap  3160 data frames, 64 subcarriers, RSSI -39.13 dBm
  ok   reference_r3.pcap  3220 data frames, 64 subcarriers, RSSI -39.16 dBm

regression: all captures match
```

It pins record and distinct-transmission counts, the frame-type mix, source
MAC, chanspec, RSSI, and the full mean CFR to 1e-3 dB — so a change in the
vendored decoder, the header handling or the subcarrier axis fails loudly
instead of silently shifting every number. `--update` re-records the
expectations, and should only be run after a change you intend.

### Component provenance

| component | tool |
|---|---|
| pcap parse + CSI decode | **nexcsi 0.5.2** (vendored) |
| Hampel / Butterworth / STFT | scipy.signal, scipy.ndimage |
| PCA | numpy.linalg.svd |
| clustering | scipy.cluster.vq |
| CSI capture on the Pi | nexutil + makecsiparams (nexmon_csi) |
| packet capture | tcpdump |

What remains project-specific in `csi_io.py` — because no standard library has
an opinion on it, and each is **measured**, not assumed:

- `load()` frame-type selection (beacons unusable on this rig)
- `subcarrier_axis()` usable set (+28 is an artifact here)
- `normalize_per_packet()` AGC removal (RSSI rescaling measured worse)
- `pca_denoise()` low-rank artifact removal

## Verdict

The collection and decode pipeline is **standard**: the header layout, FFT
ordering, and bandwidth inference all match the reference implementations, and
the decoder reads a third-party reference file correctly.

Two deviations from the naive/published approach are **deliberate and measured**:

1. **Data frames, not beacons** (`collect.sh`) — beacons give ~10x more
   variable CSI on this hardware. See `README.md`.
2. **55 subcarriers, not 52 or 56** — measured, because `+28` is bad here.

One real bug was found by this comparison (real/imag order) and fixed.
