# Vendored dependencies

## nexcsi 0.5.2

Upstream: https://github.com/nexmonster/nexcsi — PyPI: `nexcsi==0.5.2`

**Unmodified.** Extracted from the official wheel
(`nexcsi-0.5.2-py3-none-any.whl`, sha in `nexcsi-0.5.2.dist-info/RECORD`).

Vendored rather than pip-installed because this machine's Python is
externally managed (PEP 668) with no `pip`, `ensurepip`, or working `venv`.
Vendoring avoids `--break-system-packages`, which risks the OS Python.

### Why nexcsi and not our own decoder

`lib/csi_io.py` previously implemented pcap parsing and CSI decoding by hand.
It had the **real/imaginary pair swapped** — amplitudes were correct but phase
was wrong by up to 4.7 rad. That bug survived weeks of use because every
analysis here happens to be amplitude-based.

Decoding is delegated to nexcsi. Verified byte-identical across all four stored
captures after the fix (max difference 0.000e+00).

### Why not CSIKit

[CSIKit](https://github.com/Gi-z/CSIKit) is the broader, more widely used
library and would be the other reasonable choice. It requires `scikit-learn`,
`pandas` and `PyWavelets`, none of which are installed here, and it cannot be
pip-installed for the reason above. CSIKit's own reference capture
(`example_43455c0.pcap`) is still used as an independent validation input —
see `../docs/11-validation.md`.

### To update

```bash
curl -sL <wheel-url-from-pypi> -o nexcsi.whl
python3 -c "import zipfile; zipfile.ZipFile('nexcsi.whl').extractall('.')"
```

Then re-run the regression check in `../docs/11-validation.md`.
