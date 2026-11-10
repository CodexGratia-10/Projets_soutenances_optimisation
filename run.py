#!/usr/bin/env python3
"""Point d'entrée.

Un cas :
    python run.py solve ../Projet_jurys_etudiants/data/small_01.json --method baseline --out resultats/essai
Campagne complète (30 instances du manifeste) :
    python run.py campaign --method baseline --out resultats/baseline
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from soutenances.runner import METHODS, append_csv, environment, load_validator, run_one

HERE = Path(__file__).resolve().parent
DEFAULT_PACK = HERE


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("solve", "campaign"):
        sp = sub.add_parser(name)
        sp.add_argument("--method", choices=sorted(METHODS), default="baseline")
        sp.add_argument("--out", type=Path, required=True)
        sp.add_argument("--time-limit", type=float, default=60.0)
        sp.add_argument("--threads", type=int, default=1, help="limite de threads pour le solveur (défaut: 1)")
        sp.add_argument("--seeds", type=int, nargs="*", default=[0, 1, 2, 3, 4],
                        help="graines pour une méthode stochastique (ignorées si déterministe)")
        sp.add_argument("--pack", type=Path, default=DEFAULT_PACK, help="dossier fourni (validator.py, data/)")
        if name == "solve":
            sp.add_argument("instance", type=Path)
    args = parser.parse_args()

    validator = load_validator(args.pack)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.cmd == "solve":
        instances = [args.instance]
    else:
        manifest = json.loads((args.pack / "data" / "manifest.json").read_text(encoding="utf-8"))
        instances = [args.pack / row["file"] for row in manifest["instances"]]

    seeds = [None] if METHODS[args.method].deterministic else args.seeds
    log_path = args.out / "journal.jsonl"
    with open(log_path, "a", encoding="utf-8") as log_stream:
        def log(line: str) -> None:
            print(line)
            log_stream.write(line + "\n")
            log_stream.flush()
        log(json.dumps({"start": datetime.now().isoformat(timespec="seconds"), "cmd": args.cmd,
                        "method": args.method, "time_limit": args.time_limit,
                        **environment(threads=args.threads)}))
        all_valid = True
        for path in instances:
            for seed in seeds:
                row = run_one(path, args.method, args.out, validator, args.time_limit, seed,
                               threads=args.threads, log=log)
                append_csv(args.out / "resultats.csv", row)
                all_valid &= row["valid"] == "true"
    return 0 if all_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
