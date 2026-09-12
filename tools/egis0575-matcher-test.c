/*
 * Cross-validation harness: run the C matcher port on dumped PGMs and
 * print features/scores to compare against scripts/egis_matcher.py.
 *
 * Usage:
 *   egis0575-matcher-test features <image.pgm>
 *   egis0575-matcher-test score <gallery.pgm> <probe.pgm>
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../libfprint/libfprint/drivers/egis0575-matcher.h"

static unsigned char *
load_pgm (const char *path, int *w, int *h)
{
  FILE *f = fopen (path, "rb");
  char magic[8];
  int maxv;

  if (!f)
    return NULL;
  if (fscanf (f, "%7s", magic) != 1 || strcmp (magic, "P5") != 0)
    {
      fclose (f);
      return NULL;
    }
  if (fscanf (f, "%d %d %d", w, h, &maxv) != 3)
    {
      fclose (f);
      return NULL;
    }
  fgetc (f);
  size_t npix = (size_t) * w * *h;
  unsigned char *data = malloc (npix);
  if (!data || fread (data, 1, npix, f) != npix)
    {
      free (data);
      fclose (f);
      return NULL;
    }
  fclose (f);
  return data;
}

int
main (int argc, char **argv)
{
  if (argc < 3)
    {
      fprintf (stderr, "usage: %s features <pgm> | score <pgm1> <pgm2>\n", argv[0]);
      return 1;
    }

  if (strcmp (argv[1], "features") == 0)
    {
      int w, h;
      unsigned char *img = load_pgm (argv[2], &w, &h);
      if (!img)
        {
          fprintf (stderr, "load failed\n");
          return 1;
        }
      static Egis0575MFeatureSet fs;
      egis0575_m_extract (img, w, h, &fs);
      free (img);
      printf ("n=%d\n", fs.n);
      for (int i = 0; i < fs.n; i++)
        {
          printf ("%d %d %d ", fs.f[i].x, fs.f[i].y, fs.f[i].orient);
          for (int b = 0; b < EGIS0575_M_DESC_BYTES; b++)
            printf ("%02x", fs.f[i].desc[b]);
          printf ("\n");
        }
      return 0;
    }

  if (strcmp (argv[1], "score") == 0 && argc == 4)
    {
      int w, h;
      unsigned char *i1 = load_pgm (argv[2], &w, &h);
      unsigned char *i2 = load_pgm (argv[3], &w, &h);
      if (!i1 || !i2)
        {
          free (i1);
          free (i2);
          fprintf (stderr, "load failed\n");
          return 1;
        }
      static Egis0575MFeatureSet f1, f2;
      egis0575_m_extract (i1, w, h, &f1);
      free (i1);
      egis0575_m_extract (i2, w, h, &f2);
      free (i2);
      int votes = 0;
      int score = egis0575_m_score (&f2, &f1, &votes);
      printf ("features=%d/%d votes=%d score=%d\n", f1.n, f2.n, votes, score);
      return 0;
    }

  return 1;
}
