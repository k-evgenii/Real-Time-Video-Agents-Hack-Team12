# Anomaly report

How to read this: episodes are compared only with other episodes from the same camera. A score near 1 is typical. A score at or above 2.5 is flagged. Lane A is the episode layer. Lane B is left for trajectory alerts.

## Lane A

| attack | t0–t1 | s_feat | s_emb | reasons |
| --- | --- | --- | --- | --- |
| pie_e001 | 0.0–30.0 | 1.411 | 3.092 | max vehicles 2.0σ above camera median (5.00 vs 3.50); duration 1.3σ above camera median (30 s vs 15 s); segments 1.3σ above camera median (6 vs 3) |
| pie_e002 | 0.0–5.0 | 1.079 | 2.074 | flow code 1.3σ below camera median (free vs dense); mean pedestrians 1.0σ below camera median (1.00 vs 1.50); duration 0.9σ below camera median (5 s vs 15 s) |
| pie_e006 | 20.0–30.0 | 0.931 | 1.314 | flow code 1.3σ below camera median (free vs dense); ended-by code 0.7σ above camera median (2 vs 1); max vehicles 0.7σ above camera median (4.00 vs 3.50) |
| pie_e003 | 5.0–10.0 | 0.972 | 0.686 | mean pedestrians 1.0σ above camera median (2.00 vs 1.50); duration 0.9σ below camera median (5 s vs 15 s); segments 0.9σ below camera median (1 vs 3) |
| pie_e004 | 10.0–30.0 | 1.011 | 0.551 | mean vehicles 0.8σ below camera median (2.50 vs 3.25); flow code 0.7σ above camera median (stopped vs dense); ended-by code 0.7σ above camera median (2 vs 1) |

## Lane B

| attack | t0–t1 | s_feat | s_emb | reasons |
| --- | --- | --- | --- | --- |
| — | — | — | — | no attacks |


Labels are the W&B repair of existing captions. Native re-ingest of the two I-24 demo chunks has not written FLOW/SCENE lines yet, so nothing was overridden.
