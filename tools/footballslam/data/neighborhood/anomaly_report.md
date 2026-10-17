# Anomaly report

How to read this: episodes are compared only with other episodes from the same camera. A score near 1 is typical. A score at or above 2.5 is flagged. Lane A is the episode layer. Lane B is left for trajectory alerts.

## Lane A

| attack | t0–t1 | s_feat | s_emb | reasons |
| --- | --- | --- | --- | --- |
| neighborhood_e007 | 20.0–30.0 | 0.757 | 1.686 | ended-by code 5.0σ above camera median (2 vs 0); duration 0.0σ above camera median (10 s vs 10 s); segments 0.0σ above camera median (2 vs 2) |
| neighborhood_e001 | 5.0–20.0 | 1.114 | 1.237 | mean vehicles 5.0σ below camera median (0.33 vs 1.00); mean pedestrians 5.0σ above camera median (0.67 vs 0.00); flow code 5.0σ below camera median (free vs moderate) |
| neighborhood_e006 | 5.0–15.0 | 1.0 | 1.008 | mean vehicles 5.0σ below camera median (0.50 vs 1.00); flow code 5.0σ below camera median (free vs moderate); duration 0.0σ above camera median (10 s vs 10 s) |
| neighborhood_e005 | 0.0–5.0 | 0.892 | 1.0 | duration 0.7σ below camera median (5 s vs 10 s); segments 0.7σ below camera median (1 vs 2); mean vehicles 0.0σ above camera median (1.00 vs 1.00) |
| neighborhood_e002 | 20.0–30.0 | 1.232 | 0.409 | mean vehicles 5.0σ below camera median (0.50 vs 1.00); mean pedestrians 5.0σ above camera median (0.50 vs 0.00); ended-by code 5.0σ above camera median (2 vs 0) |

## Lane B

| attack | t0–t1 | s_feat | s_emb | reasons |
| --- | --- | --- | --- | --- |
| — | — | — | — | no attacks |


Labels are the W&B repair of existing captions. Native re-ingest of the two I-24 demo chunks has not written FLOW/SCENE lines yet, so nothing was overridden.
