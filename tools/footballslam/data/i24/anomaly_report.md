# Anomaly report

How to read this: episodes are compared only with other episodes from the same camera. A score near 1 is typical. A score at or above 2.5 is flagged. Lane A is the episode layer. Lane B is left for trajectory alerts.

## Lane A

| attack | t0–t1 | s_feat | s_emb | reasons |
| --- | --- | --- | --- | --- |
| i24_e007 | 0.0–5.0 | 1.0 | 4.923 | max vehicles 0.7σ below camera median (0.00 vs 4.00); mean vehicles 0.7σ below camera median (0.00 vs 3.25); duration 0.0σ above camera median (5 s vs 5 s) |
| i24_e010 | 25.0–30.0 | 1.664 | 2.975 | flow code 5.0σ above camera median (moderate vs free); ended-by code 5.0σ above camera median (2 vs 0); max vehicles 0.7σ below camera median (0.00 vs 4.00) |
| i24_e008 | 5.0–10.0 | 0.769 | 3.279 | flow code 5.0σ above camera median (moderate vs free); max vehicles 0.7σ below camera median (0.00 vs 4.00); mean vehicles 0.7σ below camera median (0.00 vs 3.25) |
| i24_e009 | 10.0–25.0 | 1.949 | 2.033 | duration 5.0σ above camera median (15 s vs 5 s); segments 5.0σ above camera median (3 vs 1); max vehicles 0.7σ below camera median (0.00 vs 4.00) |
| i24_e003 | 10.0–30.0 | 1.566 | 0.502 | duration 5.0σ above camera median (20 s vs 5 s); segments 5.0σ above camera median (4 vs 1); ended-by code 5.0σ above camera median (2 vs 0) |

## Lane B

| attack | t0–t1 | s_feat | s_emb | reasons |
| --- | --- | --- | --- | --- |
| — | — | — | — | no attacks |


Labels are the W&B repair of existing captions. Native re-ingest of the two I-24 demo chunks has not written FLOW/SCENE lines yet, so nothing was overridden.
