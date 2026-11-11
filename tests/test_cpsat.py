"""Tests ciblés du solveur CP-SAT et de ses mécanismes de délai/réparation."""
from __future__ import annotations

from pathlib import Path
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from soutenances import model as M  # noqa: E402
try:
    from ortools.sat.python import cp_model  # noqa: E402
    from soutenances.cpsat import CPSATSolver  # noqa: E402
    ORTOOLS_AVAILABLE = True
except ImportError as exc:
    if exc.name is None or not exc.name.startswith("ortools"):
        raise
    CPSATSolver = None
    cp_model = None
    ORTOOLS_AVAILABLE = False
from soutenances.schedule import PartialSolution  # noqa: E402


def tiny_instance():
    availability = lambda days: [{"day": d, "slots": [0, 1, 2]} for d in days]
    return {
        "schema_version": "4.0", "instance_id": "tiny-cpsat", "size": "demo", "seed": 0,
        "days": 2, "slots_per_day": 3, "predefence_days": [0], "final_defence_days": [1],
        "domains": ["X", "Y"],
        "teachers": [
            {"id": "P", "domains": ["Y"], "eligible_roles": ["president"], "max_sessions_per_day": 3, "availability": availability([0, 1])},
            {"id": "E", "domains": ["X"], "eligible_roles": ["examiner"], "max_sessions_per_day": 3, "availability": availability([0, 1])},
            {"id": "SUP", "domains": ["X"], "eligible_roles": [], "max_sessions_per_day": 3, "availability": availability([0, 1])},
            {"id": "Q", "domains": ["Y"], "eligible_roles": ["examiner"], "max_sessions_per_day": 3, "availability": availability([0, 1])},
        ],
        "rooms": [{"id": "R", "max_sessions_per_day": 3, "availability": availability([1])}],
        "students": [{"id": "A", "domain": "X", "supervisor_id": "SUP", "eligible_final": False, "availability": availability([0, 1])}],
    }


class PartialSolutionSnapshotTests(unittest.TestCase):
    def test_backup_restore_restores_all_incremental_indexes(self):
        model = M.build_model(tiny_instance())
        state = PartialSolution(model)
        snapshot = state.backup()
        state.assign("A", M.Decision("P", "E", (0, 0)))
        state.restore(snapshot)
        self.assertEqual(state.X, {})
        self.assertEqual(state.pi, set())
        self.assertEqual(dict(state.day_T), {})
        self.assertEqual(state.room, set())
        self.assertEqual(dict(state.day_R), {})
        self.assertEqual(state.load, {teacher: 0 for teacher in model.T})


@unittest.skipUnless(ORTOOLS_AVAILABLE, "OR-Tools n’est pas installé")
class CPSATInitialAssignmentTests(unittest.TestCase):
    def setUp(self):
        self.model = M.build_model(tiny_instance())
        self.solver = CPSATSolver(self.model)

    def test_constructive_assignment_is_complete_and_valid(self):
        schedule = self.solver._compute_initial_assignment(time.perf_counter() + 5.0)
        self.assertIsNotNone(schedule)
        self.assertTrue(schedule.is_complete())
        self.assertEqual(M.violations(self.model, schedule.X), [])

    def test_expired_deadline_stops_before_construction(self):
        schedule = self.solver._compute_initial_assignment(time.perf_counter() - 1.0)
        self.assertIsNone(schedule)

    def test_zero_budget_returns_without_running_cp_sat(self):
        result = self.solver.solve(time_limit=0.0, start=time.perf_counter())
        self.assertEqual(result["status"], "TIME_LIMIT")
        self.assertFalse(result["schedule"].is_complete())

    def test_invalid_cp_sat_model_without_initial_assignment_returns_partial_schedule(self):
        with patch.object(self.solver, "_compute_initial_assignment", return_value=None), \
             patch.object(self.solver.model, "Validate", return_value="invalid model"):
            result = self.solver.solve(time_limit=5.0, start=time.perf_counter())
        self.assertEqual(result["status"], "MODEL_INVALID")
        self.assertIsNotNone(result["schedule"])
        self.assertFalse(result["schedule"].is_complete())
        self.assertEqual(result["placed"], len(result["schedule"].X))

    def test_infeasible_cp_sat_model_is_distinct_from_timeout(self):
        class FakeCpSolver:
            def __init__(self):
                self.parameters = SimpleNamespace()

            def Solve(self, model, callback):
                return cp_model.INFEASIBLE

        with patch.object(self.solver, "_compute_initial_assignment", return_value=None), \
             patch.object(self.solver.model, "Validate", return_value=""), \
             patch("soutenances.cpsat.cp_model.CpSolver", FakeCpSolver):
            result = self.solver.solve(time_limit=5.0, start=time.perf_counter())
        self.assertEqual(result["status"], "INFEASIBLE")
        self.assertIsNotNone(result["schedule"])
        self.assertFalse(result["schedule"].is_complete())
        self.assertEqual(result["placed"], len(result["schedule"].X))

    def test_initial_feasibility_conflicting_with_cp_sat_is_reported(self):
        initial = self.solver._compute_initial_assignment(time.perf_counter() + 5.0)
        self.assertIsNotNone(initial)

        class FakeCpSolver:
            def __init__(self):
                self.parameters = SimpleNamespace()

            def Solve(self, model, callback):
                return cp_model.INFEASIBLE

        with patch.object(self.solver, "_compute_initial_assignment", return_value=initial), \
             patch.object(self.solver.model, "Validate", return_value=""), \
             patch("soutenances.cpsat.cp_model.CpSolver", FakeCpSolver):
            result = self.solver.solve(time_limit=5.0, start=time.perf_counter())
        self.assertEqual(result["status"], "MODEL_CONFLICT")
        self.assertTrue(result["schedule"].is_complete())


if __name__ == "__main__":
    unittest.main()
