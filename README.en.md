# fprintdriver — EgisTec EH575 (1c7a:0575) libfprint driver research

> [中文版](README.md)

Goal: make the EgisTec EH575 fingerprint sensor (found in the Acer
SFX14-41G and similar machines) genuinely usable on Linux — accuracy at
the level of everyday desktop unlock — and ultimately produce a driver
that can be submitted to
[libfprint upstream](https://gitlab.freedesktop.org/libfprint/libfprint).

## Release status (2026-09-13)

- **Driver works**: press capture architecture + Windows-engine matcher
  port, verified on real hardware (KDE lock screen / fprintd / Bitwarden
  polkit unlock). Matcher validation numbers in `docs/comparison.en.md`
  §6 (small-sample, single-machine validation: offline 6-genuine /
  12-impostor FRR/FAR 0%, offline threshold margin ≥20, on-hardware
  impostor separation margin 15 — evidence-strength caveat at the end of
  that section)
- **Driver source**:
  [cosct/libfprint-egis0575](https://github.com/cosct/libfprint-egis0575)
  (upstream libfprint + the `egis0575` driver, branch `egis0575`,
  LGPL-2.1+)
- **Arch users**: AUR package `libfprint-egis0575`
  (`yay -S libfprint-egis0575`)
- **Todo**: collect feedback from more EH575 machines to tune
  thresholds; prepare the upstreamable patch series
- **Upgrade note**: v0.2.0 template serialization dropped the orientation
  field that scoring depends on, so prints enrolled with v0.2.0 cannot
  verify on the new driver — after upgrading, run `fprintd-delete` and
  re-enroll

## Repository layout

```
docs/     Index in docs/README.md (bilingual): protocol wire-protocol
          baseline · comparison architecture decisions & matcher
          endgame · windows-engine-tables coefficient extraction
scripts/  Test and data-collection tooling (see below)
tools/    Evaluation utilities (egis0575-matcher-test / eval_bz3 / hwpoll)
packaging/ Release recipes: aur/PKGBUILD (canonical AUR copy) ·
          deb/build-deb.sh · rpm/libfprint-egis0575.spec — invoked by the fork
          repo's release workflow on egis0575-v* tags; artifacts are
          attached to the GitHub Release and the AUR package is updated
          automatically
PKGBUILD  Local development packaging (builds from the working tree;
          the AUR version lives on AUR)
```

The driver source lives in its own repository (the local `libfprint/`
directory is not distributed with this one):

```bash
git clone -b egis0575 https://github.com/cosct/libfprint-egis0575 libfprint
```

Intentionally not distributed here (size or privacy): `refs/` (four
third-party reference implementations — clone them yourself),
`datasets/` (raw fingerprint frames — biometric data), and `acerdrv/`
(Acer's official Windows driver — copyright EgisTec/Acer).

## Reproducing the research workflow

```bash
# 0) One-time: clone the driver source into ./libfprint/ (the path the
#    scripts expect) and build it. (Needs meson>=0.62 + ninja plus dev
#    packages for glib2/libusb/libgusb/pixman/openssl/libgudev; on Arch
#    also gobject-introspection and gtk-doc.)
git clone -b egis0575 https://github.com/cosct/libfprint-egis0575 libfprint
meson setup libfprint/builddir libfprint
meson compile -C libfprint/builddir

# 1) One-time: install a temporary udev rule for direct device access
#    (asks for the sudo password)
./scripts/setup-access.sh

# 2) 20 s fingerless probe: verify init stability, background warm-up,
#    and no idle-poll timeouts
./scripts/probe.sh

# 3) Collect a dataset: press as the script instructs (keep the sensor
#    empty for the first 3 s for background warm-up)
./scripts/collect-dataset.sh press-test 60

# 4) Column-activity analysis (settled: all 103 columns active, no dead
#    zone; the script is useful to re-check new machines)
python3 scripts/analyze-columns.py datasets/press-test-*/
```

Driver tunables (environment variables):
- `EGIS0575_ACTIVE_WIDTH` — active column count (default 103; settled —
  no dead zone — kept for experiments)
- `EGIS0575_SKIP_CALIBRATION=1` — skip calibration upload and use the
  EH577-style init (known to produce all-zero frames; A/B testing only)
- `EGIS0575_PGM_DEBUG_DIR` / `_LOG` / `_INTERVAL_MS` / `_CONTROL` — PGM
  dataset capture (in capture mode the driver keeps dumping processed
  frames and enroll/verify actions never complete — stateless probing
  only; the `_CONTROL` file can pause/resume capture)
- `EGIS0575_FRAME_DUMP_DIR` — raw 5356-byte frame dumps
- `EGIS0575_LIVE_FRAME_PATH` — live frame written to a single PGM
- `EGIS0575_VERIFY_DUMP_DIR` — dump verify-time probes and gallery
  feature counts (offline matcher analysis)
- `EGIS0575_DISABLE_STRETCH=1` — disable stretch5 contrast enhancement
- `EGIS0575_DEBUG_MAX_FILES` — file cap for PGM/raw-frame dumps (default
  5000, ≈26 MB of raw frames; all debug sinks are written 0600 into 0700
  dirs since they hold biometric data)

Python-script dependencies are listed in `requirements.txt` (Python ≥ 3.9
+ numpy; eval_sigfm also needs OpenCV, hwpoll needs pyusb). This
repository (docs/scripts/tools) is licensed LGPL-2.1-or-later like the
driver (see `LICENSE`).

## Key findings at a glance

1. The EH575 is an **image sensor** (tiny 103×52 frames, host-side
   matching, **no dead columns**) — not match-on-chip
2. swipe+Bozorth3 (the topni1 driver) is the root cause of the poor
   accuracy; every classic matching scheme (NCC / Bozorth3 / POC / SigFM
   / orientation field) **fails** to separate same-person cross-finger
   attempts at this sensor's raw SNR (data in docs/comparison.en.md §5)
3. This driver = EH577's press capture architecture + topni1's
   calibration init (a hard requirement for imaging on EH575) + the
   **Windows-engine matcher port** (11-orientation ridge matched-filter
   bank, 512-bit descriptors, Hamming/translation-cluster scoring, with
   coefficients extracted from the vendor DLL; small-sample offline
   FRR/FAR 0%, on-hardware integration accepted)
4. `01 01 01 → re-run PRE_INIT` is EH575's intended error handling
5. The topni1 `FPI_DEVICE_Egis0575` typo recorded earlier was re-checked
   across that fork's whole history and **does not exist** (see
   docs/comparison.en.md §8); nothing to report
