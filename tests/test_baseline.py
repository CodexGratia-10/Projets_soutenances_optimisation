"""Lancer depuis planification/ : python -m unittest discover -s tests -v

Chaque cas limite du sujet est relié à l'étiquette de contrainte du modèle
(MODELISATION_ET_METHODE_OPTIMISATION.md, §2.3) ET au validateur officiel.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import json
from unittest import mock
import time
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
PACK = HERE if (HERE / "validator.py").exists() else HERE.parent / "Projet_jurys_etudiants"

from soutenances import model as M                    # noqa: E402
from soutenances.baseline import Baseline             # noqa: E402
from soutenances.runner import METHODS, load_validator, run_one  # noqa: E402
from soutenances.schedule import PartialSolution      # noqa: E402

V = load_validator(PACK)


def tiny(eligible=False):
    """Pré-soutenance jour 0, finale jour 1, 3 créneaux, une salle."""
    full = lambda days: [{"day": d, "slots": [0, 1, 2]} for d in days]
    return {
        "schema_version": "4.0", "instance_id": "tiny", "size": "demo", "seed": 0,
        "days": 2, "slots_per_day": 3, "predefence_days": [0], "final_defence_days": [1],
        "domains": ["X", "Y"],
        "teachers": [
            {"id": "P", "domains": ["Y"], "eligible_roles": ["president"], "max_sessions_per_day": 3, "availability": full([0, 1])},
            {"id": "E", "domains": ["X"], "eligible_roles": ["examiner"], "max_sessions_per_day": 3, "availability": full([0, 1])},
            {"id": "Q", "domains": ["Y"], "eligible_roles": ["examiner"], "max_sessions_per_day": 3, "availability": full([0, 1])},
            {"id": "SUP", "domains": ["X"], "eligible_roles": [], "max_sessions_per_day": 3, "availability": full([0, 1])},
        ],
        "rooms": [{"id": "R", "max_sessions_per_day": 3, "availability": full([1])}],
        "students": [
            {"id": "A", "domain": "X", "supervisor_id": "SUP", "eligible_final": eligible, "availability": full([0, 1])},
            {"id": "B", "domain": "X", "supervisor_id": "SUP", "eligible_final": eligible,
             "availability": [{"day": 0, "slots": [0]}, {"day": 1, "slots": [0, 1, 2]}]},
        ],
    }


class Domains(unittest.TestCase):
    """§5.1 : les domaines réduits absorbent A.1, A.2, A.4, B.1, B.2, B.4."""
    def setUp(self):
        self.m = M.build_model(tiny(eligible=True))

    def test_roles_domain_A1_A2(self):
        b = Baseline(self.m)
        self.assertEqual(b.pairs["A"], [("P", "E")])   # Q hors domaine X, SUP sans rôle

    def test_supervisor_excluded_A4(self):
        raw = tiny(eligible=True)
        raw["teachers"][3]["eligible_roles"] = ["president", "examiner"]
        b = Baseline(M.build_model(raw))
        self.assertNotIn("SUP", {e for pair in b.pairs["A"] for e in pair})

    def test_periods_B1_and_availability_B2(self):
        self.assertTrue(all(t == 0 for t, _ in M.W_pre(self.m, "A")))
        self.assertTrue(all(t == 1 for t, _, _ in M.W_fin(self.m, "A")))
        self.assertEqual(M.W_pre(self.m, "B"), [(0, 0)])

    def test_non_eligible_has_no_final_domain_A0(self):
        self.assertEqual(M.W_fin(M.build_model(tiny(eligible=False)), "A"), [])


class ModelConstraints(unittest.TestCase):
    """§2.3 : `violations` détecte chaque cas limite demandé, comme le validateur."""
    def setUp(self):
        self.raw = tiny(eligible=True)
        self.m = M.build_model(self.raw)
        self.X = {"A": M.Decision("P", "E", (0, 1), (1, 0, "R")),
                  "B": M.Decision("P", "E", (0, 0), (1, 1, "R"))}

    def assertViolation(self, X, label):
        v = M.violations(self.m, X)
        self.assertTrue(any(x.startswith(label) for x in v), v)
        self.assertFalse(V.validate_solution(self.raw, M.to_solution(self.m, X))["valid"])

    def test_valid_reference(self):
        self.assertEqual(M.violations(self.m, self.X), [])
        r = V.validate_solution(self.raw, M.to_solution(self.m, self.X))
        self.assertTrue(r["valid"], r["errors"])

    def test_role_incompatible(self):
        self.assertViolation({**self.X, "A": replace(self.X["A"], pres="Q")}, "A.1")

    def test_wrong_domain(self):
        self.assertViolation({**self.X, "A": replace(self.X["A"], exam="Q")}, "A.2")

    def test_missing_final(self):
        self.assertViolation({**self.X, "A": replace(self.X["A"], fin=None)}, "A.0")

    def test_day_outside_period(self):
        self.assertViolation({**self.X, "A": replace(self.X["A"], pre=(1, 2))}, "B.1")

    def test_unavailability(self):
        self.assertViolation({**self.X, "B": replace(self.X["B"], pre=(0, 2))}, "B.2")

    def test_overlap(self):
        self.assertViolation({**self.X, "A": replace(self.X["A"], pre=(0, 0))}, "C.1")

    def test_room_overlap(self):
        self.assertViolation({**self.X, "A": replace(self.X["A"], fin=(1, 1, "R"))}, "C.2")

    def test_teacher_daily_cap(self):
        self.m.cap_T["P"] = 1
        self.raw["teachers"][0]["max_sessions_per_day"] = 1
        self.assertViolation(self.X, "D.1")

    def test_room_daily_cap(self):
        self.m.cap_R["R"] = 1
        self.raw["rooms"][0]["max_sessions_per_day"] = 1
        self.assertViolation(self.X, "D.2")

    def test_room_on_predefence_and_continuity_rejected_by_validator(self):
        # Ces deux erreurs sont impossibles à représenter dans le modèle (A.5 et
        # « pas de salle en ligne » sont garanties par la représentation) :
        # on vérifie qu'elles seraient bien refusées dans un fichier.
        sol = M.to_solution(self.m, self.X)
        pre = next(x for x in sol["sessions"] if x["phase"] == "predefence")
        pre["room_id"] = "R"
        self.assertFalse(V.validate_solution(self.raw, sol)["valid"])
        sol = M.to_solution(self.m, self.X)
        fin = next(x for x in sol["sessions"] if x["phase"] == "final" and x["student_id"] == "A")
        fin["president_id"], fin["examiner_id"] = fin["examiner_id"], fin["president_id"]
        self.assertFalse(V.validate_solution(self.raw, sol)["valid"])


class Objectives(unittest.TestCase):
    """§3.2 : les critères calculés par le modèle égalent ceux du validateur."""
    def test_demo_solution(self):
        raw = V.load_json(PACK / "examples/demo_instance.json")
        sol = V.load_json(PACK / "examples/demo_solution.json")
        m = M.build_model(raw)
        X = {}
        for x in sol["sessions"]:
            d = X.get(x["student_id"]) or M.Decision(x["president_id"], x["examiner_id"], (0, 0))
            if x["phase"] == "predefence":
                d = replace(d, pre=(x["day"], x["slot"]))
            else:
                d = replace(d, fin=(x["day"], x["slot"], x["room_id"]))
            X[x["student_id"]] = d
        ref = V.validate_solution(raw, sol)["metrics"]
        self.assertEqual(M.objectives(m, X), {k: ref[k] for k in M.objectives(m, X)})


class Repair(unittest.TestCase):
    def setUp(self):
        self.m = M.build_model(tiny(eligible=False))
        self.b, self.X = Baseline(self.m), PartialSolution(self.m)

    def test_ejection_unblocks_student(self):
        self.X.assign("A", M.Decision("P", "E", (0, 0)))   # A prend le seul créneau de B
        self.assertFalse(self.b.insert(self.X, "B"))
        self.assertTrue(self.b.repair(self.X, "B", ["A"], float("inf")))
        self.assertEqual((self.X.X["B"].pre, self.X.X["A"].pre), ((0, 0), (0, 1)))
        self.assertEqual(M.violations(self.m, self.X.X), [])

    def test_failed_repair_restores_state(self):
        raw = tiny(eligible=False)
        raw["students"][0]["availability"] = [{"day": 0, "slots": [0]}]
        m = M.build_model(raw)
        b, X = Baseline(m), PartialSolution(m)
        X.assign("A", M.Decision("P", "E", (0, 0)))
        snapshot = (dict(X.X), set(X.pi), dict(X.load))
        self.assertFalse(b.repair(X, "B", ["A"], float("inf")))
        self.assertEqual(snapshot, (dict(X.X), set(X.pi), dict(X.load)))

    def test_infeasible_reported(self):
        raw = tiny(eligible=False)
        raw["students"][0]["availability"] = [{"day": 0, "slots": [0]}]
        r = Baseline(M.build_model(raw)).solve(5, time.perf_counter())
        self.assertEqual(r["status"], "NO_SOLUTION")


class EndToEnd(unittest.TestCase):
    def run_case(self, path):
        with tempfile.TemporaryDirectory() as tmp:
            row = run_one(path, "baseline", Path(tmp), V, 60.0, None, log=lambda *_: None)
            self.assertEqual(row["valid"], "true", row)
            self.assertTrue(row["_agree"], "modèle et validateur en désaccord")
            return V.load_json(row["solution_file"])

    def test_demo(self):
        self.run_case(PACK / "examples/demo_instance.json")

    def test_deterministic(self):
        p = PACK / "data/small_01.json"
        self.assertEqual(self.run_case(p), self.run_case(p))

    def test_one_per_size(self):
        for name in ("small_01", "medium_01", "large_01"):
            with self.subTest(name):
                self.run_case(PACK / f"data/{name}.json")

    def test_complete_but_invalid_plan_is_not_exported_as_solution(self):
        raw = tiny(eligible=False)
        model = M.build_model(raw)
        schedule = Baseline(model).solve(5.0, time.perf_counter())["schedule"]
        self.assertTrue(schedule.is_complete())
        schedule.X["A"] = replace(schedule.X["A"], pres="Q")

        class InvalidCompleteSolver:
            name = "fake_invalid"
            deterministic = True

            def __init__(self, _model):
                pass

            def solve(self, time_limit, start):
                return {"schedule": schedule, "status": "COMPLETE", "repairs": 0,
                        "placed": len(schedule.X)}

        with tempfile.TemporaryDirectory() as tmp:
            instance_path = Path(tmp) / "instance.json"
            instance_path.write_text(json.dumps(raw), encoding="utf-8")
            with mock.patch.dict(METHODS, {"fake_invalid": InvalidCompleteSolver}):
                row = run_one(instance_path, "fake_invalid", Path(tmp) / "out", V,
                              5.0, None, log=lambda *_: None)
            self.assertEqual(row["valid"], "false")
            self.assertIn("INVALID_SOLUTION", row["stop_status"])
            self.assertIn("invalid", row["solution_file"])
            self.assertTrue(Path(row["solution_file"]).exists())
            self.assertFalse((Path(tmp) / "out" / "solutions").exists())


if __name__ == "__main__":
    unittest.main()
