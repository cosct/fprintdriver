/*
 * EgisTec EH575 matcher: port of the Windows-engine replica validated in
 * the fprintdriver research project.  Copyright (C) 2026 cosct <cosct@outlook.com>
 * Python (scripts/egis_matcher.py) validated in
 * https://github.com/cosct/fprintdriver (docs/windows-engine-tables.md).
 *
 * Pipeline: flat-field → 11-orientation ridge matched filter bank (taps
 * extracted from EgisTouchFPEngine0575.dll) → interest points on filter
 * response → 512-bit orientation-histogram descriptors (DLL pyramid
 * weights) → Hamming NN + translation-cluster + angle-mode scoring.
 *
 * Pure C, no GLib: also compiled into the standalone cross-validation
 * harness (tools/egis0575-matcher-test.c).
 *
 * Copyright (C) 2026 fprintdriver research contributors
 * LGPL-2.1-or-later
 */

#pragma once

#include <stdint.h>

#define EGIS0575_M_DESC_BYTES 64          /* 512-bit top-tier descriptor */
#define EGIS0575_M_MAX_FEATURES 120
#define EGIS0575_M_MIN_FEATURES 11
#define EGIS0575_M_MIN_MATCHED 5
#define EGIS0575_M_HAMMING_BUDGET 115     /* of 512 */
#define EGIS0575_M_ANGLE_TOL_DEG 12.0
#define EGIS0575_M_POS_TOL_PX 8
#define EGIS0575_M_N_ORIENT 11

/* Verdict thresholds. The C engine's descriptor bits differ slightly from
 * the Python reference (different interpolation path in the oriented
 * filter), so its score scale differs: validated on the same capture
 * corpus, genuine 6/6 scored 336-470 and impostors 0/12 scored 127-280
 * (https://github.com/cosct/fprintdriver/blob/master/docs/windows-engine-tables.md).
 * Threshold 300 splits with ≥20 margin. */
#define EGIS0575_M_MATCH_THRESHOLD 300
#define EGIS0575_M_AGREE_SCORE 150
#define EGIS0575_M_AGREE_FRAMES 2

typedef struct
{
  uint16_t x, y;
  uint8_t  orient;                       /* winning orientation index 0..10 */
  uint8_t  desc[EGIS0575_M_DESC_BYTES];  /* 512 bits, MSB-first packing */
} Egis0575MFeature;

typedef struct
{
  int             n;
  Egis0575MFeature f[EGIS0575_M_MAX_FEATURES];
} Egis0575MFeatureSet;

/* Extract features from a processed grayscale image (w×h, row-major). */
void egis0575_m_extract (const uint8_t *img, int w, int h,
                         Egis0575MFeatureSet *out);

/* Windows-style score: Σ(128−h) over consistent matches minus the
 * unexplained-feature penalty. Returns n_good (votes) via *votes_out
 * when non-NULL. */
int egis0575_m_score (const Egis0575MFeatureSet *probe,
                      const Egis0575MFeatureSet *gallery,
                      int *votes_out);
