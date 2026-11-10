#!/usr/bin/env python3
"""Strict, dependency-free evaluator. This is a validator, not a solver."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import sys

VERSION = "4.0"
MAX_SAFE_INTEGER = 9007199254740991
PHASES = ("predefence", "final")


def load_json(path):
    def pairs(items):
        obj = {}
        for k, v in items:
            if k in obj:
                raise ValueError(f"Duplicate JSON key: {k}")
            obj[k] = v
        return obj
    def reject_constant(value):
        raise ValueError(f"Non-finite JSON number: {value}")
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"Non-finite JSON number: {value}")
        return number
    with open(path, encoding="utf-8") as stream:
        return json.load(stream, object_pairs_hook=pairs, parse_constant=reject_constant, parse_float=finite_float)


class Check:
    def __init__(self):
        self.errors = []
    def fail(self, path, message):
        self.errors.append(f"{path}: {message}")
    def obj(self, value, keys, path):
        if type(value) is not dict:
            self.fail(path, "expected object")
            return False
        missing, extra = set(keys) - set(value), set(value) - set(keys)
        if missing:
            self.fail(path, "missing fields: " + ", ".join(sorted(missing)))
        if extra:
            self.fail(path, "unknown fields: " + ", ".join(sorted(map(str, extra))))
        return not missing and not extra
    def integer(self, value, path, lo=0, hi=None):
        hi = MAX_SAFE_INTEGER if hi is None else min(hi, MAX_SAFE_INTEGER)
        if type(value) is not int or value < lo or value > hi:
            self.fail(path, f"expected integer in [{lo}, {hi if hi is not None else 'infinity'}]")
            return False
        return True
    def string(self, value, path):
        if type(value) is not str or not value.strip():
            self.fail(path, "expected nonempty string")
            return False
        return True
    def array(self, value, path, nonempty=False):
        if type(value) is not list or (nonempty and not value):
            self.fail(path, "expected " + ("nonempty " if nonempty else "") + "array")
            return False
        return True
    def strings(self, value, path, allowed=None, nonempty=False):
        if not self.array(value, path, nonempty):
            return
        seen = set()
        for i, item in enumerate(value):
            here = f"{path}[{i}]"
            if self.string(item, here):
                if item in seen:
                    self.fail(here, "duplicate value")
                seen.add(item)
                if allowed is not None and item not in allowed:
                    self.fail(here, "unknown value")
    def availability(self, value, path, days, slots):
        if not self.array(value, path):
            return
        seen = set()
        for i, row in enumerate(value):
            here = f"{path}[{i}]"
            if not self.obj(row, {"day", "slots"}, here):
                continue
            if self.integer(row["day"], here + ".day", 0, days-1):
                if row["day"] in seen:
                    self.fail(here, "duplicate day")
                seen.add(row["day"])
            if self.array(row["slots"], here + ".slots", True):
                used = set()
                for j, slot in enumerate(row["slots"]):
                    if self.integer(slot, f"{here}.slots[{j}]", 0, slots-1):
                        if slot in used:
                            self.fail(here, "duplicate slot")
                        used.add(slot)


def validate_instance(instance):
    c = Check()
    keys = {"schema_version", "instance_id", "size", "seed", "days", "slots_per_day", "predefence_days", "final_defence_days", "domains", "teachers", "rooms", "students"}
    if not c.obj(instance, keys, "instance"):
        return c.errors
    if instance["schema_version"] != VERSION:
        c.fail("schema_version", "must be 4.0")
    c.string(instance["instance_id"], "instance_id")
    if type(instance["size"]) is not str or instance["size"] not in ("demo", "small", "medium", "large"):
        c.fail("size", "must be demo, small, medium or large")
    c.integer(instance["seed"], "seed")
    for name in ("days", "slots_per_day"):
        c.integer(instance[name], name, 1)
    if c.errors:
        return c.errors
    days, slots = instance["days"], instance["slots_per_day"]
    for field in ("predefence_days", "final_defence_days"):
        if c.array(instance[field], field, True):
            seen = set()
            for index, day in enumerate(instance[field]):
                if c.integer(day, f"{field}[{index}]", 0, days-1):
                    if day in seen:
                        c.fail(field, "duplicate day")
                    seen.add(day)
    if c.errors:
        return c.errors
    pre_days, final_days = set(instance["predefence_days"]), set(instance["final_defence_days"])
    if pre_days & final_days:
        c.fail("phase periods", "predefence_days and final_defence_days must be disjoint")
    if max(pre_days) >= min(final_days):
        c.fail("phase periods", "all predefence days must precede all final defence days")
    c.strings(instance["domains"], "domains", nonempty=True)
    if c.errors:
        return c.errors
    domains = set(instance["domains"])
    ids = {}
    for kind, fields in (
        ("teachers", {"id", "domains", "eligible_roles", "max_sessions_per_day", "availability"}),
        ("rooms", {"id", "max_sessions_per_day", "availability"}),
        ("students", {"id", "domain", "supervisor_id", "eligible_final", "availability"}),
    ):
        ids[kind] = set()
        if not c.array(instance[kind], kind, True):
            continue
        for i, row in enumerate(instance[kind]):
            here = f"{kind}[{i}]"
            if not c.obj(row, fields, here):
                continue
            if c.string(row["id"], here + ".id"):
                if row["id"] in ids[kind]:
                    c.fail(here, "duplicate identifier")
                ids[kind].add(row["id"])
            c.availability(row["availability"], here + ".availability", days, slots)
            if kind == "teachers":
                c.strings(row["domains"], here + ".domains", domains, True)
                c.strings(row["eligible_roles"], here + ".eligible_roles", {"president", "examiner"})
            elif kind == "students":
                if c.string(row["domain"], here + ".domain") and row["domain"] not in domains:
                    c.fail(here + ".domain", "unknown domain")
                c.string(row["supervisor_id"], here + ".supervisor_id")
                if type(row["eligible_final"]) is not bool:
                    c.fail(here + ".eligible_final", "expected boolean")
            if kind != "students":
                c.integer(row["max_sessions_per_day"], here + ".max_sessions_per_day", 1)
    if c.errors:
        return c.errors
    for student in instance["students"]:
        if student["supervisor_id"] not in ids["teachers"]:
            c.fail("student " + student["id"], "unknown supervisor_id")
    return c.errors


def availability(row):
    return {(block["day"], s) for block in row["availability"] for s in block["slots"]}


def participants(session, students):
    result = [session["president_id"], session["examiner_id"]]
    if session["phase"] == "final":
        result.append(students[session["student_id"]]["supervisor_id"])
    return result


def compute_metrics(instance, sessions):
    students = {s["id"]: s for s in instance["students"]}
    loads = {t["id"]: 0 for t in instance["teachers"]}
    teacher_days = defaultdict(list)
    streams = defaultdict(list)
    online_slots = defaultdict(set)
    pairs = set()
    for s in sessions:
        duration = 1
        for tid in participants(s, students):
            loads[tid] += 1
            teacher_days[(tid, s["day"])].append((s["slot"], s["slot"]+duration))
        if s["phase"] == "predefence":
            pairs.add((s["president_id"], s["examiner_id"]))
            supervisor = students[s["student_id"]]["supervisor_id"]
            online_slots[(supervisor, s["day"])].add(s["slot"])
        else:
            streams[(s["phase"], s["day"], s["room_id"])].append(s)
    idle = sum(max(e for _, e in intervals) - min(b for b, _ in intervals) - sum(e-b for b,e in intervals) for intervals in teacher_days.values())
    groups = Counter()
    for (supervisor, day), slots in online_slots.items():
        previous = None
        for slot in sorted(slots):
            if previous is None or slot != previous + 1:
                groups[(supervisor, "predefence")] += 1
            previous = slot
    for (phase, day, room), stream in streams.items():
        previous = None
        for s in sorted(stream, key=lambda x:(x["slot"], x["student_id"])):
            supervisor = students[s["student_id"]]["supervisor_id"]
            if previous is None or previous[0] != supervisor or previous[1] != s["slot"]:
                groups[(supervisor, phase)] += 1
            previous = (supervisor, s["slot"] + 1)
    return {
        "teacher_presence_days": len(teacher_days),
        "teacher_idle_slots": idle,
        "teacher_load_range": max(loads.values()) - min(loads.values()),
        "supervisor_group_breaks": sum(n-1 for n in groups.values()),
        "distinct_jury_pairs": len(pairs),
        "teacher_session_counts": dict(sorted(loads.items())),
    }


def validate_solution(instance, solution):
    errors = validate_instance(instance)
    if errors:
        return {"valid": False, "errors": ["Invalid instance: " + e for e in errors], "metrics": None}
    c = Check()
    def result():
        return {"valid": not c.errors, "errors": c.errors, "metrics": None}
    if not c.obj(solution, {"schema_version", "instance_id", "sessions"}, "solution"):
        return result()
    if solution["schema_version"] != VERSION:
        c.fail("schema_version", "must be 4.0")
    if solution["instance_id"] != instance["instance_id"]:
        c.fail("instance_id", "does not match instance")
    if not c.array(solution["sessions"], "sessions"):
        return result()
    teachers = {t["id"]: t for t in instance["teachers"]}
    rooms = {r["id"]: r for r in instance["rooms"]}
    students = {s["id"]: s for s in instance["students"]}
    fields = {"student_id", "phase", "day", "slot", "room_id", "president_id", "examiner_id"}
    for i, s in enumerate(solution["sessions"]):
        here = f"sessions[{i}]"
        if not c.obj(s, fields, here):
            continue
        for field, pool in (("student_id", students), ("president_id", teachers), ("examiner_id", teachers)):
            if c.string(s[field], here + "." + field) and s[field] not in pool:
                c.fail(here + "." + field, "unknown identifier")
        if type(s["phase"]) is not str or s["phase"] not in PHASES:
            c.fail(here + ".phase", "unknown phase")
        elif s["phase"] == "predefence":
            if s["room_id"] is not None:
                c.fail(here + ".room_id", "must be null for online predefence")
        elif c.string(s["room_id"], here + ".room_id") and s["room_id"] not in rooms:
            c.fail(here + ".room_id", "unknown identifier")
        c.integer(s["day"], here + ".day", 0, instance["days"]-1)
        c.integer(s["slot"], here + ".slot", 0, instance["slots_per_day"]-1)
    if c.errors:
        return result()
    booked = defaultdict(list)
    daily = Counter()
    phases = defaultdict(list)
    available = {"teacher": {k: availability(v) for k,v in teachers.items()}, "room": {k: availability(v) for k,v in rooms.items()}, "student": {k: availability(v) for k,v in students.items()}}
    for i, s in enumerate(solution["sessions"]):
        here = f"sessions[{i}]"
        sid, phase, day, slot = s["student_id"], s["phase"], s["day"], s["slot"]
        student = students[sid]
        duration = 1
        phases[(sid, phase)].append(s)
        if phase == "final" and not student["eligible_final"]:
            c.fail(here, "final forbidden: student is not eligible")
        period = instance["predefence_days"] if phase == "predefence" else instance["final_defence_days"]
        if day not in period:
            c.fail(here, f"{phase} day is outside its common phase period")
        jury = participants(s, students)
        if len(set(jury)) != len(jury):
            c.fail(here, "jury members must be distinct")
        for role, tid in (("president", s["president_id"]), ("examiner", s["examiner_id"])):
            if role not in teachers[tid]["eligible_roles"]:
                c.fail(here, f"teacher {tid} is not eligible as {role}")
        if student["domain"] not in teachers[s["examiner_id"]]["domains"]:
            c.fail(here, "examiner does not cover student domain")
        resources = [("student", sid)] + [("teacher", tid) for tid in set(jury)]
        if phase == "final":
            resources.append(("room", s["room_id"]))
        for kind, rid in resources:
            if any((day, t) not in available[kind][rid] for t in range(slot, slot+duration)):
                c.fail(here, f"{kind} {rid} unavailable for whole session")
            for a,b,index in booked[(kind, rid, day)]:
                if slot < b and a < slot+duration:
                    c.fail(here, f"{kind} {rid} overlap with sessions[{index}]")
            booked[(kind, rid, day)].append((slot, slot+duration, i))
            daily[(kind, rid, day)] += 1
    for student in instance["students"]:
        sid = student["id"]
        expected = {"predefence": 1, "final": int(student["eligible_final"])}
        for phase, count in expected.items():
            if len(phases[(sid, phase)]) != count:
                c.fail("student " + sid, f"expected {count} {phase} session(s), got {len(phases[(sid, phase)])}")
        if len(phases[(sid, "predefence")]) == len(phases[(sid, "final")]) == 1:
            pre, final = phases[(sid, "predefence")][0], phases[(sid, "final")][0]
            if (pre["president_id"], pre["examiner_id"]) != (final["president_id"], final["examiner_id"]):
                c.fail("student " + sid, "president/examiner continuity violated")
    for (kind, rid, day), count in daily.items():
        if kind in ("teacher", "room"):
            cap = (teachers if kind == "teacher" else rooms)[rid]["max_sessions_per_day"]
            if count > cap:
                c.fail(f"{kind} {rid} day {day}", f"daily cap exceeded ({count}>{cap})")
    if c.errors:
        return result()
    return {"valid": True, "errors": [], "metrics": compute_metrics(instance, solution["sessions"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-only", action="store_true", help="Check input schema, not mathematical feasibility")
    parser.add_argument("instance", type=Path)
    parser.add_argument("solution", type=Path, nargs="?")
    args = parser.parse_args(argv)
    if not args.instance_only and args.solution is None:
        parser.error("solution is required unless --instance-only is used")
    try:
        instance = load_json(args.instance)
        if args.instance_only:
            errors = validate_instance(instance)
            output = {"valid": not errors, "errors": errors, "metrics": None}
        else:
            output = validate_solution(instance, load_json(args.solution))
    except (OSError, ValueError, RecursionError) as exc:
        output = {"valid": False, "errors": [f"Cannot read JSON input: {exc}"], "metrics": None}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
