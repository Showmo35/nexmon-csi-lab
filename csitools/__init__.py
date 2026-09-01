"""
csitools — a small, reusable toolkit for Nexmon CSI on the Raspberry Pi 4B.

Decoding is delegated to **nexcsi** (vendored in ../vendor/), the reviewed
decoder for nexmon_csi. Nothing here reimplements pcap parsing or CSI decoding.

    from csitools import load, subcarrier_axis, normalize_per_packet

    ts, csi, rssi, macs = load("capture.pcap")   # one frame type, beacons dropped
    idx, sc = subcarrier_axis()                  # 55 usable subcarriers
    db = 20*np.log10(abs(csi[:, idx]))
    db = normalize_per_packet(db)                # remove AGC

KNOWN LIMITATIONS of the underlying hardware/firmware — these are not bugs in
this toolkit and are not fixable here:

  1. The Pi is 1x1. `-N 7` returns three copies of ONE spatial stream, and -
     more importantly - frames the AP sends with TWO spatial streams cannot
     be decoded at all, so they yield no CSI. A 2x2 client will rate-adapt
     into that region and the capture will be nearly empty of data frames.
     Use bin/csi-capture, whose broadcast traffic is always single-stream.
  2. Record count is NOT sampling rate. Retransmissions reuse their sequence
     number and are reported again. Use csitools.audit() / bin/csi-audit.
     (The former "data-frame CSI arrives as a ~0.5 s burst then stops"
     limitation was not a firmware quirk - it was the Pi's own association
     collapsing while it tried to be both client and receiver.)
  3. Subcarrier sign inversion is reported upstream (nexmon_csi #100) and
     unresolved. Affects phase, not amplitude.
"""
from csitools.io import (              # noqa: F401
    load, read_raw, unpack, subcarrier_axis, mean_cfr_db,
    DEVICE, BEACON_FCTL,
)
from csitools.clean import (           # noqa: F401
    normalize_per_packet, pca_denoise, despike,
)
from csitools.audit import (           # noqa: F401
    audit, check, format_audit, frame_type_name, is_control,
    OUTAGE_S, CLUSTER_S,
)

__all__ = [
    "load", "read_raw", "unpack", "subcarrier_axis", "mean_cfr_db",
    "normalize_per_packet", "pca_denoise", "despike", "audit", "check",
    "format_audit",
    "frame_type_name", "is_control", "OUTAGE_S", "CLUSTER_S",
    "DEVICE", "BEACON_FCTL",
]
