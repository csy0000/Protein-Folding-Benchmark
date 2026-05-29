# Scoring Metrics

The benchmark writes per-prediction score CSVs with lDDT-C-alpha, TM-align/USalign metrics, C-alpha RMSD diagnostics, and GDT_TS.

## lDDT-C-alpha

`lddt_ca` is the primary ranking metric in per-target and all-target summaries. It is computed from matched C-alpha atoms with the configured local-distance cutoff.

## TM-score and RMSD

When `--use-tmalign` is enabled, `scripts/02_score_predictions.py` resolves USalign/TMalign and records:

- `tmalign_tm_score_ref`: TM-score normalized by reference length.
- `tmalign_tm_score_pred`: TM-score normalized by prediction length.
- `tmalign_rmsd`: alignment RMSD reported by the external aligner.
- `ca_rmsd`: repository C-alpha RMSD diagnostic from the configured residue matching mode.

TM-score normalized by reference length is the secondary ranking metric.

## GDT_TS

GDT_TS is enabled by default in the scoring scripts and can be disabled with `--no-gdt-ts`.

Per-prediction score CSVs include:

- `gdt_ts`: GDT_TS on a 0-1 scale.
- `gdt_ts_percent`: GDT_TS on a 0-100 scale.
- `gdt_p1`, `gdt_p2`, `gdt_p4`, `gdt_p8`: fractions under the 1, 2, 4, and 8 Angstrom cutoffs.
- `gdt_ts_method`: the scorer used.
- `gdt_ts_error`: parse or scorer errors, kept blank on success.

By default, `--gdt-ts-method auto` first uses the external `TMscore` executable when it is available in the scoring environment. This is recorded as `external_tmscore`. If `TMscore` is unavailable, scoring falls back to an internal iterative C-alpha superposition implementation recorded as `internal_iterative_ca`.

The external `TMscore` value is preferred for reported benchmark tables. The internal fallback is intended to keep local smoke tests usable when external scoring binaries are missing; it is not a formal CASP/LGA replacement.

## Summary Columns

Per-target model summaries include `best_gdt_ts`, `best_gdt_ts_percent`, `mean_gdt_ts`, and `mean_gdt_ts_percent`. All-target summaries include `mean_best_gdt_ts` and `mean_best_gdt_ts_percent`. Consolidated all-model exports include per-row GDT_TS values and model-level mean/best GDT_TS values.
