# Corruption Comparison Report

| State | Samples | Retrieval hit rate | Mean token F1 | Field-aware score | Judge accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 10 | 1.0000 | 0.1515 | 0.6833 | 0.9000 |
| Corrupted | 10 | 0.6000 | 0.1202 | 0.3819 | 0.7000 |
| Repaired | 10 | 1.0000 | 0.1560 | 0.6831 | 0.9000 |

## Data quality and freshness

| State | Valid | Rows | Duplicate rows | Stale rows | Missing dates |
| --- | --- | ---: | ---: | ---: | ---: |
| Baseline | True | 197 | 0 | 172 | 6 |
| Corrupted | False | 198 | 1 | 173 | 6 |
| Repaired | True | 197 | 0 | 172 | 6 |

Frozen test-set SHA-256: `c0302193f620f9de2618a45b2fb24f8858f781482309b4b680286628182b54bb`

![Comparison chart](corruption_metrics.svg)
