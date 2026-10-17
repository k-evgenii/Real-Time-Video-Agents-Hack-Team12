# Speaker crib

1. **Why no trained model.** Nothing in the archive is labelled "anomalous". Robust z plus k-nearest neighbours needs no labels and no camera-specific weights. The reason on screen is the features with the largest robust z, which a judge can check against the clip.
2. **Why scores are per camera.** Each episode is compared only with other episodes from that same camera. A highway median full of cars and a residential median of one car are both ordinary for themselves. The threshold is that camera's own neighbour-distance median.
3. **Why the dashcam has no Kalman layer.** `pie_cam-3` moves with the car. A constant-velocity model in the image would describe the camera, so `map_mode` is `NONE`, the flow panel stays hidden, and only the episode layer runs.
4. **What the Simulate toggle means.** It injects a stop, swerve, or reverse into a real track and loads `map_sim.json`. The picture is labelled simulated. It is a labelled injection for a quiet highway, and it is separate from a detected event.
