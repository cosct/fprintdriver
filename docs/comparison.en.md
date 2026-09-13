# Four Implementations Compared & EH575 Driver Architecture Decisions

> **Status: research concluded.** All architecture decisions are settled and
> shipped in the published driver
> [cosct/libfprint-egis0575](https://github.com/cosct/libfprint-egis0575)
> v0.2.0 (AUR `libfprint-egis0575`). This document preserves the full
> decision chain and the experimental evidence.
> [中文版](comparison.md)

## 1. Architecture overview

| Dimension | topni1 egis0575 | Animeshz patch (2021) | championswimmer egis0577 (b19955e) | python |
|---|---|---|---|---|
| libfprint class | `FpImageDevice` | `FpImageDevice` | **`FpDevice` (pure device)** | none (open-fprintd D-Bus) |
| Scan model | swipe (10-frame stitching) | swipe (8 frames) | **press (single frame/touch)** | press (single frame) |
| Matcher | NBIS Bozorth3 (bz3=15) | NBIS Bozorth3 (bz3=15) | custom NCC (12-frame gallery) | OpenCV |
| Init | calibration read+upload (5 phases) | PRE_INIT/POST_INIT tables | PRE_INIT/POST_INIT tables | a third, equivalent sequence |
| Hardware status | EH575 works (poor accuracy) | unfinished | EH577 works (enroll/verify/KDE unlock) | semi-stable |

**This driver** = championswimmer's press-architecture base + topni1's
calibration init + the EH575 protocol tables + a port of the vendor Windows
engine matcher (§6).

## 2. Why the swipe model has poor accuracy

1. The sensor is 103×52; swipe stitching relies on motion estimation between
   small strips — motion-estimation error is amplified and stitching
   distortion destroys minutiae extraction outright
2. Bozorth3 is unreliable on images this small anyway (the EH577 author's
   own conclusion: NBIS unusable, match scores unstable)
3. Swipe asks the user to "drag the whole fingertip across" a sensor the
   size of a power button — terrible UX, and speed/angle/skew all affect
   frame assembly

## 3. Mechanisms ported from EH577 (all shipped)

### Capture (one complete fresh cycle per poll)
- PRE_INIT(29) → POST_INIT(17) with trailing `64 14 ec` frame read; the
  calibration driver replaces this with the calibration flow
  (protocol.md §4A), keeping POST_INIT semantics as the error-retry path
- Claim recycling: on reaching the budget, release + re-claim the interface
  and re-upload calibration (budget set to 200 frames/claim on EH575, §7.1)
- Startup hardening: 150 ms settle after claim; first-packet timeout →
  ≤2 claim-recycle retries → clean failure; uniform 2000 ms timeouts

### Finger presence (software)
- Warm-background baseline: collect 3 valid empty frames at startup
  (BACKGROUND_WARMUP_FRAMES=3), otherwise hot-pixel idle frames read as
  fingers (a deadlock trap)
- Rolling baseline: recent "no-finger" frames keep overwriting it;
  refresh gate std<10 (EH577's raw<200 gate is always false on EH575)
- Criteria: dual coverage/intensity gates after background subtraction
  (18%/10 presence, 25%/20 usable; validated with a clean margin on the
  EH575 dataset, see protocol.md §6)

### Per-touch (turn) state machine
- 400 ms settle (evaluate only after the finger settles); 1400 ms turn
  timeout (a single press never polls forever)
- Frames passing the quality gate are submitted immediately (fast exit);
  otherwise keep the "best frame" (fewest saturated pixels)
- After each accepted enrollment frame, an 800 ms re-arm lockout (forces
  a genuine lift)
- Phantom-presence recovery: unconditional 4-second stuck-presence watchdog

### Image pipeline (in order)
1. Full 103×52 width (EH575 has no dead columns, decision §4)
2. Warm-background subtraction (`val > bg+2 ? val-bg : 0`)
3. Pad width to a multiple of 4 (104) → `fpi_image_resize` 2x → 208×104
4. 3×3 median denoise (kills high-frequency speckle, keeps edges)
5. stretch5 contrast stretch: p5..p99 → 20..245
6. Stage-2 quality gate (all must pass):
   - grain < 6.000% (share of pixels with median-filter residual >25,
     stored ×1000)
   - 0 < minutiae < 10 (NBIS get_minutiae; the cap prevents noise from
     minting fake minutiae)
   - ridge pixels > 4000 (below threshold 180 counts as ridge)
   - Genuine-finger pass rate 86% (48/56); all failures had minutiae=0
     (blurry frames correctly rejected)

## 4. EH575 porting decisions (all settled)

| Decision | Outcome | Basis |
|---|---|---|
| Base architecture | championswimmer press | the only capture route proven on a real small-image sensor |
| Init | **topni1 calibration flow (required)** | hardware-verified: no calibration → all-zero frames (protocol.md §4B) |
| Active width | **full 103, no dead zone** | settled by 600-frame column-activity analysis; EH577's 33 dead columns don't exist on EH575 |
| swipe/press | press | §2 |
| Claim budget/recycle | ported, budget relaxed to 200 | deadlock prevention; pushing harder hangs the firmware (§7) |
| settle/turn timing | ported (400/1400 ms) | already tuned on real hardware |
| Stage-2 gate | ported + retuned on EH575 data | 86% pass rate, blurry frames correctly rejected |
| Matcher | **Windows-engine port** (NCC rejected) | §5: seven schemes all failed → §6: engine port passes |

## 5. Matcher experiment history: why seven schemes all failed (2026-09-12)

On a single dataset (same person's left/right index fingers,
position-varied galleries, multi-frame probes), every classic matching
scheme failed to separate genuine from impostor:

| Matcher | Genuine best | Impostor best | Conclusion |
|---|---|---|---|
| NCC (±30 window, multi-frame best) | 0.36–0.96 | 0.38–0.80 | overlapping; impostors reach 0.80 |
| Masked NCC (non-zero union) | 0.36–0.67 | 0.38–0.70 | no difference from plain NCC |
| Bozorth3 (2x, 4–10 minutiae) | ~0 | 0–7 | too few minutiae, consensus matching fails |
| Bozorth3 (4x, 54 minutiae) | 0 | 0–7 | minutiae are enhancement artifacts, not repeatable across presses |
| POC / BLPOC | 0.05–0.29 | 0.04–0.34 | complete overlap |
| Orientation field (structure-tensor block) | 0.023–0.026 | 0.019–0.026 | complete overlap |
| SigFM (SIFT+Lowe+geometric voting) | — | — | cross-press Lowe passes only 2–4 pairs (<5 floor); 350M self-match votes proved the port correct |

**Root cause (measured on raw frames)**: raw gray std of a press frame is
only 3.0 (empty frame 2.7) — ridge visibility is entirely synthesized by
the driver pipeline (background subtraction + stretching); the raw signal
SNR is extremely low. Descriptors that rely on "natural texture
repeatability" (SIFT/minutiae) have no raw material; global correlation
(NCC/POC) drowns in the structural similarity of the same person's
fingers.

Note: the EH577 author's NCC matcher very likely has the same FAR problem
(no same-person cross-finger test data published).

## 6. The Windows-engine port: the endgame

Timeline: architecture recovered from decompilation (2026-09-13, from the
Animeshz Ghidra archive) → coefficient tables extracted from
EgisTouchFPEngine0575.dll (signature scanning, see
windows-engine-tables.md) → Python replica iterated to perfect offline
separation → ported to C in the driver (`egis0575-matcher.c`, pure C, no
GLib, independently testable).

### Engine pipeline (every parameter traceable to the DLL)
1. Flat-field normalization → **11-orientation ridge matched-filter FIR
   bank** (taps extracted from the DLL) → enhanced image + orientation map
2. Strict local maxima of filter response as interest points + density NMS
   (52% cross-press geometric repeatability)
3. 512-bit top-tier descriptor: 4×4 regions × 32 orientation bins, DLL
   pyramid weights, main orientation = winning filter orientation
4. Hamming nearest neighbor (budget 115/512, no Lowe) → translation-cluster
   RANSAC → angle-mode voting
5. Windows scoring Σ(128−hamming) − unmatched-feature penalty (h/2)
6. **Dual-frame gallery agreement** (defeats position-specific accidental
   alignments)

### Validation numbers
- **Offline** (Python replica; verdict = single-frame best ≥244 AND ≥2
  gallery frames agreeing ≥150): genuine A/C all pass, impostor A/C all
  rejected (including a 438-score impostor killed by the 1-frame agreement
  rule) — FRR 0% (6/6), FAR 0% (0/12)
- **C-port calibration**: the C engine's descriptor bits differ slightly
  from the Python reference (different interpolation path in the oriented
  filter), so the score scale differs — on the same corpus genuine 6/6
  scored 336–470, impostors 0/12 scored 127–280; **threshold 300 splits
  with ≥20 margin**
- **On-hardware integration acceptance** (2026-09-13): right index ×3 =
  622/404/381, all MATCH (early-exit verdict ~2 s); left-index impostor =
  285, correctly rejected (15 below threshold — worth retuning with more
  data or tightening the agree rule later)
- **System level** (full fprintd chain): `probes=1 best_score=1086/300
  => MATCH`

### Differences from the original Windows engine
The original uses threshold 660 (adaptive −80/+60, capped at 1.5×); this
driver uses a fixed 300 plus dual-frame agreement (2 frames × ≥150)
because the C port's score scale differs. The adaptive threshold and the
verification-time template feedback (encrypted registry blob 'AE') were
not ported.

## 7. Stability engineering results (all hardware-verified)

1. The calibration chain (read → reset → upload → POST_CAL polling)
   produces stable imagery
2. Claim-budget recycling + calibration re-upload: budget relaxed from 6
   to 200 frames/claim (stress of one re-upload per 130 ms — 1865 in
   3.5 min — hangs the firmware; 200 is a safe working point)
3. End-of-capture shutdown sequence (topni1 POST_REPEAT, incl. the
   AGC/exposure `71` family): prevents the sensor being stranded in
   continuous-capture mode where presses stop registering (reproduced
   twice)
4. Phantom-presence recovery: background refresh gate std<10 (EH577's
   raw<200 gate is always false on EH575) + unconditional 4-second
   stuck-presence watchdog
5. Graceful shutdown (interface release deferred to the end of the
   capture loop) + SIGINT-friendly test scripts
6. USBDEVFS_RESET soft reset (scripts/reset-sensor.sh) recovers from
   endpoint residue/hangs
7. Frame-read hangs where the 2 s timeout doesn't fire and the SIGINT
   chain fails → only kill -9 + reset; root cause is firmware fatigue,
   the shutdown sequence (item 3) is the main mitigation
8. Long-session progressive desensitization (>10 min polling, coverage
   50%→2–5%) → **in-driver watchdog shipped with v0.2.0**: 10-minute
   prophylactic full re-init + weak-press degradation detection (≥20 frames
   in an 8 s window) → claim recycle + calibration-chain re-run; the hard
   hang case of item 7 still needs the manual USBDEVFS_RESET script

## 8. Upstream issues found

- topni1 `egis0575.c:782` typo `FPI_DEVICE_Egis0575` (should be
  `EGIS0575`): only a warning on GCC ≤13, an error on GCC 14+.
  **To be reported to the topni1 fork.**

## 9. Open items

1. Whether identify (1:N) can be enabled safely — gallery-size limit
   untested
2. Impostor separation margin is only 15 points (285 vs 300) — widen the
   dataset to retune, or tighten the agree rule
3. Automatic USBDEVFS_RESET for hard frame-read hangs (2 s timeouts don't
   even fire, SIGINT chain dead — §7 item 7); the desensitization watchdog
   is already in-driver (§7 item 8), only this extreme case still needs the
   manual scripts/reset-sensor.sh
4. Long-run adaptive matching threshold (Windows has it; not ported)
5. Upstream patch preparation (separate matcher file + protocol docs),
   targeting [libfprint upstream](https://gitlab.freedesktop.org/libfprint/libfprint)
