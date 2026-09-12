/*
 * eval_bz3: offline Bozorth3 matcher evaluation on dumped PGMs.
 *
 * Extracts minutiae exactly the way the egis0575 driver does (lfsparms_V2,
 * remove_perimeter_pts=FALSE, 8bpp, ppmm=0) and scores gallery-vs-probe
 * pairs with Bozorth3, mirroring fpi_print_bz3_match().
 *
 * Usage: eval_bz3 <gallery_dir> <probes_dir>
 *   gallery_dir/gallery-*.pgm vs probes_dir/probe-*.pgm
 */

#include <dirent.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <lfs.h>
#include <bozorth.h>

#define MAX_LOAD 32

typedef struct
{
  unsigned char *data;
  int            width;
  int            height;
} Img;

typedef struct
{
  struct xyt_struct xyt;
  char              name[512];
} Tpl;

static int
cmp_x_y (const void *a, const void *b)
{
  const struct minutiae_struct *ma = a;
  const struct minutiae_struct *mb = b;

  if (ma->col[0] < mb->col[0])
    return -1;
  if (ma->col[0] > mb->col[0])
    return 1;
  if (ma->col[1] < mb->col[1])
    return -1;
  if (ma->col[1] > mb->col[1])
    return 1;
  return 0;
}

static unsigned char *
load_pgm (const char *path, int *w, int *h)
{
  FILE *f = fopen (path, "rb");
  char  magic[8];
  int   maxval;

  if (!f)
    return NULL;

  /* handle both single-line ("P5 W H 255\n", driver) and multi-line
   * ("P5\nW H\n255\n", PIL) headers */
  if (fscanf (f, "%7s", magic) != 1 || strcmp (magic, "P5") != 0)
    {
      fclose (f);
      return NULL;
    }

  if (fscanf (f, "%d %d %d", w, h, &maxval) != 3)
    {
      fclose (f);
      return NULL;
    }

  fgetc (f);        /* single whitespace before raster */

  unsigned char *data = malloc ((size_t) * w * *h);
  if (fread (data, 1, (size_t) * w * *h, f) != (size_t) (* w * *h))
    {
      free (data);
      fclose (f);
      return NULL;
    }

  fclose (f);
  return data;
}

/* Same extraction as egis0575 stage2_minutiae_count + fpi-print.c xyt conversion. */
static int
image_to_xyt (Img *img, struct xyt_struct *xyt)
{
  MINUTIAE     *minutiae = NULL;
  int          *quality_map = NULL, *direction_map = NULL;
  int          *low_contrast_map = NULL, *low_flow_map = NULL, *high_curve_map = NULL;
  unsigned char *binarized = NULL;
  LFSPARMS     *lfsparms = NULL;
  int           map_w = 0, map_h = 0, bw = 0, bh = 0, bd = 0;
  int           r, i, nmin;
  struct minutiae_struct c[MAX_FILE_MINUTIAE];

  lfsparms = malloc (sizeof (LFSPARMS));
  memcpy (lfsparms, &g_lfsparms_V2, sizeof (LFSPARMS));
  lfsparms->remove_perimeter_pts = FALSE;

  r = get_minutiae (&minutiae,
                    &quality_map, &direction_map,
                    &low_contrast_map, &low_flow_map, &high_curve_map,
                    &map_w, &map_h,
                    &binarized, &bw, &bh, &bd,
                    img->data, img->width, img->height,
                    8,
                    0.0,      /* ppmm, same as the driver's FpImage default */
                    lfsparms);

  free (lfsparms);
  free (quality_map); free (direction_map);
  free (low_contrast_map); free (low_flow_map); free (high_curve_map);
  free (binarized);

  if (r || !minutiae)
    return -1;

  nmin = minutiae->num < MAX_BOZORTH_MINUTIAE ? minutiae->num : MAX_BOZORTH_MINUTIAE;

  for (i = 0; i < nmin; i++)
    {
      struct fp_minutia *m = minutiae->list[i];

      lfs2nist_minutia_XYT (&c[i].col[0], &c[i].col[1], &c[i].col[2],
                            m, img->width, img->height);
      c[i].col[3] = sround (m->reliability * 100.0);
      if (c[i].col[2] > 180)
        c[i].col[2] -= 360;
    }

  qsort (c, (size_t) nmin, sizeof (struct minutiae_struct), cmp_x_y);

  for (i = 0; i < nmin; i++)
    {
      xyt->xcol[i] = c[i].col[0];
      xyt->ycol[i] = c[i].col[1];
      xyt->thetacol[i] = c[i].col[2];
    }
  xyt->nrows = nmin;

  free_minutiae (minutiae);
  return nmin;
}

static int
load_dir (const char *dir, const char *prefix, Tpl *out, int max)
{
  DIR           *d = opendir (dir);
  struct dirent *ent;
  char          path[1024];
  int           n = 0;

  if (!d)
    return 0;

  while ((ent = readdir (d)) && n < max)
    {
      if (strncmp (ent->d_name, prefix, strlen (prefix)) != 0)
        continue;

      snprintf (path, sizeof (path), "%s/%s", dir, ent->d_name);
      int w, h;
      unsigned char *data = load_pgm (path, &w, &h);

      if (!data)
        continue;

      Img img = { data, w, h };
      int nm = image_to_xyt (&img, &out[n].xyt);

      free (data);
      if (nm < 0)
        {
          fprintf (stderr, "minutiae failed: %s\n", path);
          continue;
        }

      snprintf (out[n].name, sizeof (out[n].name), "%s", ent->d_name);
      printf ("  [load] %-28s minutiae=%d\n", ent->d_name, nm);
      n++;
    }

  closedir (d);
  return n;
}

int
main (int argc, char **argv)
{
  if (argc != 3)
    {
      fprintf (stderr, "usage: %s <gallery_dir> <probes_dir>\n", argv[0]);
      return 1;
    }

  static Tpl gallery[MAX_LOAD], probes[MAX_LOAD];

  printf ("Gallery:\n");
  int ng = load_dir (argv[1], "gallery-", gallery, MAX_LOAD);
  printf ("Probes:\n");
  int np = load_dir (argv[2], "probe-", probes, MAX_LOAD);

  if (ng == 0 || np == 0)
    {
      fprintf (stderr, "no templates loaded\n");
      return 1;
    }

  printf ("\nXYT debug (first gallery template):\n");
  for (int i = 0; i < (gallery[0].xyt.nrows > 5 ? 5 : gallery[0].xyt.nrows); i++)
    printf ("  x=%d y=%d t=%d\n", gallery[0].xyt.xcol[i], gallery[0].xyt.ycol[i], gallery[0].xyt.thetacol[i]);
  {
    int self_len = bozorth_probe_init (&gallery[0].xyt);
    int self_score = bozorth_to_gallery (self_len, &gallery[0].xyt, &gallery[0].xyt);
    printf ("SELF-MATCH score = %d (nrows=%d)\n", self_score, gallery[0].xyt.nrows);
  }

  printf ("\nBozorth3 scores (probe x best gallery frame):\n");
  for (int p = 0; p < np; p++)
    {
      int probe_len = bozorth_probe_init (&probes[p].xyt);
      int best = 0;

      for (int g = 0; g < ng; g++)
        {
          int score = bozorth_to_gallery (probe_len, &probes[p].xyt, &gallery[g].xyt);
          if (score > best)
            best = score;
        }

      printf ("  %-24s best_score=%d %s\n",
              probes[p].name, best, best >= 20 ? "(≥20)" : "");
    }

  return 0;
}
