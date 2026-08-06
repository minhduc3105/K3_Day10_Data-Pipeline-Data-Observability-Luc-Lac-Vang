# Phase 1 Baseline Report

## Source

| Field | Value |
| --- | --- |
| Source API | Crossref REST API |
| Query | `agentic retrieval augmented generation large language model` |
| Filter | `from-pub-date:2026-02-07,has-abstract:true` |
| Raw records | 24 |
| Clean records | 24 |
| Raw response | `D:\Lab_VinUni\day10\K3_Day10_Data-Pipeline-Data-Observability-Luc-Lac-Vang\data\raw\crossref_response.json` |
| Raw records path | `D:\Lab_VinUni\day10\K3_Day10_Data-Pipeline-Data-Observability-Luc-Lac-Vang\data\raw\crossref_records.json` |

## Evaluation

| Metric | Value |
| --- | ---: |
| Samples | 24 |
| Retrieval hit rate | 1.0000 |
| Mean token F1 | 1.0000 |
| Judge accuracy | 1.0000 |
| Mean judge score | 5 |

## Data Quality

Overall status: PASS

| Check | Status | Details |
| --- | --- | --- |
| row_count_positive | PASS | `{'total_rows': 24}` |
| paper_id_not_null | PASS | `{'non_null': 24, 'total_rows': 24}` |
| paper_id_unique | PASS | `{'duplicate_rows': 0}` |
| title_not_blank | PASS | `{'non_blank': 24, 'total_rows': 24}` |
| summary_min_length | PASS | `{'min_chars': 40, 'short_rows': 0}` |
| freshness_threshold | PASS | `{'threshold_days': 180, 'stale_rows': 0}` |

## Freshness

| Field | Value |
| --- | --- |
| Latest published | 2026-08-01 |
| Oldest published | 2026-02-12 |
| Stale rows | 0 |
| Total rows | 24 |
| Is fresh | True |
