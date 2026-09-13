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

/* Read one header token, skipping whitespace and '#' comment lines. */
static int
pgm_next_token (FILE *f, char *buf, size_t len)
{
  int c;

  for (;;)
    {
      c = fgetc (f);
      if (c == EOF)
        return 0;
      if (c == '#')
        {
          while (c != EOF && c != '\n')
            c = fgetc (f);
          continue;
        }
      if (c != ' ' && c != '\t' && c != '\r' && c != '\n')
        break;
    }

  size_t n = 0;
  while (c != EOF && c != ' ' && c != '\t' && c != '\r' && c != '\n' && c != '#')
    {
      if (n + 1 < len)
        buf[n++] = (char) c;
      c = fgetc (f);
    }
  if (c != EOF)
    ungetc (c, f);  /* leave the terminator for the caller (CRLF handling) */
  buf[n] = '\0';
  return n > 0;
}

static unsigned char *
load_pgm (const char *path, int *w, int *h)
{
  FILE *f = fopen (path, "rb");
  char tok[32];
  int maxv;

  if (!f)
    return NULL;
  if (!pgm_next_token (f, tok, sizeof (tok)) || strcmp (tok, "P5") != 0)
    {
      fclose (f);
      return NULL;
    }
  if (!pgm_next_token (f, tok, sizeof (tok)) || (*w = atoi (tok)) <= 0 ||
      !pgm_next_token (f, tok, sizeof (tok)) || (*h = atoi (tok)) <= 0 ||
      !pgm_next_token (f, tok, sizeof (tok)) || (maxv = atoi (tok)) != 255)
    {
      fclose (f);
      return NULL;
    }
  /* consume the single whitespace terminator after maxval (tolerate CRLF) */
  {
    int t = fgetc (f);
    if (t == '\r')
      {
        int t2 = fgetc (f);
        if (t2 != '\n')
          ungetc (t2, f);
      }
  }
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
      fprintf (stderr, "usage: %s features <pgm> | score <gallery.pgm> <probe.pgm>\n", argv[0]);
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
      int w1, h1, w2, h2;
      unsigned char *i1 = load_pgm (argv[2], &w1, &h1);
      unsigned char *i2 = load_pgm (argv[3], &w2, &h2);
      if (!i1 || !i2)
        {
          free (i1);
          free (i2);
          fprintf (stderr, "load failed\n");
          return 1;
        }
      static Egis0575MFeatureSet f1, f2;
      egis0575_m_extract (i1, w1, h1, &f1);
      free (i1);
      egis0575_m_extract (i2, w2, h2, &f2);
      free (i2);
      int votes = 0;
      int score = egis0575_m_score (&f2, &f1, &votes);
      printf ("features=%d/%d votes=%d score=%d\n", f1.n, f2.n, votes, score);
      return 0;
    }

  fprintf (stderr, "usage: %s features <pgm> | score <gallery.pgm> <probe.pgm>\n", argv[0]);
  return 1;
}
