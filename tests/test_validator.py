"""Run: python -m unittest discover -s tests -v (from the pack root)."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from validator import load_json,validate_instance,validate_solution


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.i=load_json(ROOT/"examples/demo_instance.json")
        self.s=load_json(ROOT/"examples/demo_solution.json")
    def invalid(self,fragment=None):
        result=validate_solution(self.i,self.s)
        self.assertFalse(result["valid"])
        self.assertIsNone(result["metrics"])
        if fragment:
            self.assertTrue(any(fragment in e for e in result["errors"]),result["errors"])
    def test_demo_metrics_exact(self):
        r=validate_solution(self.i,self.s)
        self.assertTrue(r["valid"],r)
        self.assertEqual(r["metrics"],{"teacher_presence_days":6,"teacher_idle_slots":6,"teacher_load_range":5,"supervisor_group_breaks":2,"distinct_jury_pairs":2,"teacher_session_counts":{"ENS-A":5,"ENS-B":4,"ENS-C":3,"ENS-D":0}})
    def test_all_30_feasible_witnesses(self):
        manifest=load_json(ROOT/"data/manifest.json")
        self.assertEqual(len(manifest["instances"]),30)
        for row in manifest["instances"]:
            witness=ROOT/"teacher/witnesses"/(row["instance_id"]+".solution.json")
            if not witness.exists():
                self.skipTest("Teacher witnesses intentionally absent from student distribution")
            with self.subTest(instance=row["instance_id"]):
                result=validate_solution(load_json(ROOT/row["file"]),load_json(witness))
                self.assertTrue(result["valid"],result["errors"])
    def test_all_30_instance_schemas(self):
        manifest=load_json(ROOT/"data/manifest.json")
        self.assertEqual({r["size"] for r in manifest["instances"]},{"small","medium","large"})
        for row in manifest["instances"]:
            with self.subTest(instance=row["instance_id"]):
                i=load_json(ROOT/row["file"])
                self.assertEqual(validate_instance(i),[])
                self.assertTrue(any(not s["eligible_final"] for s in i["students"]))
                self.assertTrue(any(s["eligible_final"] for s in i["students"]))
    def test_unknown_solution_field(self):
        self.s["solver_name"]="unrecognized";self.invalid("unknown fields")
    def test_missing_session_field(self):
        del self.s["sessions"][0]["day"];self.invalid("missing fields")
    def test_unknown_instance_field(self):
        self.i["students"][0]["rapporteur_id"]="ENS-D";self.invalid("unknown fields")
    def test_bool_is_not_integer(self):
        self.s["sessions"][0]["day"]=True;self.invalid("expected integer")
    def test_float_is_not_integer(self):
        self.s["sessions"][0]["slot"]=0.0;self.invalid("expected integer")
    def test_duplicate_teacher_id(self):
        self.i["teachers"][1]["id"]=self.i["teachers"][0]["id"];self.invalid("duplicate identifier")
    def test_duplicate_domain(self):
        self.i["domains"].append(self.i["domains"][0]);self.invalid("duplicate value")
    def test_duplicate_availability_day(self):
        self.i["teachers"][0]["availability"].append(copy.deepcopy(self.i["teachers"][0]["availability"][0]));self.invalid("duplicate day")
    def test_duplicate_availability_slot(self):
        row=self.i["teachers"][0]["availability"][0];row["slots"].append(row["slots"][0]);self.invalid("duplicate slot")
    def test_unknown_reference(self):
        next(s for s in self.s["sessions"] if s["phase"]=="final")["room_id"]="missing";self.invalid("unknown identifier")
    def test_unknown_supervisor(self):
        self.i["students"][0]["supervisor_id"]="missing";self.invalid("unknown supervisor_id")
    def test_missing_predefence(self):
        self.s["sessions"]=[s for s in self.s["sessions"] if not(s["student_id"]=="ETU-1" and s["phase"]=="predefence")];self.invalid("expected 1 predefence")
    def test_missing_final(self):
        self.s["sessions"]=[s for s in self.s["sessions"] if not(s["student_id"]=="ETU-1" and s["phase"]=="final")];self.invalid("expected 1 final")
    def test_duplicate_phase(self):
        self.s["sessions"].append(copy.deepcopy(self.s["sessions"][0]));self.invalid("expected 1 predefence")
    def test_ineligible_final_forbidden(self):
        extra=copy.deepcopy(next(s for s in self.s["sessions"] if s["student_id"]=="ETU-3"));extra["phase"]="final";extra["room_id"]=self.i["rooms"][0]["id"];self.s["sessions"].append(extra);self.invalid("final forbidden")
    def test_continuity(self):
        final=next(s for s in self.s["sessions"] if s["phase"]=="final");final["president_id"]="ENS-D";self.invalid("continuity")
    def test_final_outside_common_period(self):
        final=next(s for s in self.s["sessions"] if s["phase"]=="final");final["day"]=0;self.invalid("outside its common phase period")
    def test_pre_jury_distinct(self):
        self.s["sessions"][0]["examiner_id"]=self.s["sessions"][0]["president_id"];self.invalid("must be distinct")
    def test_final_jury_distinct(self):
        final=next(s for s in self.s["sessions"] if s["phase"]=="final");student=next(s for s in self.i["students"] if s["id"]==final["student_id"]);final["president_id"]=student["supervisor_id"];self.invalid("must be distinct")
    def test_examiner_domain(self):
        session=self.s["sessions"][0];student=next(s for s in self.i["students"] if s["id"]==session["student_id"]);self.i["domains"].append("OTHER");teacher=next(t for t in self.i["teachers"] if t["id"]==session["examiner_id"]);teacher["domains"]=["OTHER"];self.invalid("does not cover")
    def test_president_no_domain_restriction(self):
        # A's qualification can be unrelated while still president; A is never examiner in the demo.
        self.i["domains"].append("OTHER")
        self.i["teachers"][0]["domains"]=["OTHER"]
        self.assertTrue(validate_solution(self.i,self.s)["valid"])
    def test_role_eligibility(self):
        tid=self.s["sessions"][0]["president_id"];next(t for t in self.i["teachers"] if t["id"]==tid)["eligible_roles"]=[];self.invalid("not eligible")
    def test_slot_outside_day(self):
        final=next(s for s in self.s["sessions"] if s["phase"]=="final");final["slot"]=self.i["slots_per_day"];self.invalid("expected integer")
    def test_teacher_availability(self):
        self.i["teachers"][0]["availability"]=[];self.invalid("unavailable")
    def test_room_availability(self):
        self.i["rooms"][0]["availability"]=[];self.invalid("unavailable")
    def test_student_availability(self):
        self.i["students"][0]["availability"]=[];self.invalid("unavailable")
    def test_single_occupied_slot_availability(self):
        final=next(s for s in self.s["sessions"] if s["phase"]=="final");student=next(s for s in self.i["students"] if s["id"]==final["student_id"]);row=next(r for r in student["availability"] if r["day"]==final["day"]);row["slots"].remove(final["slot"]);self.invalid("unavailable")
    def test_overlapping_online_teacher(self):
        pre=[s for s in self.s["sessions"] if s["phase"]=="predefence"]
        for k in ("day","slot","room_id"):pre[1][k]=pre[0][k]
        self.invalid("overlap")
    def test_teacher_daily_cap(self):
        self.i["teachers"][0]["max_sessions_per_day"]=1;self.invalid("daily cap exceeded")
    def test_room_daily_cap(self):
        self.i["rooms"][0]["max_sessions_per_day"]=1;self.invalid("daily cap exceeded")
    def test_recursive_bad_types_do_not_crash(self):
        bad=[None,True,False,{},[],"",1.5]
        paths=[("days",),("domains",),("teachers",),("predefence_days",),("final_defence_days",),("predefence_days",0),("final_defence_days",0),("teachers",0,"id"),("teachers",0,"domains"),("teachers",0,"eligible_roles"),("teachers",0,"availability"),("teachers",0,"availability",0,"day"),("teachers",0,"availability",0,"slots"),("students",0,"supervisor_id"),("students",0,"eligible_final")]
        for path in paths:
            for value in bad:
                with self.subTest(path=path,value=value):
                    instance=copy.deepcopy(self.i);target=instance
                    for key in path[:-1]:target=target[key]
                    target[path[-1]]=value
                    result=validate_solution(instance,self.s)
                    self.assertIs(type(result["valid"]),bool)
        for key in self.s["sessions"][0]:
            for value in bad:
                if key == "room_id" and value is None:
                    continue
                solution=copy.deepcopy(self.s);solution["sessions"][0][key]=value
                self.assertFalse(validate_solution(self.i,solution)["valid"])
    def test_duplicate_json_keys_and_nonfinite_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"bad.json"
            for text in ('{"x":1,"x":2}','{"nested":{"k":0,"k":1}}','{"x":NaN}','{"x":Infinity}','{"x":1e999}'):
                path.write_text(text)
                with self.assertRaises(ValueError):load_json(path)
    def test_schema_version(self):
        self.assertEqual(self.i["schema_version"],"4.0")
        self.assertEqual(self.s["schema_version"],"4.0")
        self.s["schema_version"]="1.0";self.invalid("must be 4.0")
    def test_empty_predefence_period(self):
        self.i["predefence_days"]=[];self.invalid("nonempty array")
    def test_empty_final_period(self):
        self.i["final_defence_days"]=[];self.invalid("nonempty array")
    def test_missing_predefence_period(self):
        del self.i["predefence_days"];self.invalid("missing fields")
    def test_missing_final_period(self):
        del self.i["final_defence_days"];self.invalid("missing fields")
    def test_duplicate_predefence_day(self):
        self.i["predefence_days"]=[0,0];self.invalid("duplicate day")
    def test_duplicate_final_day(self):
        self.i["final_defence_days"]=[2,2];self.invalid("duplicate day")
    def test_period_overlap(self):
        self.i["predefence_days"]=[0,1];self.i["final_defence_days"]=[1,2];self.invalid("must be disjoint")
    def test_periods_ordered_globally(self):
        self.i["predefence_days"]=[0,2];self.i["final_defence_days"]=[1];self.invalid("must precede")
    def test_reversed_periods(self):
        self.i["predefence_days"]=[2];self.i["final_defence_days"]=[0];self.invalid("must precede")
    def test_period_day_above_horizon(self):
        self.i["final_defence_days"]=[3];self.invalid("expected integer")
    def test_period_day_negative(self):
        self.i["predefence_days"]=[-1];self.invalid("expected integer")
    def test_period_bool_not_day(self):
        self.i["predefence_days"]=[False];self.invalid("expected integer")
    def test_period_float_not_day(self):
        self.i["final_defence_days"]=[2.0];self.invalid("expected integer")
    def test_unhashable_period_member(self):
        for value in ([],{},[0],{"day":0}):
            self.i["predefence_days"]=[value];self.invalid("expected integer")
    def test_unsorted_period_arrays_are_valid(self):
        self.i["final_defence_days"]=[2,1]
        self.assertTrue(validate_solution(self.i,self.s)["valid"])
    def test_available_day_outside_both_periods_forbidden(self):
        self.s["sessions"][0]["day"]=1;self.invalid("outside its common phase period")
    def test_day_of_other_phase_forbidden(self):
        self.s["sessions"][0]["day"]=2;self.invalid("outside its common phase period")
    def test_last_slot_is_valid_for_final(self):
        final=next(s for s in self.s["sessions"] if s["phase"]=="final");final["slot"]=self.i["slots_per_day"]-1
        result=validate_solution(self.i,self.s);self.assertTrue(result["valid"],result)
    def test_adjacent_one_slot_finals_do_not_overlap(self):
        finals=[s for s in self.s["sessions"] if s["phase"]=="final"];finals[1]["slot"]=1
        result=validate_solution(self.i,self.s);self.assertTrue(result["valid"],result)
        self.assertEqual(result["metrics"]["teacher_idle_slots"],3)
        self.assertEqual(result["metrics"]["supervisor_group_breaks"],1)
    def test_noncontiguous_period_hole_is_forbidden(self):
        self.i["days"]=4;self.i["predefence_days"]=[0,2];self.i["final_defence_days"]=[3]
        # Move finals to day3 and copy availability; day1 remains available but outside periods.
        for kind in ("teachers","rooms","students"):
            for resource in self.i[kind]:
                resource["availability"].append({"day":3,"slots":list(range(self.i["slots_per_day"]))})
        for session in self.s["sessions"]:
            if session["phase"]=="final":session["day"]=3
        self.assertTrue(validate_solution(self.i,self.s)["valid"])
        self.s["sessions"][0]["day"]=1;self.invalid("outside its common phase period")
    def test_manifest_periods_match_instances(self):
        manifest=load_json(ROOT/"data/manifest.json")
        self.assertEqual(manifest["schema_version"],"4.0")
        for row in manifest["instances"]:
            instance=load_json(ROOT/row["file"])
            for field in ("predefence_days","final_defence_days"):
                self.assertEqual(row[field],instance[field])
            self.assertLess(max(instance["predefence_days"]),min(instance["final_defence_days"]))
    def online_only(self):
        self.i["students"] = self.i["students"][:2]
        for student in self.i["students"]:student["eligible_final"]=False
        self.s["sessions"] = [s for s in self.s["sessions"] if s["phase"]=="predefence" and s["student_id"] in ("ETU-1","ETU-2")]
        self.s["sessions"][1].update(slot=0,president_id="ENS-C",examiner_id="ENS-D")
        self.i["teachers"][2]["availability"][0]["slots"]=list(range(self.i["slots_per_day"]))
        self.i["rooms"]=self.i["rooms"][:1]
    def test_online_simultaneous_despite_one_unavailable_room(self):
        self.online_only()
        self.i["rooms"][0].update(availability=[],max_sessions_per_day=1)
        result=validate_solution(self.i,self.s)
        self.assertTrue(result["valid"],result)
        self.assertEqual(result["metrics"]["supervisor_group_breaks"],0)
        self.assertEqual(result["metrics"]["teacher_presence_days"],4)
    def test_online_room_assignment_rejected(self):
        self.s["sessions"][0]["room_id"]=self.i["rooms"][0]["id"];self.invalid("must be null")
    def test_final_null_room_rejected(self):
        next(s for s in self.s["sessions"] if s["phase"]=="final")["room_id"]=None;self.invalid("expected nonempty string")
    def test_online_room_id_required_even_when_null(self):
        del self.s["sessions"][0]["room_id"];self.invalid("missing fields")
    def test_room_day_zero_unavailable_ignored_online(self):
        for room in self.i["rooms"]:room["availability"]=[a for a in room["availability"] if a["day"]!=0]
        self.assertTrue(validate_solution(self.i,self.s)["valid"])
    def test_online_room_daily_cap_not_counted(self):
        self.online_only()
        self.s["sessions"][1]["slot"]=1
        self.i["rooms"][0]["max_sessions_per_day"]=1
        result=validate_solution(self.i,self.s)
        self.assertTrue(result["valid"],result)
    def test_online_teacher_availability_still_required(self):
        self.online_only();self.i["teachers"][0]["availability"]=[];self.invalid("teacher ENS-A unavailable")
    def test_online_student_availability_still_required(self):
        self.online_only();self.i["students"][0]["availability"]=[];self.invalid("student ETU-1 unavailable")
    def test_online_shared_teacher_collision_rejected(self):
        self.online_only();self.s["sessions"][1]["president_id"]="ENS-A";self.invalid("teacher ENS-A overlap")
    def test_online_same_supervisor_simultaneous_counts_one_slot(self):
        self.online_only()
        result=validate_solution(self.i,self.s)
        self.assertTrue(result["valid"],result)
        self.assertEqual(result["metrics"]["supervisor_group_breaks"],0)
    def test_online_same_supervisor_consecutive_slots_one_group(self):
        self.online_only();self.s["sessions"][1]["slot"]=1
        result=validate_solution(self.i,self.s)
        self.assertTrue(result["valid"],result)
        self.assertEqual(result["metrics"]["supervisor_group_breaks"],0)
    def test_online_same_supervisor_gap_adds_group(self):
        self.online_only();self.s["sessions"][1]["slot"]=2
        result=validate_solution(self.i,self.s)
        self.assertTrue(result["valid"],result)
        self.assertEqual(result["metrics"]["supervisor_group_breaks"],1)
    def test_online_groups_across_days_are_added(self):
        self.online_only();self.i["predefence_days"]=[0,1];self.s["sessions"][1]["day"]=1
        result=validate_solution(self.i,self.s)
        self.assertTrue(result["valid"],result)
        self.assertEqual(result["metrics"]["supervisor_group_breaks"],1)
    def test_other_supervisor_simultaneous_does_not_split_online_run(self):
        self.online_only()
        self.s["sessions"][1].update(slot=1,president_id="ENS-A",examiner_id="ENS-B")
        student=copy.deepcopy(self.i["students"][0]);student.update(id="ETU-3",supervisor_id="ENS-D");self.i["students"].append(student)
        session=copy.deepcopy(self.s["sessions"][0]);session.update(student_id="ETU-3",president_id="ENS-C",examiner_id="ENS-D");self.s["sessions"].append(session)
        result=validate_solution(self.i,self.s)
        self.assertTrue(result["valid"],result)
        self.assertEqual(result["metrics"]["supervisor_group_breaks"],0)
    def test_final_room_collision_still_rejected(self):
        finals=[s for s in self.s["sessions"] if s["phase"]=="final"];finals[1]["slot"]=finals[0]["slot"];self.invalid("room Salle-1 overlap")
    def test_safe_integer_upper_boundary(self):
        self.i["seed"]=9007199254740991
        self.assertTrue(validate_solution(self.i,self.s)["valid"])
        self.i["seed"]=9007199254740992;self.invalid("expected integer")
    def test_exponent_and_decimal_integer_spellings_rejected_by_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"bad.json"
            for token in ("0.0","0e0","0E+0"):
                text=json.dumps(self.s).replace('"slot": 0','"slot": '+token,1)
                path.write_text(text)
                result=validate_solution(self.i,load_json(path))
                self.assertFalse(result["valid"],token)
    def test_all_witness_predefences_have_no_room(self):
        for row in load_json(ROOT/"data/manifest.json")["instances"]:
            witness=ROOT/"teacher/witnesses"/(row["instance_id"]+".solution.json")
            if not witness.exists():self.skipTest("Teacher witnesses intentionally absent from student distribution")
            for session in load_json(witness)["sessions"]:
                if session["phase"]=="predefence":self.assertIsNone(session["room_id"])
                else:self.assertIsInstance(session["room_id"],str)
    def test_room_model_fields_exact(self):
        expected={"id","max_sessions_per_day","availability"}
        for room in self.i["rooms"]:self.assertEqual(set(room),expected)
        for row in load_json(ROOT/"data/manifest.json")["instances"]:
            for room in load_json(ROOT/row["file"])["rooms"]:
                self.assertEqual(set(room),expected)
    def test_unknown_room_property_rejected(self):
        self.i["rooms"][0]["unrecognized_room_attribute"]=1;self.invalid("unknown fields")
    def test_cli_success_and_failure_codes(self):
        cmd=[sys.executable,str(ROOT/"validator.py"),str(ROOT/"examples/demo_instance.json")]
        good=subprocess.run(cmd+[str(ROOT/"examples/demo_solution.json")],capture_output=True,text=True)
        self.assertEqual(good.returncode,0,good.stderr)
        self.assertTrue(json.loads(good.stdout)["valid"])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"bad.json";path.write_text('{"x":1,"x":2}')
            bad=subprocess.run(cmd+[str(path)],capture_output=True,text=True)
            self.assertEqual(bad.returncode,1)
            self.assertFalse(json.loads(bad.stdout)["valid"])
        checked=subprocess.run([sys.executable,str(ROOT/"validator.py"),"--instance-only",str(ROOT/"examples/demo_instance.json")],capture_output=True,text=True)
        self.assertEqual(checked.returncode,0)

if __name__=="__main__":unittest.main()
