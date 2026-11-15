# scoring/ (Noor)

Checks whether what the tool shows is true, and writes `data/scoreboard.json` for the site.
Built to the spec in `team_update_2026-11-15.md` ("Noor: scoring").

```
python scoring/build_scoreboard.py          # rebuild data/scoreboard.json
python scoring/build_scoreboard.py --plot   # also rebuild scoring/figures/*.png
```

It only reads finished files in `data/`, so re-run it whenever someone pushes new target files.
Every test is described in the docstring at the top of `build_scoreboard.py`.

## The three checks

| Check | Question | Reads |
|---|---|---|
| 1. Target motion | Does the measured motion match the catalog? `agrees` / `tension` / `disagrees`, or `not_measurable` (e.g. saturated) | `manifest.json` |
| 2. Target error bars | Are the target's error bars honest? Constant offset reported separately | `manifest.json` (every image and visit) |
| 3. Field stars | Same tests on Gaia stars nobody tuned the tool on | `objects.json` |

Thresholds: `agrees` p >= 0.05, `tension` 0.0027 <= p < 0.05, `disagrees` p < 0.0027 (3 sigma, as in the verdicts).

## `data/scoreboard.json` (what the site reads)

- `headline`: plain sentences, ready to show as-is in the "How accurate is this?" panel.
- `method`: one line per test, for the same panel.
- `summary`: field-star pulls over all targets, an error-bar assessment, and `disagreeing_objects`.
- `targets[]`, one per target:
  - `name`, `verdict` (copied from the manifest), `field_size_px`
  - `motion`: measured and catalog motion, `z` per axis, `p_value`, `agreement`, total speed, shift over the data in pixels. `{"agreement": "not_measurable", "reason": ...}` when there is no measured motion.
  - `target_position`: `constant_offset` (px, arcsec), `image_pulls`, `random_part` (image pulls with each visit's mean removed), `visit_pulls`, `visit_pulls_offset_removed`, `error_bars` (plain phrase)
  - `field_stars`: `null` until the target has an `objects.json`. Otherwise counts, `recovered_by_g`, pulls for scored and reference stars, `agreement_counts`, `disagreeing`, and
    - `objects[]`: `{name, agreement, chi2, n_visits, dof, p_value, g_mag, role}`. Join to `objects.json` and `overlays.json` by `name`. `role` is `scored`, `reference` (sets the error bars, agrees by construction), `blended` or `not_scored`; `agreement` is `null` when the star has no usable visit.
