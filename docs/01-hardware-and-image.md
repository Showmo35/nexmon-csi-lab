# 1. Hardware and the USB image

## Hardware

| Item | Value |
|---|---|
| Board | Raspberry Pi 4 Model B Rev 1.5 |
| RAM | 7.6 GiB |
| Boot media | 58.3 GB USB flash drive (no SD card) |
| Wi-Fi chip | BCM4345/6 — i.e. **bcm43455c0**, SDIO `02D0:A9A6` |
| Wi-Fi MAC | `d8:3a:dd:f2:a3:3d` |
| Ethernet MAC | `d8:3a:dd:f2:a3:3a` |
| OS | Raspberry Pi OS Lite 64-bit, Debian 13 (trixie) |
| Kernel (as flashed) | `6.18.34+rpt-rpi-v8` aarch64 |
| Stock Wi-Fi firmware | `7.45.265` (Cypress, 2023-08-29), `FWID 01-b677b91b` |

**Why USB boot:** no SD card reader was available. The Pi 4B supports USB boot
out of the box on recent bootloader EEPROMs, so the image was written to a USB
flash drive instead.

> If the Pi ever fails to boot from USB, check that **no microSD card is
> inserted**. The Pi 4B's default EEPROM boot order tries SD first, so a
> leftover card — even a blank one — silently wins.

## How the image was created

Raspberry Pi Imager, Raspberry Pi OS Lite (64-bit), with advanced options:

- hostname `pi4b-nexmon`
- username `nexmon` (not the default `pi`)
- SSH enabled, **public-key only** (`ssh_pwauth: false`)
- timezone `America/New_York`, keyboard `us` / `pc105`
- `avahi-daemon` added as a package so `pi4b-nexmon.local` would resolve
- Wi-Fi configured for `eduroam`

The Imager writes three cloud-init files to the FAT32 `bootfs` partition:
`user-data`, `network-config`, and `meta-data`. These are read once, by
cloud-init, on first boot. **Because they are plain text on a FAT32 partition,
they can be edited from any PC before the first boot** — which is exactly how
both problems below were fixed.

## Two problems the image shipped with

Both were found *before* first boot and corrected on the boot partition. Neither
would have been recoverable afterwards without a monitor and keyboard.

### Problem 1 — the SSH key belonged to a different computer

`user-data` contained:

```yaml
ssh_authorized_keys:
  - "ssh-ed25519 AAAA...9FlE showmik@windows-pc-nexmon"
```

That key was generated on the original Windows PC (`~/.ssh/pi4b_nexmon`). Its
**private half does not exist on this machine**, and SSH password authentication
was disabled in the image. The Pi would have booted into a state nobody present
could log into.

Fixed by generating a fresh keypair here and rewriting that one line. See
[03-ssh-access.md](03-ssh-access.md).

### Problem 2 — the Wi-Fi config could never have worked

`network-config` contained:

```yaml
wifis:
  wlan0:
    access-points:
      "eduroam":
        auth:
          key-management: none
```

`eduroam` is WPA2-Enterprise (802.1X) and requires an identity, a password, and
an EAP method. Raspberry Pi Imager's basic Wi-Fi field cannot express any of
that, so it emitted `key-management: none` — an *open network* with no
credentials. This would never associate.

This was not worth fixing: the plan was always Ethernet. The entire `wifis`
section was removed instead, which also avoids `wpa_supplicant` retry noise at
boot and leaves `wlan0` unmanaged — the preferred starting state for Nexmon CSI
monitor-mode work. See [02-network-topology.md](02-network-topology.md).

## Files

- `config/boot-partition/user-data.ORIGINAL` — as written by Imager
- `config/boot-partition/user-data` — as corrected
- `config/boot-partition/network-config.ORIGINAL` — as written by Imager
- `config/boot-partition/network-config` — as corrected

Password hashes are redacted in all four.
