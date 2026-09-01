"""
csitools.audit — how many times was the channel ACTUALLY measured?

A nexmon_csi pcap is a stream of CSI *records*. It is NOT a stream of
measurements: the same 802.11 transmission can produce many records, and
counting records overstates the sampling rate by a large factor.

Measured on a capture made the old way (the Pi associated to the AP and
pinging it, while also extracting CSI): 661 QoS-Data records carrying **27
distinct sequence numbers**, all inside a 0.49 s window of a 26.9 s capture.
Reported at the time as "44 Hz". The channel was sampled 27 times. That
method, and every capture made with it, has been removed - see
docs/10-collection-method.md.

The 802.11 sequence-control field (`seq` in nexcsi's array) is the ground
truth: the transmitter increments it once per new MSDU, so

    distinct (fctl, seq) values / time span  =  real CSI sampling rate
    records / distinct                       =  inflation factor

Note `seq` packs sequence_number<<4 | fragment, hence the multiples of 16.
A retransmission reuses the sequence number, so a retry burst and a firmware
re-read of a stale register both land in the same bucket — either way those
records are not independent samples of the channel and must not be counted
as if they were.
"""
from collections import Counter

import numpy as np

from csitools.io import read_raw

# A gap longer than this is an outage, not arrival structure. Two beacon
# intervals (102.4 ms each) covers DTIM buffering with room to spare.
OUTAGE_S = 0.25

# Frames separated by more than this belong to different arrival clusters.
# An absolute threshold, because a multiple of the median cadence is
# meaningless here: within a DTIM batch frames are ~0.2 ms apart, so even
# 20x the median lands at 4 ms and splits the batch itself into "bursts".
# 50 ms is below one beacon interval (102.4 ms) and far above any in-batch
# spacing.
CLUSTER_S = 0.05

# First octet of the 802.11 Frame Control field:
#   bits 0-1 protocol version | bits 2-3 type | bits 4-7 subtype
_MGMT = {0: "AssocReq", 1: "AssocResp", 2: "ReassocReq", 3: "ReassocResp",
         4: "ProbeReq", 5: "ProbeResp", 8: "Beacon", 9: "ATIM",
         10: "Disassoc", 11: "Auth", 12: "Deauth", 13: "Action"}
_CTRL = {8: "BlockAckReq", 9: "BlockAck", 10: "PS-Poll", 11: "RTS",
         12: "CTS", 13: "ACK", 14: "CF-End"}
_DATA = {0: "Data", 4: "Null", 8: "QoS Data", 12: "QoS Null"}


def is_control(fctl):
    """Control frames (ACK, BlockAck, RTS/CTS) carry NO sequence-control
    field, so `seq` is meaningless for them and must not be used to count
    distinct transmissions or an inflation factor."""
    return ((int(fctl) >> 2) & 3) == 1


def frame_type_name(fctl):
    """Decode a frame-control first octet, e.g. 0x88 -> 'QoS Data'.

    Worth decoding rather than printing hex: on the old associated-Pi
    captures the two unexplained types 0x84 and 0xa0 turn out to be
    **BlockAckReq** and **Disassoc** — i.e. the AP asking again for
    acknowledgements it never got, and finally dropping the client. That is
    a retransmission storm, and it is why one transmission showed up dozens
    of times.
    """
    f = int(fctl)
    table = (_MGMT, _CTRL, _DATA, {})[(f >> 2) & 3]
    return table.get(f >> 4, f"0x{f:02x}")


def _unwrap_seq(seq):
    """Undo 12-bit sequence-number wrapping. Returns (unwrapped_seq, frag)
    packed into one integer so retransmissions still collide."""
    sn = (np.asarray(seq).astype(np.int64) >> 4) & 0xFFF   # 12-bit seq number
    frag = np.asarray(seq).astype(np.int64) & 0xF
    if len(sn) > 1:
        step = np.diff(sn)
        wraps = np.cumsum(np.r_[0, (step < -2048).astype(np.int64)])
        sn = sn + 4096 * wraps
    return sn * 16 + frag


