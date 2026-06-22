"""Tests for the daily-daemon scheduling logic (run.py).

Only the pure decision helpers are unit-tested here (weekend filter, dated
snapshot path, "is a run due now?"). The fetch + analysis orchestration is
verified by actually running `run.py --run-once`.
"""

import os
import sys
from datetime import date, datetime

# run.py lives at the project root, not in src/.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import run


# Known weekdays: 2024-01-01 = Mon, -05 = Fri, -06 = Sat, -07 = Sun.

def test_is_weekday_filters_sat_and_sun():
    assert run.is_weekday(date(2024, 1, 1))       # Monday
    assert run.is_weekday(date(2024, 1, 5))       # Friday
    assert not run.is_weekday(date(2024, 1, 6))   # Saturday
    assert not run.is_weekday(date(2024, 1, 7))   # Sunday


def test_snapshot_path_is_yyyy_mm_dd():
    p = run.snapshot_path(date(2026, 6, 22), os.path.join("x", "results"))
    assert os.path.basename(p) == "2026_06_22.png"


def test_due_today_true_on_weekday_after_hour(tmp_path):
    now = datetime(2024, 1, 5, 10)   # Friday 10:00, no snapshot yet
    assert run.due_today(now, run_hour=1, results_dir=str(tmp_path)) is True


def test_due_today_false_on_weekend(tmp_path):
    now = datetime(2024, 1, 6, 10)   # Saturday
    assert run.due_today(now, run_hour=1, results_dir=str(tmp_path)) is False


def test_due_today_false_before_run_hour(tmp_path):
    now = datetime(2024, 1, 5, 0)    # Friday 00:00, before run_hour=1
    assert run.due_today(now, run_hour=1, results_dir=str(tmp_path)) is False


def test_due_today_false_if_snapshot_already_exists(tmp_path):
    now = datetime(2024, 1, 5, 10)
    open(run.snapshot_path(now.date(), str(tmp_path)), "w").close()
    assert run.due_today(now, run_hour=1, results_dir=str(tmp_path)) is False
