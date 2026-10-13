#!/usr/bin/env python3
"""
tests/test_feature_scaling.py

Unit tests for telemetry state feature scaling.
Validates the actual production function in local_controller.scaling.
Ensures identical normalization between training and inference,
and strictly rejects legacy states containing unnormalized epoch timestamps.
"""

import sys
import unittest
from pathlib import Path
import numpy as np

# Ensure local_controller is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from local_controller.scaling import scale_state_features, FEATURE_SCALES


class TestFeatureScaling(unittest.TestCase):
    def test_valid_state_scaling(self):
        s_valid = np.array([10, 8000, 15, 12000, 12, 10000, 35.0, 30.0, 1040.0], dtype=np.float32)
        s_scaled = scale_state_features(s_valid)
        self.assertEqual(len(s_scaled), 9)
        self.assertTrue(np.all(s_scaled >= 0.0))
        self.assertTrue(np.all(s_scaled <= 1.0))
        # Spot check scaled queue depth on bottleneck (15 / 64)
        self.assertAlmostEqual(s_scaled[2], 15.0 / 64.0, places=4)
        # Spot check target framerate (30 / 30 = 1.0)
        self.assertAlmostEqual(s_scaled[7], 1.0, places=4)

    def test_2d_batch_scaling(self):
        s_batch = np.array([[10, 8000, 15, 12000, 12, 10000, 35.0, 30.0, 1040.0]], dtype=np.float32)
        s_scaled = scale_state_features(s_batch)
        self.assertEqual(s_scaled.shape, (1, 9))
        self.assertTrue(np.all(s_scaled >= 0.0))
        self.assertTrue(np.all(s_scaled <= 1.0))

    def test_rejection_of_19_col_state(self):
        s_raw = np.zeros(19)
        s_raw[0] = 1728000000.0
        with self.assertRaises(ValueError):
            scale_state_features(s_raw)

    def test_rejection_of_epoch_timestamp(self):
        s_bad = np.array([10, 8000, 15, 12000, 12, 10000, 35.0, 30.0, 1728000000.0], dtype=np.float32)
        with self.assertRaises(ValueError):
            scale_state_features(s_bad)

    def test_rejection_of_invalid_dimension(self):
        s_short = np.array([10, 8000, 15, 12000], dtype=np.float32)
        with self.assertRaises(ValueError):
            scale_state_features(s_short)


if __name__ == "__main__":
    unittest.main()
