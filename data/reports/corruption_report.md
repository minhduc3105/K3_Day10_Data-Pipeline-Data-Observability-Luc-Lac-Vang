# Corruption Impact Report

## Metrics Comparison

| Metric | Baseline | Corrupted | Repaired |
| --- | ---: | ---: | ---: |
| Samples | 24 | 24 | 24 |
| Retrieval hit rate | 1.0000 | 0.5000 | 1.0000 |
| Mean token F1 | 1.0000 | 0.5104 | 1.0000 |
| Judge accuracy | 1.0000 | 0.5000 | 1.0000 |
| Mean judge score | 5 | 3 | 5 |

## Quality Status

| State | Overall | Total rows |
| --- | --- | ---: |
| Corrupted | FAIL | 23 |
| Repaired | PASS | 24 |

## Freshness Status

| State | Is fresh | Stale rows | Latest published |
| --- | --- | ---: | --- |
| Corrupted | False | 5 | 2026-07-03 |
| Repaired | True | 0 | 2026-08-01 |

## Interpretation

The corrupted run intentionally removes recent papers, damages summaries and titles, adds stale dates, and duplicates rows. The repaired run rebuilds the dataset from raw Crossref records, so metrics and quality checks should move back toward the baseline.
