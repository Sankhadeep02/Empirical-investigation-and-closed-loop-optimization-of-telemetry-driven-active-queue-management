#!/usr/bin/env python3
"""
local_controller/scaling.py

Production feature scaling for telemetry state vectors in the DESiRED control plane.
Replaces single-row L2 normalization with fixed physical min-max feature bounds.
Strictly validates state dimensions and rejects vectors contaminated with raw hardware epoch timestamps.
"""

import numpy as np

# Physical scaling boundaries across the 9 telemetry features:
# [q1, dt1, q2, dt2, q3, dt3, buffer, fps, bitrate]
FEATURE_SCALES = np.array([
    64.0,     # max queue depth hop 1 (pkts) - BMv2 queue capacity
    50000.0,  # max dequeue timedelta hop 1 (us)
    64.0,     # max queue depth hop 2 (pkts) - bottleneck capacity
    50000.0,  # max dequeue timedelta hop 2 (us)
    64.0,     # max queue depth hop 3 (pkts) - egress capacity
    50000.0,  # max dequeue timedelta hop 3 (us)
    60.0,     # max client video buffer (s)
    30.0,     # target playback framerate (fps)
    2000.0    # nominal max bitrate (kbps)
], dtype=np.float32)

def scale_state_features(raw_state):
    """
    Applies fixed physical feature scaling across 9 telemetry features.
    
    Parameters:
        raw_state: 1D or 2D array-like containing raw telemetry observations.
        
    Returns:
        np.ndarray: Scaled features clipped strictly to [0.0, 1.0].
        
    Raises:
        ValueError: If a legacy 19-column state or unnormalized epoch timestamp is detected.
    """
    arr = np.asarray(raw_state, dtype=np.float32)
    flat = arr.flatten()
    
    # Reject legacy 19-column state or states contaminated with hardware epoch timestamps (> 1e6)
    if len(flat) == 19 or np.any(flat > 1e6):
        raise ValueError("Raw timestamp state detected! Only cleaned 9-feature vectors allowed.")
    if len(flat) != 9:
        raise ValueError(f"Expected 9 features, got {len(flat)}")
        
    scaled = np.clip(flat / FEATURE_SCALES, 0.0, 1.0)
    
    if arr.ndim == 2:
        return scaled.reshape(arr.shape)
    return scaled
