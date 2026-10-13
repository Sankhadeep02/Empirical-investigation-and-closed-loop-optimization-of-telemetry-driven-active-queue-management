#!/usr/bin/env python3
"""
tests/test_controller_integration.py

Verifies the integration of physical domain feature scaling with the controller pipeline.
Tests state dimension validation and ensures raw hardware timestamps are strictly rejected.
"""

import unittest
import numpy as np
import sys
import os

sys.path.append(os.path.abspath("local_controller"))
from scaling import scale_state_features, FEATURE_SCALES

class TestControllerIntegration(unittest.TestCase):
    def test_nine_feature_scaling_bounds(self):
        # 9 features: [q1, dt1, q2, dt2, q3, dt3, buffer, fps, bitrate]
        raw_state = np.array([32.0, 25000.0, 16.0, 10000.0, 48.0, 40000.0, 30.0, 25.0, 1500.0])
        scaled = scale_state_features(raw_state)
        self.assertEqual(len(scaled), 9)
        self.assertTrue(np.all(scaled >= 0.0))
        self.assertTrue(np.all(scaled <= 1.0))
        # Expected scaling: 32/64 = 0.5, 25000/50000 = 0.5, etc.
        self.assertAlmostEqual(scaled[0], 0.5)
        self.assertAlmostEqual(scaled[1], 0.5)

    def test_legacy_19_col_rejection(self):
        legacy_state = np.zeros(19)
        with self.assertRaises(ValueError):
            scale_state_features(legacy_state)

    def test_timestamp_contamination_rejection(self):
        # Contaminated 9-feature vector with epoch timestamp
        contaminated = np.array([32.0, 25000.0, 16.0, 10000.0, 48.0, 40000.0, 1791111490260.0, 25.0, 1500.0])
        with self.assertRaises(ValueError):
            scale_state_features(contaminated)

if __name__ == '__main__':
    unittest.main()