def audit(path):
    """Per-frame-type accounting of records vs. distinct transmissions.

    Returns dict(span, n_records, macs, types=[per-type dicts]) where each
    per-type dict has:

        fctl, name, records, distinct, inflation,
        span        seconds between first and last record OF THIS TYPE
        rate        distinct / span   <- the real sampling rate
        coverage    span / capture span
        dup_csi     records whose CSI payload is byte-identical to another's
    """
    s = read_raw(path)
    if len(s) == 0:
        raise ValueError(f"{path}: no CSI records")
    t = s["ts_sec"].astype(np.float64) + s["ts_usec"].astype(np.float64) / 1e6
    t0, span = t.min(), max(t.max() - t.min(), 1e-9)
    macs = sorted({":".join(f"{b:02x}" for b in m) for m in s["mac"]})

    out = []
    for fctl, n in Counter(int(x) for x in s["fctl"]).most_common():
        m = s["fctl"] == fctl
        tt, seq, csi = t[m], s["seq"][m].astype(int), s["csi"][m]
        # ONE transmission = one sequence number. Core/stream slots are NOT
        # extra samples: this receiver is 1x1, so `-N 7` returns three copies
        # of a single estimate (see csitools/__init__.py, limitation 2).
        tspan = float(tt.max() - tt.min())
        # Arrival structure. "coverage" only says first-to-last span, which
        # reads 100% even when a third of the timeline has no frames in it.
        #
        # Two different things have to be told apart:
        #
        #   BURSTS  An AP buffers broadcast until a DTIM beacon and then sends
        #           the batch back to back, so frames legitimately arrive in
        #           ~0.2 ms clusters about every 100 ms. Measuring gaps against
        #           the within-burst median would call that 95% dead and fire
        #           on every good capture - a check that always fires is one
        #           nobody reads.
        #   OUTAGES A gap longer than OUTAGE_S is not structure. Nothing in
        #           normal 802.11 timing is that long: it means the source
        #           stopped, or the receiver stalled.
        gaps = np.diff(np.sort(tt))
        if len(gaps):
            med = max(float(np.median(gaps)), 1e-9)
            # "dead" only counts gaps over OUTAGE_S. A stream can be badly
            # chopped up well below that: a competing client on the same AP
            # produced 142 interruptions of 20-250 ms in 69 s, losing 31 % of
            # the timeline, while dead stayed at 0 %. Track that separately.
            choppy_thr = max(0.020, 10 * float(np.median(gaps)))
            chop = gaps > choppy_thr
            choppy = float(gaps[chop].sum()) / tspan if tspan > 0 else 0.0
            n_chop = int(chop.sum())
            outage = gaps > OUTAGE_S
            dead = float(gaps[outage].sum()) / tspan if tspan > 0 else 0.0
            n_gaps = int(outage.sum())
            # descriptive: how clustered are the arrivals?
            clustered = gaps > CLUSTER_S
            n_bursts = int(clustered.sum()) + 1
            cluster_gap_ms = (float(np.median(gaps[clustered])) * 1e3
                              if clustered.any() else 0.0)
            # Bunched or merely interrupted? If the median gap is close to the
            # mean, arrivals are evenly spaced and every frame is its own look
            # at the channel - an occasional long interruption does not change
            # that. Only when the median collapses far below the mean are
            # frames arriving in batches, where a whole batch samples one
            # instant and counting frames overstates the rate.
            bunched = float(np.median(gaps)) < 0.25 * float(gaps.mean())
        else:
            dead, n_gaps, med, n_bursts, cluster_gap_ms = 0.0, 0, 0.0, 1, 0.0
            bunched = False
            choppy, n_chop, choppy_thr = 0.0, 0, 0.0
        ctrl = is_control(fctl)
        distinct = None if ctrl else len(set(_unwrap_seq(seq).tolist()))
        out.append(dict(
            fctl=fctl, name=frame_type_name(fctl), records=int(n),
            control=ctrl,
            distinct=distinct,
            inflation=None if ctrl else n / distinct,
            streams=len(set(s["css"][m].astype(int).tolist())),
            span=tspan,
            dead=dead, n_gaps=n_gaps, median_gap_ms=med * 1e3,
            choppy=choppy, n_chop=n_chop, choppy_thr_ms=choppy_thr * 1e3,
            bursts=n_bursts, cluster_gap_ms=cluster_gap_ms, bunched=bunched,
            burst_hz=(n_bursts / tspan) if tspan > 0 else None,
            per_burst=(n / n_bursts) if n_bursts else n,
            # one frame spans no time, so it has no rate - report None rather
            # than dividing by an epsilon and printing 1e9 Hz
            rate=((n if ctrl else distinct) / tspan) if tspan > 0 else None,
            coverage=float(tspan / span) if span > 0 else 0.0,
            dup_csi=int(n - len(np.unique(np.asarray(csi), axis=0))),
        ))
    return dict(path=path, span=float(span), t0=float(t0),
                n_records=int(len(s)), macs=macs, types=out)


