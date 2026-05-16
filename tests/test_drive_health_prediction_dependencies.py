import builtins
import importlib
import sys
import unittest
from unittest.mock import patch

DRIVE_HEALTH_MODULE = "simple_safer_server.services.drive_health"
NUMPY_X86_V2_ERROR = (
    "NumPy was installed with baseline optimizations requiring X86_V2, "
    "but this CPU only supports X86"
)


class DriveHealthPredictionDependencyTests(unittest.TestCase):
    def setUp(self):
        self.original_module = importlib.import_module(DRIVE_HEALTH_MODULE)

    def tearDown(self):
        # These tests import the service through a deliberately broken optional
        # dependency path. Put the original module object back so patch targets
        # in other Drive Health tests still refer to the same object they
        # imported at collection time.
        sys.modules[DRIVE_HEALTH_MODULE] = self.original_module
        importlib.reload(self.original_module)

    def import_drive_health_with_prediction_import_error(self, exception):
        original_import = builtins.__import__

        def failing_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "pandas":
                raise exception
            return original_import(name, globals, locals, fromlist, level)

        sys.modules.pop(DRIVE_HEALTH_MODULE, None)
        with patch("builtins.__import__", side_effect=failing_import):
            return importlib.import_module(DRIVE_HEALTH_MODULE)

    def test_drive_health_import_survives_numpy_x86_v2_prediction_dependency_failure(self):
        with self.assertLogs(DRIVE_HEALTH_MODULE, level="WARNING") as captured:
            drive_health = self.import_drive_health_with_prediction_import_error(
                RuntimeError(NUMPY_X86_V2_ERROR)
            )

        self.assertFalse(drive_health.PREDICTION_DEPENDENCIES_AVAILABLE)
        self.assertEqual(
            drive_health.PREDICTION_UNAVAILABLE_MESSAGE,
            (
                "SMART prediction is unavailable because this machine's CPU cannot run "
                "the installed NumPy package. SMART and HDSentinel checks can still run."
            ),
        )
        self.assertEqual(drive_health.get_optimal_threshold(), 0.5)
        self.assertIsNone(drive_health.predict_failure_probability({"smart_194_raw": 31.0}))
        self.assertEqual(len(captured.records), 1)
        self.assertIsNone(captured.records[0].exc_info)
        self.assertIn("SMART prediction dependencies could not be loaded", captured.output[0])

    def test_drive_health_import_survives_general_prediction_dependency_failure(self):
        with self.assertLogs(DRIVE_HEALTH_MODULE, level="WARNING"):
            drive_health = self.import_drive_health_with_prediction_import_error(
                RuntimeError("shared object could not be mapped")
            )

        self.assertFalse(drive_health.PREDICTION_DEPENDENCIES_AVAILABLE)
        self.assertEqual(
            drive_health.PREDICTION_UNAVAILABLE_MESSAGE,
            (
                "SMART prediction is unavailable because the prediction dependencies could "
                "not be loaded. SMART and HDSentinel checks can still run."
            ),
        )
        self.assertIsNone(drive_health.predict_failure_probability({"smart_194_raw": 31.0}))

    def test_prediction_dependency_boundary_does_not_catch_base_exception(self):
        with self.assertRaises(SystemExit):
            self.import_drive_health_with_prediction_import_error(SystemExit("stop import"))


if __name__ == "__main__":
    unittest.main()
