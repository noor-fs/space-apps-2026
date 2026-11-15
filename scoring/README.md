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
| 3. Field stars | Gaia stars nobody tuned the tool on. **Motion test** (main): does each star move as Gaia predicts, after removing its constant offset? **Position test**: is it where Gaia predicts, allowing for the crowding floor (`absolute_floor_px`)? Crowded stars (`crowded_by`) reported separately | `objects.json` |

Fields with a crowding floor above 0.25 px (R Draconis, glow) are scored in their own entry but left out of the pooled totals and headline.

Thresholds: `agrees` p >= 0.05, `tension` 0.0027 <= p < 0.05, `disagrees` p < 0.0027 (3 sigma, as in the verdicts).

## `data/scoreboard.json` (what the site reads)

- `headline`: plain sentences, ready to show as-is in the "How accurate is this?" panel.
- `method`: one line per test, for the same panel.
- `summary`: field-star pulls over all targets, an error-bar assessment, and `disagreeing_objects`.
- `targets[]`, one per target:
  - `name`, `verdict` (copied from the manifest), `field_size_px`
  - `motion`: measured and catalog motion, `z` per axis, `p_value`, `agreement`, total speed, shift over the data in pixels. `{"agreement": "not_measurable", "reason": ...}` when there is no measured motion.
  - `target_position`: `constant_offset` (px, arcsec), `image_pulls`, `random_part` (image pulls with each visit's mean removed), `visit_pulls`, `visit_pulls_offset_removed`, `error_bars` (plain phrase)
  - `field_stars`: `null` until the target has an `objects.json`. Otherwise `absolute_floor_px`, counts, `recovered_by_g`, `motion_test` and `absolute_test` (pulls overall, uncrowded, crowded and for reference stars, `agreement_counts`, `disagreeing`), `in_pooled_totals`, and
    - `objects[]`: `{name, agreement, chi2, dof, p_value, agreement_absolute, chi2_absolute, n_visits, g_mag, crowded, role}`. Join to `objects.json` and `overlays.json` by `name`. **`agreement` is the motion test** (show this one: "moves as Gaia predicts"); `agreement_absolute` is the position test. `role` is `scored`, `reference` (sets the error bars, agrees by construction), `blended` or `not_scored`; agreements are `null` when the star has fewer than 2 usable visits.
