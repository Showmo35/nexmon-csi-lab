"""
csitools.clean — artifact removal.

Both functions here are project-specific because no standard library has an
opinion on them, and both are MEASURED rather than assumed. See
docs/05-validation.md.
"""
import numpy as np


def normalize_per_packet(db, method="l2"):
    """Remove the per-packet AGC gain from CSI amplitude in dB.

    nexmon delivers CSI *after* the receiver AGC, and the AGC restages even at
    fixed distance. From nexmon_csi issue #93, by the author of the RSSI patch:

        "CSI ... goes through AGC first, destroying most 'distance' information
         with it... Even at a stable physical distance, AGC will cause the CSI
         waveform to change"

    The commonly cited remedy is RSSI rescaling. MEASURED HERE IT IS WORSE:
    RSSI carried only 6 distinct values across a 5 dB range and correlated just
    +0.33 with CSI total power - too coarse.

        raw                  1.000 dB per-subcarrier std, lag-1 +0.144
        RSSI-compensated     1.281 dB   (-28%)
        per-packet mean      0.828 dB
        per-packet L2        0.729 dB, lag-1 +0.008   <- default

    COST: absolute level is discarded, so path-loss/range information is lost.
    The CFR *shape* is preserved, which is what material characterisation uses.
    """
    if method == "l2":
        lin = 10 ** (db / 20.0)
        lin = lin / np.linalg.norm(lin, axis=1, keepdims=True)
        return 20 * np.log10(lin + 1e-12)
    if method == "mean":
        return db - db.mean(axis=1, keepdims=True)
    raise ValueError(f"unknown method {method!r}")


def pca_denoise(db, drop=2, return_components=False):
    """Remove a low-rank artifact from a CSI amplitude time series.

    The standard WiFi-sensing recipe (CARM lineage; WiAR uses Kalman+PCA+DWT):
    PCA across subcarriers, discard the leading component(s) as noise.

    Only useful for DYNAMIC sensing. It operates on mean-removed data and so
    cannot change the mean CFR (verified: 9.2e-14 dB), which is what a
    quasi-static measurement uses - there it is a no-op.
    """
    mu = db.mean(axis=0)
    C = db - mu
    U, S, Vt = np.linalg.svd(C, full_matrices=False)
    Sd = S.copy()
    Sd[:drop] = 0
    clean = mu + (U * Sd) @ Vt
    if return_components:
        return clean, dict(explained=(S ** 2 / (S ** 2).sum()),
                           pc=(U * S)[:, :max(drop, 3)])
    return clean


def despike(db, window=7, sigma=8.0):
    """Replace impulsive outliers with a local median (Hampel filter).

    nexmon_csi occasionally returns a wildly wrong value for a subcarrier -
    the sign-inversion artifact reported upstream in issue #100, unresolved.
    Measured on a 24294-frame capture: 1.22 % of samples, touching 21.5 % of
    frames, and they inflate per-subcarrier std from 0.40 to 0.70 dB.

    They matter most for SPECTRAL work. An impulse is broadband, so a handful
    of them paint vertical stripes across an entire spectrogram and bury any
    real narrow line underneath.

    db      [T, N] real array, time along axis 0
    window  samples in the local median (odd, along time)
    sigma   threshold in robust standard deviations (MAD-scaled)
    """
    from scipy.ndimage import median_filter
    med = median_filter(db, size=(window, 1), mode="nearest")
    resid = db - med
    mad = np.median(np.abs(resid - np.median(resid)))
    if mad <= 0:
        return db.copy()
    return np.where(np.abs(resid) > sigma * 1.4826 * mad, med, db)
