# Schema contract, version 4.0

Outils de résolution de problèmes d’optimisation  
Année académique 2026 - 2027  
Université d’Abomey-Calavi  
Institut de Formation et de Recherche en Informatique (IFRI)  
Licence 3 en Intelligence Artificielle  
Chargé du cours : Dr Ing. (MC) Houndji Vinasetan Ratheil — https://ratheil.info

All JSON files are UTF-8. Unknown properties, duplicate JSON object keys, missing properties, wrong types (including booleans instead of integers), duplicate identifiers and dangling references are errors. No field is optional. Identifiers are nonempty strings. Every numeric value must be written as an integer JSON token: no decimal point and no exponent (for example, `3.0` and `3e0` are rejected). Integers must be in the exactly representable JavaScript safe range 0 through 9007199254740991, subject to the stricter field-specific bounds below. Browser operational size limits are separate from this numerical contract. Days and slots are zero-based integers; one day has `slots_per_day` equal-length slots. Every session occupies exactly ONE slot: the half-open interval `[slot, slot + 1)`. A slot is indivisible and a session cannot span several slots or days.

## Instance

Top-level keys: `schema_version` (exactly `"4.0"`), `instance_id` (string), `size` (`"demo"`, `"small"`, `"medium"`, `"large"`), `seed` (integer >= 0), `days` (integer >= 1, giving days 0..days-1), `slots_per_day` (integer >= 1), `predefence_days` and `final_defence_days` (nonempty arrays of unique valid integer day indices), `domains` (nonempty unique string array), `teachers`, `rooms`, `students` (nonempty arrays).

The two common phase periods must be disjoint and satisfy `max(predefence_days) < min(final_defence_days)`. Every predefence must use a day in `predefence_days`; every final must use a day in `final_defence_days`. Arrays need not be sorted or contiguous. Days outside these arrays may remain in the horizon but cannot host sessions. There is no student-specific delay constraint; the two ordered common periods impose the temporal separation.

A teacher has `id`, `domains` (nonempty unique references to instance domains), `eligible_roles` (unique array drawn from `president`, `examiner`; can be empty), `max_sessions_per_day` (positive integer), `availability`.

Rooms are physical resources used ONLY by final defences. Online predefences have no room assignment, availability, occupancy or room daily-cap constraint. The nonempty input room array remains structurally required.

A room has `id`, `max_sessions_per_day` (positive integer), `availability`.

A student has `id`, `domain` (domain reference), `supervisor_id` (teacher reference; the supervisor is also the rapporteur), `eligible_final` (boolean), `availability`.

`availability` is an array of objects with exactly `day` (valid day index), `slots` (nonempty unique valid integer slot indices). A day occurs at most once. Missing days/slots mean unavailable. An empty availability array is syntactically allowed but may imply infeasibility. The single occupied slot must be listed as available.

## Solution

Top-level keys: `schema_version` (exactly `"4.0"`), `instance_id` (exact matching instance identifier), `sessions` (array).

Each session has exactly `student_id`, `phase` (`predefence` or `final`), `day`, `slot`, `room_id`, `president_id`, `examiner_id`. `room_id` is required and must be JSON `null` for `predefence`; for `final`, it must be a nonempty string referencing an instance room. Other identifiers must reference the instance. There must be exactly one predefence per student. A student with `eligible_final: true` must also have exactly one final; a student with `eligible_final: false` must have no final. The online predefence has president + examiner + student (no physical room); the final has the same president + examiner + fixed supervisor acting as rapporteur + student. The two predefence jury members must be distinct; the three final jury members must be distinct. President/examiner must have the respective eligible role; examiner must cover the student's domain, while president need not. The supervisor/rapporteur needs no eligible role or domain qualification. Fixed supervisor/rapporteur attendance is required only at the final.

Every attending teacher and student must be available and nonoverlapping, including online predefences. Physical rooms must be available and nonoverlapping only for final defences. Teacher daily caps count attended sessions of either phase; room daily caps count final sessions only. Each session occupies one slot. Online sessions with disjoint attending teachers and students may run simultaneously without any limit implied by the room inventory. A teacher's multiple roles may never be counted as separate people. Every session must lie in the common period of its phase. Continuity of president/examiner between phases is a hard constraint.

## Metrics (all minimized; only returned for valid solutions)

1. `teacher_presence_days`: sum over all teachers of the number of days with at least one attended session.
2. `teacher_idle_slots`: for each teacher and day, `last_slot - first_slot + 1 - number_of_attended_sessions`, summed. No overnight gaps.
3. `teacher_load_range`: maximum minus minimum attended-session count across ALL listed teachers, including unused teachers. Also return per-teacher counts for transparency.
4. `supervisor_group_breaks`: use phase-specific groups. For ONLINE PREDEFENCES, for each (fixed supervisor, day), collect the DISTINCT occupied slots of that supervisor's students. A group is a maximal run of consecutive distinct slots. Simultaneous online sessions of students with the same supervisor count as one occupied slot for this metric; no fictional online room or ordering of simultaneous sessions is introduced. Other supervisors' simultaneous sessions do not interrupt a run. For FINALS, sort sessions separately for each (day, room) by (slot, student_id). A group is a maximal sequence of temporally adjacent sessions with the same fixed supervisor. For either phase, aggregate group counts across all days (and rooms for finals), then contribute `max(0, group_count - 1)` per (supervisor, phase), and sum these contributions. The supervisor need not attend online predefences for this organizational criterion. This operational metric is a modeling convention, not an institutional rule.
5. `distinct_jury_pairs`: number of distinct ordered (president_id, examiner_id) pairs assigned to students, counted once from their predefence. Minimizing encourages reuse across students, irrespective of adjacency, days or rooms. This soft criterion is separate from mandatory cross-phase continuity for eligible students.

No weighted objective is imposed: students report the vector in this order and justify their scalarization or Pareto strategy.

## Python interface and CLI

`validator.py`: `validate_instance(instance) -> list[str]`; `validate_solution(instance, solution) -> {"valid": bool, "errors": list[str], "metrics": object|null}`; `load_json(path)` rejects duplicate keys and non-finite numbers. `python validator.py data/small_01.json submission.json` prints JSON and exits 0 if valid, 1 if invalid (including malformed input). `python validator.py --instance-only data/small_01.json` validates structure only, not existence of a feasible solution. No external packages required (Python >= 3.10).

`data/manifest.json` lists the 30 benchmark files and descriptive statistics. Feasible witnesses and the generator belong ONLY under `teacher/` and must not be distributed to students. `examples/empty_solution.json` illustrates output shape but is intentionally incomplete. A separate tiny demonstration instance and solution are not counted among the 30 benchmarks.
