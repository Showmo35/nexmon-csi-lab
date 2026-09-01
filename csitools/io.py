"""
csitools.io — reading Nexmon CSI captures.

PARSING AND DECODING IS NOT IMPLEMENTED HERE. It is delegated to
**nexcsi** (https://github.com/nexmonster/nexcsi), the reviewed decoder for
nexmon_csi, vendored unmodified in ../vendor/. A previous hand-written decoder
in this file had the real/imaginary pair swapped - amplitudes were right but
phase was wrong by up to 4.7 rad. Do not reimplement it.

What this module adds is only what nexcsi does not provide, and every piece of
it is measured rather than assumed - see ../docs/11-validation.md:

  load()                  frame-type selection (beacons are unusable here)
  subcarrier_axis()       usable subcarrier set for THIS hardware
  normalize_per_packet()  AGC removal
  pca_denoise()           low-rank artifact removal

Usage:

    import sys; sys.path.insert(0, "lib")
    import csitools as csi
    ts, csi_, rssi, macs = csi.load("capture.pcap")
    idx, sc = csi.subcarrier_axis()
"""
import os
import sys

import numpy as np

# vendored upstream decoder
_VENDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "vendor")
if _VENDOR not in sys.path:
    sys.path.insert(0, os.path.abspath(_VENDOR))

from nexcsi import decoder as _nexcsi_decoder          # noqa: E402
from nexcsi import nulls as NEXCSI_NULLS               # noqa: E402
from nexcsi import pilots as NEXCSI_PILOTS             # noqa: E402

DEVICE = "raspberrypi"          # bcm43455c0 - the Pi 3B+/4 chip
_dec = _nexcsi_decoder(DEVICE)

BEACON_FCTL = 0x80


def read_raw(path):
    """Parse a pcap with nexcsi. Returns its structured array unchanged.

    Fields: ts_sec ts_usec saddr daddr sport dport magic rssi fctl mac seq
            css csp cvr csi
    (css = core/spatial-stream, csp = chanspec, cvr = chip version)
    """
    return _dec.read_pcap(path)


def unpack(csi_field, fftshift=False):
    """nexcsi's int16 -> complex64 conversion. fftshift=False keeps raw FFT
    order (bin 0 = DC), which is what subcarrier_axis() indexes against."""
    return np.asarray(_dec.unpack(csi_field, fftshift=fftshift))


def load(path, fctl="auto"):
    """Return (timestamps, csi[T,N] complex, rssi[T], sorted source MACs).

    fctl selects which 802.11 frame type to keep:
        "auto"  (default) the most numerous NON-BEACON type
        int     that exact frame-control byte, e.g. 0x88 for QoS Data
        None    keep everything (NOT recommended)

    WHY FILTER: measured on this rig, same capture, split by frame type -

        frame type   n    per-SC std   5-apart SC corr   lag-1 (time)
        QoS Data   661      0.45 dB         +0.857          -0.003
        0x84       259      0.27 dB         +0.760          +0.006
        Beacon     259      4.26 dB         +0.052          +0.386

    Beacons are ~10x more variable and make a static room look like it is
    moving. Types also sit at different mean levels, so mixing any two adds
    variance (QoS only 0.45 dB, data mixed 1.52 dB, everything 3.14 dB).
    """
    s = read_raw(path)
    if len(s) == 0:
        raise ValueError(f"{path}: no CSI records")

    if fctl == "auto":
        from collections import Counter
        c = Counter(int(x) for x in s["fctl"] if int(x) != BEACON_FCTL)
        if not c:
            c = Counter(int(x) for x in s["fctl"])
        fctl = c.most_common(1)[0][0]

    keep = np.ones(len(s), dtype=bool) if fctl is None else (s["fctl"] == fctl)
    if not keep.any():
        raise ValueError(f"{path}: no frames of type 0x{fctl:02x}")
    s = s[keep]

    ts = s["ts_sec"].astype(np.float64) + s["ts_usec"].astype(np.float64) / 1e6
    csi = unpack(s["csi"], fftshift=False)
    rssi = s["rssi"].astype(np.int16)
    macs = sorted({":".join(f"{b:02x}" for b in m) for m in s["mac"]})
    return ts, csi, rssi, macs


def subcarrier_axis(n=64, conservative=False):
    """(fft_bin_indices, subcarrier_numbers) for the usable data subcarriers.

    Raw layout is standard FFT order (bin 0 = DC, 1..31 = +1..+31,
    32..63 = -32..-1) - which is why unpack() is called with fftshift=False.

    The published null sets disagree, and neither matches this hardware:

        nexmon README  -> 52 used (+/-1..+/-26)   legacy 802.11a/g
        nexcsi         -> 56 used (+/-1..+/-28)   802.11n HT
        MEASURED HERE  -> 55 used (-28..-1, +1..+27)

    Measured across four HT captures: bins with std exactly 0, and bins whose
    median amplitude exceeds 5x typical, are unusable. On this rig **+28 is an
    artifact** (median ~17000 vs ~600 typical) while -28 is clean - an
    asymmetry neither published set describes.

    conservative=True returns nexcsi's HT set minus our measured-bad bins,
    intersected with the nexmon README set (+/-1..+/-26, 52) - use it to match
    published nexmon work exactly.
    """
    if n != 64:
        raise NotImplementedError(
            f"subcarrier_axis for n={n} not defined. nexcsi.nulls has the "
            f"null indices for 40/80/160 MHz if you need them.")
    if conservative:
        pairs = [(i - 64, i) for i in range(38, 64)] + [(i, i) for i in range(1, 27)]
    else:
        pairs = [(i - 64, i) for i in range(36, 64)] + [(i, i) for i in range(1, 28)]
    return [i for _, i in pairs], np.array([sc for sc, _ in pairs])


def mean_cfr_db(path, drop_adjacent_dc=False, fctl="auto"):
    """Mean channel frequency response in dB, averaged over all frames."""
    ts, csi, rssi, macs = load(path, fctl=fctl)
    idx, sc = subcarrier_axis(csi.shape[1])
    mag = np.abs(csi[:, idx])
    if drop_adjacent_dc:
        k = np.abs(sc) > 1
        sc, mag = sc[k], mag[:, k]
    db = 20 * np.log10(mag + 1e-9)
    return dict(sc=sc, mean=db.mean(axis=0), std=db.std(axis=0),
                n=len(ts), rssi=float(np.mean(rssi)), macs=macs)
