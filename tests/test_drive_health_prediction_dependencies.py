import subprocess
import sys
import unittest

DRIVE_HEALTH_MODULE = "simple_safer_server.services.drive_health"
NUMPY_X86_V2_ERROR = (
    "NumPy was installed with baseline optimizations requiring X86_V2, "
    "but this CPU only supports X86"
)


class DriveHealthPredictionDependencyTests(unittest.TestCase):
    def run_import_in_subprocess(self, exception_class_name, exception_arg):
        # We invoke Python in a subprocess to test the import behavior with zero side effects on the main process.
        code = f"""
import builtins
import sys
import logging

class LogCaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []
    def emit(self, record):
        self.records.append(record)

logger = logging.getLogger("{DRIVE_HEALTH_MODULE}")
logger.setLevel(logging.WARNING)
handler = LogCaptureHandler()
logger.addHandler(handler)

original_import = builtins.__import__
def failing_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "pandas":
        if "{exception_class_name}" == "SystemExit":
            raise SystemExit("{exception_arg}")
        else:
            raise RuntimeError("{exception_arg}")
    return original_import(name, globals, locals, fromlist, level)

builtins.__import__ = failing_import

try:
    from simple_safer_server.services import drive_health
except SystemExit as exc:
    print("SYSTEM_EXIT: " + str(exc))
    sys.exit(99)

assert not drive_health.PREDICTION_DEPENDENCIES_AVAILABLE
if "X86_V2" in "{exception_arg}":
    assert "this machine's CPU cannot run the installed NumPy package" in drive_health.PREDICTION_UNAVAILABLE_MESSAGE
else:
    assert "prediction dependencies could not be loaded" in drive_health.PREDICTION_UNAVAILABLE_MESSAGE

assert drive_health.get_optimal_threshold() == 0.5
assert drive_health.predict_failure_probability({{"smart_194_raw": 31.0}}) is None

# Verify warning is logged properly
assert len(handler.records) == 1
assert handler.records[0].exc_info is None
assert "SMART prediction dependencies could not be loaded" in handler.records[0].getMessage()

print("OK")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        return result

    def test_drive_health_import_survives_numpy_x86_v2_prediction_dependency_failure(self):
        result = self.run_import_in_subprocess("RuntimeError", NUMPY_X86_V2_ERROR)
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("OK", result.stdout)

    def test_drive_health_import_survives_general_prediction_dependency_failure(self):
        result = self.run_import_in_subprocess("RuntimeError", "shared object could not be mapped")
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("OK", result.stdout)

    def test_prediction_dependency_boundary_does_not_catch_base_exception(self):
        result = self.run_import_in_subprocess("SystemExit", "stop import")
        # SystemExit should bubble up, causing our try-except block in the subprocess to print SYSTEM_EXIT and exit with 99
        self.assertEqual(result.returncode, 99, msg=result.stderr or result.stdout)
        self.assertIn("SYSTEM_EXIT: stop import", result.stdout)


if __name__ == "__main__":
    unittest.main()
