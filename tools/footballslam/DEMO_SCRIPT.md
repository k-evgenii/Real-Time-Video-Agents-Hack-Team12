# Traffic demo script (~2:30)

Voice only. Leave the two slots empty until the integrator pastes a real track from `track_alerts.json` and a real episode from `anomaly_report.md`. Numbers in parentheses are examples from the script, not measurements. Do not speak them as if they were scored on this archive.

**[0:00]** "Traffic cameras produce hours of nothing and seconds that matter. We built two detectors that find those seconds with no labels and no training, on any camera in this archive."

**[0:20 Trajectories, I-24]** *(overlay + flow map)* "Every vehicle gets a constant-velocity Kalman filter; the arrows are the lane flow the system learned in 20 seconds. Green means physics agrees. There — TODO(trajectory-1)." *(example: vehicle 14, predicted here, actually here; Mahalanobis 18 against a threshold this camera set for itself at 11; three frames → hard braking.)* *(If the clip is quiet, use the Simulate toggle: "and here's an injected wrong-way track — the flow field catches it in five frames; it's labelled simulated.")*

**[1:05 Episodes]** *(timeline + Episodes tab)* "Second layer, coarser: Cosmos Reason already described every segment; a small LLM pass converts that to a fixed grammar — flow, vehicles, events. Runs of the same flow state become episodes. Per camera we robust-z-score ten plain features and rank episodes by nearest-neighbour distance. TODO(episode-1). Independently, in Cosmos's visual-embedding space, we ask the same question of that episode. That view never saw our labels." *(example: vehicles 2.9σ above this camera's median, two risk events, ended in a stop; the same episode is the furthest from its neighbours.)*

**[1:50 Generalise]** *(neighborhood cam, then the dashcam tab)* "Same code, residential street: the thresholds re-learn themselves — nothing is tuned per camera. On the moving dashcam we switch the physics layer off and keep the episode layer; the system knows what it can't claim."

**[2:15 Close]** "Limits: image-space physics, occlusions, and segment-length resolution. But today: two unsupervised anomaly detectors over the whole archive, explainable to the sigma, 'find more like this' across cameras. Thank you."
