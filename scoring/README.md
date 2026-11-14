# scoring/ (Noor)

Checks whether what the tool shows is true, and writes `data/scoreboard.json` for the site.

```
python scoring/build_scoreboard.py          # rebuild data/scoreboard.json
python scoring/build_scoreboard.py --plot   # also rebuild scoring/figures/*.png
```

It only reads finished files in `data/`, so re-run it whenever someone pushes new target files.

## The three checks

| Check | Question it answers | Reads |
|---|---|---|
| Motion | Does the motion SPHEREx measured match the catalog (Gaia, CatWISE)? | `manifest.json` |
| Target position | Are the error bars honest, and how far are positions from the catalog? | `manifest.json` (every single image) |
| Field stars | Same test on every other catalog star in the field | `objects.json` (Yara T, when it exists) |

Detections in no catalog (`candidates.json`, Sifna) are counted by label when the file exists.

Details of each test are in the docstring at the top of `build_scoreboard.py`.

## `data/scoreboard.json` (what the site reads)

- `headline`: 2 to 4 plain sentences, ready to show as-is.
- `targets[]`: one entry per target, with:
  - `verdict` (copied from the manifest)
  - `motion`: measured and catalog motion, `z` per axis, `p_value`, `agreement` (`agrees`, `tension` or `disagrees`), total speed and the shift in pixels over the baseline
  - `target_position`: `constant_offset` (px and arcsec), `random_pulls` (should be about 68% within 1 sigma and 95% within 2), `raw_pulls`
  - `field_stars` and `candidates`: `null` until those files exist
- `field_stars_all`: field-star pulls over all targets together.
- `method`: one-line descriptions of each test, for the "How accurate is this?" panel.
