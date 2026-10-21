from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import _calc_endpoint_status

def test_endpoint_status_untested_empty():
    assert _calc_endpoint_status("op1", {}) == "untested"
    assert _calc_endpoint_status("op1", {"op2": {"tc1": {"passed": True}}}) == "untested"

def test_endpoint_status_passed():
    results = {
        "op1": {
            "tc1": {"passed": True},
            "tc2": {"passed": True},
        }
    }
    assert _calc_endpoint_status("op1", results) == "passed"

def test_endpoint_status_failed():
    results = {
        "op1": {
            "tc1": {"passed": True},
            "tc2": {"passed": False},
        }
    }
    assert _calc_endpoint_status("op1", results) == "failed"
