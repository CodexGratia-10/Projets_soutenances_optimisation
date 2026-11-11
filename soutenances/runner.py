"""Exécution chronométrée d'une méthode, export, validation officielle et journal CSV.

Découpage des temps (conforme au protocole) :
- lecture du fichier d'instance : hors budget ;
- build_seconds : prétraitement / construction du modèle (dans le budget) ;
- search_seconds : recherche (dans le budget) ;
- total_seconds = build + search, plafonné par le budget de 60 s ;
- export, validation : hors budget, mesurés séparément dans le journal.
"""
from __future__ import annotations

import csv
import importlib.util
import inspect
import json
import platform
import os
import sys
import time
from pathlib import Path

from .baseline import Baseline
from .model import build_model, load_instance, objectives, violations

# CP-SAT est facultatif : le modèle de référence et le validateur restent utilisables
# dans un environnement où OR-Tools n'est pas installé.
METHODS = {"baseline": Baseline}
try:
    from .cpsat import CPSATSolver
except ImportError as exc:
    if exc.name is None or not exc.name.startswith("ortools"):
        raise
else:
    METHODS["cpsat"] = CPSATSolver

CSV_HEADER = ["instance_id", "method", "seed", "build_seconds", "search_seconds", "total_seconds",
              "first_feasible_seconds", "stop_status", "valid", "teacher_presence_days",
              "teacher_idle_slots", "teacher_load_range", "supervisor_group_breaks",
              "distinct_jury_pairs", "solution_file", "validation_file"]
METRICS = CSV_HEADER[9:14]


def get_ram_gb() -> float | None:
    try:
        if sys.platform == "win32":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return round(stat.ullTotalPhys / (1024 ** 3), 1)
        elif sys.platform.startswith("linux"):
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return round(kb / (1024 ** 2), 1)
    except Exception:
        pass
    return None


def load_validator(validator_dir: Path):
    spec = importlib.util.spec_from_file_location("official_validator", validator_dir / "validator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def run_one(instance_path: Path, method: str, out_dir: Path, validator, time_limit: float = 60.0,
            seed: int | None = None, threads: int = 1, log=print) -> dict:
    t0 = time.perf_counter()
    raw = load_instance(instance_path)
    read_seconds = time.perf_counter() - t0

    # ---------------- budget de résolution : commence ici
    start = time.perf_counter()
    model = build_model(raw)
    solver_cls = METHODS[method]
    sig = inspect.signature(solver_cls.__init__)
    kwargs = {}
    if "seed" in sig.parameters and seed is not None:
        kwargs["seed"] = seed
    if "threads" in sig.parameters:
        kwargs["threads"] = threads
    solver = solver_cls(model, **kwargs)
    build_seconds = time.perf_counter() - start
    result = solver.solve(time_limit=time_limit - build_seconds, start=time.perf_counter())
    end = time.perf_counter()
    search_seconds = end - start - build_seconds
    total_seconds = end - start
    # ---------------- fin du budget

    seed_label = "deterministe" if solver.deterministic else str(seed)
    tag = f"{raw['instance_id']}__{method}__{seed_label}"
    schedule = result["schedule"]
    complete = schedule.is_complete()
    # Pour CP-SAT, le temps de première solution est relatif au début de solve().
    # On y ajoute la construction du modèle afin de respecter le budget global.
    first_feasible = result.get("first_feasible_seconds")
    if first_feasible is not None:
        first_feasible += build_seconds
    elif method == "baseline" and complete:
        first_feasible = total_seconds

    # Contrôle interne par le modèle (§2.3) et critères calculés par le modèle (§3.2), hors budget.
    model_violations = violations(model, schedule.X) if complete else ["A.0 planning incomplet"]
    model_f = objectives(model, schedule.X) if complete else None

    # On valide un fichier temporaire AVANT de le classer comme solution livrable.
    # Un planning complet mais invalide ne doit jamais apparaître dans solutions/.
    candidate_dir = out_dir / ".staging"
    candidate_file = candidate_dir / f"{tag}.json"
    solution_file = out_dir / "partial" / f"{tag}.partial.json"
    valid_solution_file = out_dir / "solutions" / f"{tag}.json"
    invalid_solution_file = out_dir / "invalid" / f"{tag}.invalid.json"
    for previous in (solution_file, valid_solution_file, invalid_solution_file):
        if previous.exists():
            previous.unlink()

    t1 = time.perf_counter()
    write_json(candidate_file, schedule.to_solution())
    export_seconds = time.perf_counter() - t1

    # Validation du FICHIER exporté (relu depuis le disque), pas de l'objet en mémoire.
    t2 = time.perf_counter()
    report = validator.validate_solution(validator.load_json(instance_path), validator.load_json(candidate_file))
    validation_seconds = time.perf_counter() - t2
    if report["valid"]:
        solution_file = valid_solution_file
    elif complete:
        solution_file = invalid_solution_file
    else:
        solution_file = out_dir / "partial" / f"{tag}.partial.json"
    solution_file.parent.mkdir(parents=True, exist_ok=True)
    os.replace(candidate_file, solution_file)
    try:
        candidate_dir.rmdir()
    except OSError:
        pass

    validation_file = out_dir / "validations" / f"{tag}.validation.json"
    write_json(validation_file, report)

    status = result["status"]
    if complete and not report["valid"]:
        status = f"{status}_INVALID_SOLUTION"
    if total_seconds > time_limit:
        status = f"{status}_OVER_BUDGET"   # tout dépassement reste visible dans le bilan
    if not report["valid"]:
        first_feasible = None

    row = {
        "instance_id": raw["instance_id"], "method": solver.name, "seed": seed_label,
        "build_seconds": f"{build_seconds:.4f}", "search_seconds": f"{search_seconds:.4f}",
        "total_seconds": f"{total_seconds:.4f}",
        "first_feasible_seconds": "" if first_feasible is None else f"{first_feasible:.4f}",
        "stop_status": status, "valid": str(report["valid"]).lower(),
        "solution_file": str(solution_file), "validation_file": str(validation_file),
    }
    for m in METRICS:
        row[m] = report["metrics"][m] if report["valid"] else ""

    agreement = (report["valid"] == (not model_violations)
                 and (not report["valid"] or all(model_f[k] == report["metrics"][k] for k in METRICS)))
    log(json.dumps({"instance": raw["instance_id"], "method": solver.name, "seed": seed_label,
                    "threads": threads, "status": status, "valid": report["valid"],
                    "placed": result.get("placed"), "students": len(model.S),
                    "repairs": result.get("repairs"),
                    "read_s": round(read_seconds, 4), "build_s": round(build_seconds, 4),
                    "search_s": round(search_seconds, 4), "export_s": round(export_seconds, 4),
                    "validation_s": round(validation_seconds, 4),
                    "metrics": {m: row[m] for m in METRICS}, "model_f": model_f,
                    "model_violations": model_violations[:5], "model_validator_agree": agreement,
                    "errors": report["errors"][:5]}, ensure_ascii=False))
    row["_agree"] = agreement
    return row


def append_csv(path: Path, row: dict) -> None:
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_HEADER, extrasaction="ignore")
        if new:
            writer.writeheader()
        writer.writerow(row)


def environment(threads: int = 1) -> dict:
    env = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "ram_gb": get_ram_gb(),
        "threads": threads,
    }
    try:
        import ortools
        env["ortools_version"] = ortools.__version__
    except Exception:
        pass
    return env
