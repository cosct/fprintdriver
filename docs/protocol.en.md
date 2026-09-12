# EgisTec EH575 (1c7a:0575) USB Wire Protocol

> **Status: settled.** This document is the protocol baseline used to develop
> the EH575 driver. All entries are cross-validated across four sources;
> entries marked "verified on hardware" were confirmed in live sessions on
> 2026-09-12/13. The driver is published:
> [cosct/libfprint-egis0575](https://github.com/cosct/libfprint-egis0575)
> (branch `egis0575`) · AUR package `libfprint-egis0575`.
> [中文版](protocol.md)

Four-source cross-validation: the topni1 fork (hardware-verified), the
Animeshz reverse-engineering archive (pcap + Ghidra), the championswimmer
EH577 project (2026-06 state), and python-egistec-eh575 (independent
implementation).

## 1. Transport layer

| Item | Value |
|---|---|
| Interface | #0 (vendor-specific 0xFF/0xFF/0x00) |
| Command endpoint | bulk OUT `0x01` |
| Response endpoint | bulk IN `0x82` |
| Interrupt endpoints | EH577 has `0x83`/`0x84`; **unused in a captured Windows session** (§7), safe to ignore |
| Transfer model | one write + one read (command → mirrored-length response), no control transfers |

## 2. Command and response format

- Commands start with ASCII `EGIS` (`45 47 49 53`) followed by
  "register-style" bytes:
  - `60 xx` — status/query
  - `61 xx vv` — register write
  - `62 67 03` / `63 …` (9–18 bytes) — multi-byte parameter blocks
  - `71 …` — parameter block (seen in PRE_FIRST_IMAGE / POST_REPEAT)
  - `97 00 00` — sensor reset (3rd packet of topni1's PRE_RESET)
- Responses start with `SIGE` (`53 49 47 45`) and mirror the command length
  (exceptions below)
- Notable exception commands:
  - `64 14 ec` → read one image frame, **5356 bytes** (103×52)
  - `72 14 ec` → read the calibration block, **5356 bytes**
  - `73 14 ec` → enter calibration-upload mode (7-byte short response),
    after which the host directly writes 5356 bytes of calibration data
- Response status byte: for most commands `resp[5]` carries a
  status/progress value (see the polls in §4)
- Known erratum: the response to `63 01 02 0f 03` is **9 bytes** (topni1's
  table says 7; reading 7 overflows)

## 3. Image geometry (settled)

- Raw frame: 5356 bytes = 103 columns × 52 rows, row-major, 103-byte stride
- **EH575 has no dead columns** (settled 2026-09-12 by dataset analysis):
  over 600 frames, every one of the 103 columns showed 100% non-zero rate
  with cross-frame std 11–20. The 33 hard-zero dead columns of the EH577
  (whose true active area is 70×52) do **not** exist on the EH575; the full
  103-column width is usable directly
- Pixel polarity: fingerprint images use `FPI_IMAGE_COLORS_INVERTED`
- EH575 empty-frame signature: the full frame carries low-intensity content
  (all 5356 pixels in the 15–150 gray range), completely unlike EH577's
  "no-finger frame has only ~173 active pixels". Raw-finger-pixel style
  criteria have no discriminating power on EH575; **coverage after
  warm-background subtraction is the only working presence criterion** (§6)

## 4. Initialization sequences

### A. Calibration flow (topni1's flow; **required** for EH575 imaging — production path)

```
A. Read calibration (re-read on every open, not persisted)
   1. PHASE_1 (16 packets: register config + AGC settings)
   2. Poll 60 2d until resp[5]==0x05
   3. PHASE_3 (2 packets: 62 67 03 / 63 33 03 73 10 01)
   4. Poll 60 35 until resp[5]==0x00
   5. PHASE_5 (4 packets)
   6. 72 14 ec → read the 5356-byte calibration block
   Corrupt-block detection: if the tail has ≥100 identical bytes
   (observed as 0x3f), discard and retry
B. Reset + upload calibration
   7. PRE_RESET (3 packets, last is the 97 00 00 reset)
   8. Poll 60 00 until resp[5]!=0x00 (reset complete)
   9. POST_RESET (13 packets)
  10. 73 14 ec → write 5356 bytes of calibration data → read 7-byte ack
  11. POST_CALIBRATION (20 packets, last is 64 14 ec which also
      collects one warm-up frame)
```

### B. PRE_INIT/POST_INIT flow (EH577's route; **does not work** on EH575)

The Animeshz/championswimmer alternative: PRE_INIT (29 packets) →
POST_INIT (17 packets + frame). EH575 semantics: when POST_INIT[1]
(`60 01 fc`) answers `SIGE 01 01 01`, the device is asking for
pre-initialization — jump back and re-run PRE_INIT (this is EH575's
intended error handling).

**Verified on hardware, 2026-09-12**: on route B every command is answered
correctly and `64 14 ec` reliably returns 5356 bytes, but the frame content
is **all zeros** — calibration upload is a hard requirement for imaging on
EH575. topni1's calibration flow is essentially PRE_INIT's register writes
with the calibration acquisition split out and made explicit. Also
verified: sending bare `73 14 ec` (without the 5356-byte payload) yields a
507 ms all-zero response the first time and deadlocks the transport on the
second. In the driver, route B is kept only behind
`EGIS0575_SKIP_CALIBRATION=1` for A/B experiments. The Python
implementation has a third equivalent sequence (8-packet rearm).

## 5. Capture loop

- Frame acquisition: PRE_FIRST_IMAGE (25 packets, first loop only) →
  `64 14 ec` frame → REPEAT (8 packets) + `64 14 ec` frame ×N →
  POST_REPEAT (9 packets)
- **The shutdown sequence must be sent when capture ends** (topni1's
  POST_REPEAT, including the AGC/exposure `71` family): it prevents the
  sensor from being stranded in continuous-capture mode where presses stop
  registering (reproduced twice on hardware)
- Windows' frame loop likewise uses REPEAT (8 packets), not POST_CAL
  (20 packets) — see §7

## 6. Finger presence

- Hardware presence: poll `60 01` and test `resp[5] > 0x03` per topni1 —
  **unreliable**. On hardware it never reacted to presses (1199 polls,
  always 0x01), and Windows does not rely on it either (§7)
- Software criteria, compared:
  - topni1: mean squared adjacent-pixel difference in the open interval
    (100, 1000)
  - championswimmer (adopted by this driver): after warm-background
    subtraction, coverage ≥18% and intensity ≥10 (presence); ≥25%/≥20
    (usable). Validated on an EH575 dataset: empty frames peaked at 17%
    coverage vs finger frames bottoming at 19% — a clean margin
    (56 finger / 450 empty frames)
  - python: np.std > 31.0

## 7. Windows online behavior, observed (2026-09-13, vmware-0.pcap, 57 s session)

| Window | Bus behavior | Takeaway for the driver |
|---|---|---|
| 0 s | Init: calibration upload (5356 B OUT) + POST_CAL header (15 packets) | Calibration happens once per session |
| 10 s | 6-packet keepalive (60 00/01/40 66 + 61 0c/0b/0a = POST_REPEAT tail family) | Keeps the sensor armed while idle |
| 10–50 s | **Fully silent (zero polling)** | Windows never babysits the sensor; it only captures during UI sessions |
| 50–56 s | Auth session: REPEAT light loop at full speed (~500 packets/s, 8+1 per frame) | The frame loop is REPEAT (8), not POST_CAL (20) |

Conclusion: Windows keeps the sensor healthy via a **duty cycle below
0.1%** (full-speed capture only for a few seconds while the auth UI is
active). fprintd semantics require continuous finger-state reporting, so
"don't babysit" cannot be copied. This driver's adaptation: slow 230 ms
frame polling (~7% duty cycle) + USB-reset recovery for long-session
degradation (`scripts/reset-sensor.sh`; an in-driver automatic watchdog
is still on the todo list, see §9).

## 8. Known pitfalls (all verified on hardware, 2026-09-12/13)

1. **Per-claim quota on 5356-byte bulk reads**: as reported for topni1.
   Verified countermeasure: after releasing and re-claiming the interface,
   **re-upload calibration** (POST_RESET → 73 14 ec → write 5356 B → ack →
   POST_CAL): 156 recycles in 20 s with zero timeouts. The per-claim
   budget was relaxed from 6 frames to 200; pushing harder (1865
   re-uploads in 3.5 min) hangs the firmware — see comparison.md §7
2. **Bulk endpoint FIFO residue desynchronizes the next session**: if a
   process exits mid-response, the next process times out on the very
   first PHASE_1 packet. Countermeasure: `USBDEVFS_RESET` soft reset
   (scripts/reset-sensor.sh; works with the uaccess ACL, no root needed)
3. Calibration-block reads can be corrupt (≥100 identical tail bytes,
   observed 0x3f) — the driver detects this
4. No calibration → all-zero frames (§4B); bare `73 14 ec` deadlocks the
   transport on the second attempt
5. `63 01 02 0f 03` responds with 9 bytes (§2)
6. **Progressive desensitization under long continuous polling**: after
   >10-minute-scale continuous polling, press coverage decays from 50% to
   2–5% — `USBDEVFS_RESET` restores it immediately; automatic in-driver
   detection + recovery is pending

## 9. System-level acceptance (2026-09-13 00:39)

With the sensor healthy, the full fprintd chain: `probes=1
best_score=1086/300 => MATCH`, coverage 51%. Early-exit verdict (~2 s),
multi-probe collection, and the dual-frame agreement rule all work (see
windows-engine-tables.md for the matcher and its threshold calibration).

## 10. Not yet reverse-engineered

- The semantics of `73 14 ec` answering only a 7-byte short response in
  the EH577 PRE_INIT context
- The calibration-data persistence protocol (Windows behavior with
  storage; mentioned in topni1's comments)
- Register semantics of `71 …` / `97 00 00`

(The interrupt-endpoint 0x83/0x84 question was answered by §7: Windows
does not use them.)

## Reference implementation index

| Implementation | Path | Notes |
|---|---|---|
| topni1 (EH575) | `refs/topni1-libfprint/libfprint/drivers/egis0575.{c,h}` | Complete calibration flow, swipe model |
| championswimmer (EH577, authoritative b19955e) | `refs/libfprint-eh577/refs/libfprint/libfprint/drivers/egis0577.{c,h}` | Press-architecture base, 70×52 |
| Animeshz original patch (2021) | `refs/EgisTec-EH575/libfprint.patch` | pcap + Ghidra in `findings/` of the same repo |
| python standalone | `refs/python-egistec-eh575/open-fprintd-eh575/egis_driver/egis_driver.py` | Cross-validates sequence equivalence |

Reference repos are not distributed with this repository (see the root
README); fetch them at the paths above.