def format_audit(a, indent="  "):
    """Human-readable audit table. Returns a string."""
    L = [f"{indent}{a['n_records']} records over {a['span']:.1f}s "
         f"from {', '.join(a['macs'])}"]
    if len(a["macs"]) != 1:
        L.append(f"{indent}WARNING: {len(a['macs'])} transmitters — "
                 f"MAC filter is not doing its job")
    L.append(f"{indent}{'frame type':<12}{'recs':>6}{'distinct':>9}"
             f"{'x':>6}{'real Hz':>9}{'covers':>8}{'dead':>7}")
    for d in a["types"]:
        # control frames have no sequence number: report records only
        dist = "  n/a" if d["control"] else f"{d['distinct']}"
        infl = "    -" if d["control"] else f"{d['inflation']:>4.1f}x"
        rate = "      n/a" if d["rate"] is None else f"{d['rate']:>9.1f}"
        L.append(f"{indent}{d['name']:<12}{d['records']:>6}{dist:>9}"
                 f"{infl:>6}{rate}"
                 f"{d['coverage']*100:>7.0f}%"
                 + ("     -" if (d["control"] or d["records"] < 20)
                    else f"{d['dead']*100:>6.0f}%"))
    for d in a["types"]:
        if not d["control"] and d["records"] >= 50 and d["bunched"]:
            L.append(f"{indent}  {d['name']}: arrives in {d['burst_hz']:.1f} "
                     f"clusters/s of ~{d['per_burst']:.0f} frames, "
                     f"{d['cluster_gap_ms']:.0f} ms apart "
                     f"(~DTIM {max(1, round(d['cluster_gap_ms']/102.4))}); "
                     f"effective sampling rate is {d['burst_hz']:.1f} Hz, "
                     f"not {d['rate']:.0f} Hz")
    return "\n".join(L)


def check(a, want_hz=None, want_coverage=0.9, want_inflation=1.5):
    """Return a list of problem strings, empty if the capture is sound.

    A sound capture has ONE transmitter, one dominant frame type that spans
    essentially the whole recording with an even cadence, and ~1 record per
    transmission.
    """
    problems = []
    if len(a["macs"]) != 1:
        problems.append(f"{len(a['macs'])} source MACs: {', '.join(a['macs'])}")
    if not a["types"]:
        return ["no frames at all"]
    usable = [d for d in a["types"] if not d["control"]]
    if not usable:
        return ["only control frames — nothing carries a sequence number"]
    # judge the frame type you would actually analyse: the same choice
    # csitools.load(fctl="auto") makes - most numerous, beacons excluded
    pool = [d for d in usable if d["fctl"] != 0x80] or usable
    best = max(pool, key=lambda d: d["records"])

    # inflation is worth reporting wherever it is large enough to mislead,
    # not only on the frame type that happens to win
    for d in usable:
        if d is not best and d["records"] >= 50 and d["inflation"] > 3:
            problems.append(
                f"{d['name']}: {d['records']} records but {d['distinct']} "
                f"distinct transmissions ({d['inflation']:.1f}x)")
    if best["records"] >= 20 and best["coverage"] < want_coverage:
        problems.append(
            f"{best['name']} covers only {best['coverage']*100:.0f}% of the "
            f"capture ({best['span']:.1f}s of {a['span']:.1f}s) — the source "
            f"stopped transmitting or the extractor stalled")
    if best["inflation"] > want_inflation:
        problems.append(
            f"{best['name']} repeats each transmission {best['inflation']:.1f}x "
            f"({best['records']} records, {best['distinct']} distinct "
            f"sequence numbers) — records are NOT independent samples")
    if best["choppy"] > 0.05 and best["dead"] <= 0.05:
        problems.append(
            f"{best['name']}: stream is chopped up — {best['n_chop']} "
            f"interruptions longer than {best['choppy_thr_ms']:.0f} ms "
            f"({best['n_chop']/max(best['span'],1e-9):.1f}/s) losing "
            f"{best['choppy']*100:.0f}% of the timeline. Something else is "
            f"using the AP or the channel.")
    if best["dead"] > 0.05:
        problems.append(
            f"{best['name']}: {best['dead']*100:.0f}% of the timeline is dead "
            f"({best['n_gaps']} gaps longer than {OUTAGE_S*1000:.0f} ms) — the "
            f"source stopped and restarted, or the receiver stalled")
    if want_hz is not None and (best["rate"] is None or best["rate"] < want_hz):
        problems.append(
            f"{best['name']} real rate "
            + ("undefined (1 frame)" if best["rate"] is None
               else f"{best['rate']:.1f} Hz")
            + f" is below the {want_hz:.0f} Hz target")
    return problems
