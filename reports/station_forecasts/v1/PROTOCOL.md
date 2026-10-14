# Phase 2 protocol — fixed before fitting or final-test evaluation

Synthetic data only. Separate artifacts per station. No frozen module imported for
training and no original artifact overwritten. Scope: forecasting, not a live service.

Train January–August2025, validation September–October, final test November–December.
Training loader reads monthly files only through October. Final-test evaluation is
an explicit separate command requiring a saved selection freeze and matching hashes.
No refit on validation: all estimators remain fitted on January–August. Validation
is reused for early stopping/algorithm selection/detection thresholds, so validation
scores are selection estimates; November–December is the held-out evaluation.

48 steps of15min. Origin t is last observed interval start; issue=t+15min. Last target
ends=t+49*15min. Purge48 origins at every partition end. Minimum history2689 rows.
All target-time calendar features are known at issue. Historical lags/rolling windows
are backward only. Weather observations are joined by weather_available_at<=issue;
never use future TMY as a forecast. Timestamps remain timezone-aware.

Compute budget: train on hourly origins (stride4) with all48 targets; validation and
test every15min. This preserves all target quarter-hours. Pooled-horizon LightGBM,
not48 separate fits: horizon is a feature. Two fixed Motor1 candidates (15/31 leaves),
one Motor2 candidate (15 leaves), max180 trees, patience18, seed20261011, two threads.
Fixed settings, no further search after viewing test. Explicit counts of independent
sessions must accompany overlapping origin/horizon metrics; rows are not independent.

Motor1 candidates: persistence, previous day, previous week, small/medium LightGBM.
Select global minimum validation MAE; report RMSE,WAPE,train-p90 peak and per horizon.

Motor2: zero, persistence, previous day, previous week, shrinkage frequency by local
hour/weekday, and LightGBM heads (power, occupancy, arrivals, queue, queue risk,
charging occurrence). Train rare binary heads as constants when no positive cases.
Q90: empirical train-hour quantile vs LightGBM quantile, select pinball on validation.
Report raw Q90 and max(point,Q90) separately; neither guarantees delivery.

Charging event threshold: requested>0.1kW; peak: >=80% of EVSE power (one vehicle).
Choose occurrence probability threshold by validation F1 over fixed grid
[0.01,0.025,0.05,0.1,0.2,0.35,0.5], ties prefer larger threshold.
Point candidate selection score:
  0.5*(MAE_active+MAE_inactive)/EV_limit + 0.1*(1-F1).
Reject candidates with zero recall when positives exist. If none qualify, explicitly
mark unresolved detection, not excellent. This prevents all-zero forecasts winning
solely on global MAE. Counts/risk use the same selected candidate; disclose any losses.

Queue: Brier/log-loss plus precision/recall at0.5, calibration bins, positive support.
No-positive periods: recall/PR metrics null with explicit caveat. Charging: precision,
recall,F1,active/connected/idle errors, peaks missed, arrival lead-time and per-session
metrics where possible. Overlapping windows cannot be counted as distinct sessions.

Original preservation baseline includes previous synthetic outputs (592 files).
Known preexisting frozen mismatch demo/high_autonomy_v2/app.py is not repaired.
