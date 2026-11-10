"""Modèle mathématique pur (PARTIE I de MODELISATION_ET_METHODE_OPTIMISATION.md).

Ce module transcrit, avec la même notation, la formulation indépendante de toute
méthode de résolution :
  - §2.1 données et ensembles      -> `ModelData`, `build_model`
  - §2.2 variables de décision     -> `Decision` (pres_s, exam_s, pré-soutenance, finale)
  - §2.3 contraintes A.0 … D.2     -> `violations` (vérification directe, étiquetée)
  - §3.2 critères f1 … f5          -> `objectives` (valeurs calculées par le modèle)
  - §5.1 domaines réduits          -> `W_pre`, `W_fin`, `T_compat`, `T_pres`, `T_exam`

Les valeurs de `objectives` sont celles « calculées par le modèle » ; elles sont
comparées aux valeurs « recalculées par le validateur » sur le fichier exporté.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path


# --------------------------------------------------------------------------
# §2.1  Données et ensembles
# --------------------------------------------------------------------------
@dataclass
class ModelData:
    instance_id: str
    K: range                          # créneaux {0, …, slots_per_day-1}
    D_pre: list[int]                  # jours de pré-soutenance (triés)
    D_fin: list[int]                  # jours de finale (triés)
    S: list[str]                      # étudiants
    T: list[str]                      # enseignants
    R: list[str]                      # salles (finales uniquement)
    d: dict[str, str]                 # d_s     : domaine de l'étudiant
    sup: dict[str, str]               # sup_s   : encadrant = rapporteur
    elig: dict[str, bool]             # elig_s  : admissible en finale
    P: dict[str, bool]                # P_e     : habilité à présider
    E: dict[str, bool]                # E_e     : habilité à examiner
    Dom: dict[str, frozenset]         # 𝒟_e     : domaines couverts
    cap_T: dict[str, int]             # cap_e   : plafond journalier enseignant
    cap_R: dict[str, int]             # cap_r   : plafond journalier salle
    A_S: dict[str, frozenset]         # A^S_{s,t,k} = 1  <=>  (t,k) ∈ A_S[s]
    A_T: dict[str, frozenset]         # A^T_{e,t,k}
    A_R: dict[str, frozenset]         # A^R_{r,t,k}
    rank: dict[str, int]              # position dans le fichier (départage uniquement)

    @property
    def S_elig(self) -> list[str]:
        return [s for s in self.S if self.elig[s]]

    @property
    def D(self) -> list[int]:
        return self.D_pre + self.D_fin


def _A(row: dict) -> frozenset:
    return frozenset((b["day"], k) for b in row["availability"] for k in b["slots"])


def load_instance(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def build_model(raw: dict) -> ModelData:
    T, R, S = raw["teachers"], raw["rooms"], raw["students"]
    rank = {}
    for rows in (T, R, S):
        rank.update({row["id"]: i for i, row in enumerate(rows)})
    return ModelData(
        instance_id=raw["instance_id"],
        K=range(raw["slots_per_day"]),
        D_pre=sorted(raw["predefence_days"]),
        D_fin=sorted(raw["final_defence_days"]),
        S=[s["id"] for s in S], T=[e["id"] for e in T], R=[r["id"] for r in R],
        d={s["id"]: s["domain"] for s in S},
        sup={s["id"]: s["supervisor_id"] for s in S},
        elig={s["id"]: s["eligible_final"] for s in S},
        P={e["id"]: "president" in e["eligible_roles"] for e in T},
        E={e["id"]: "examiner" in e["eligible_roles"] for e in T},
        Dom={e["id"]: frozenset(e["domains"]) for e in T},
        cap_T={e["id"]: e["max_sessions_per_day"] for e in T},
        cap_R={r["id"]: r["max_sessions_per_day"] for r in R},
        A_S={s["id"]: _A(s) for s in S},
        A_T={e["id"]: _A(e) for e in T},
        A_R={r["id"]: _A(r) for r in R},
        rank=rank,
    )


# --------------------------------------------------------------------------
# §2.2  Variables de décision naturelles
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Decision:
    pres: str                                   # pres_s
    exam: str                                   # exam_s (mêmes valeurs dans les deux phases : A.5)
    pre: tuple[int, int]                        # (day^pre_s, slot^pre_s), pas de salle
    fin: tuple[int, int, str] | None = None     # (day^fin_s, slot^fin_s, room_s) si s ∈ S_elig


Solution = dict[str, Decision]   # s -> décisions de l'étudiant s


def jury(m: ModelData, s: str, x: Decision, phase: str) -> list[str]:
    """Enseignants e tels que Participe^phase(e, s, ·, ·) = 1."""
    return [x.pres, x.exam] + ([m.sup[s]] if phase == "fin" else [])


def sessions(m: ModelData, X: Solution):
    """Énumère (s, phase, t, k, r) pour toutes les séances de X."""
    for s, x in X.items():
        yield s, "pre", x.pre[0], x.pre[1], None
        if x.fin is not None:
            yield s, "fin", x.fin[0], x.fin[1], x.fin[2]


# --------------------------------------------------------------------------
# §5.1  Réduction statique des domaines (valable pour toute méthode)
# --------------------------------------------------------------------------
def W_pre(m: ModelData, s: str) -> list[tuple[int, int]]:
    """𝒲^pre_s = {(t,k) ∈ D^pre × K | A^S_{s,t,k} = 1} — absorbe B.1, B.2 (pré)."""
    return [(t, k) for t in m.D_pre for k in m.K if (t, k) in m.A_S[s]]


def W_fin(m: ModelData, s: str) -> list[tuple[int, int, str]]:
    """𝒲^fin_s = {(t,k,r) | A^S_{s,t,k} = A^T_{sup_s,t,k} = A^R_{r,t,k} = 1} — absorbe B.1, B.2, B.4 et B.3(sup)."""
    if not m.elig[s]:
        return []
    sup = m.A_T[m.sup[s]]
    return [(t, k, r) for t in m.D_fin for k in m.K if (t, k) in m.A_S[s] and (t, k) in sup
            for r in m.R if (t, k) in m.A_R[r]]


def T_compat(m: ModelData, s: str, wp, wf) -> list[str]:
    """Enseignants ayant un créneau commun dans 𝒲^pre_s et, si s ∈ S_elig, dans 𝒲^fin_s (e ≠ sup_s)."""
    pre_tk = set(wp)
    fin_tk = {(t, k) for t, k, _ in wf}
    out = []
    for e in m.T:
        if not (pre_tk & m.A_T[e]):
            continue
        if m.elig[s] and (e == m.sup[s] or not (fin_tk & m.A_T[e])):
            continue
        out.append(e)
    return out


def T_pres(m: ModelData, compat: list[str]) -> list[str]:
    """T^pres_s : compatibles avec P_e = 1 — absorbe A.1 (et pres ≠ sup de A.4)."""
    return [e for e in compat if m.P[e]]


def T_exam(m: ModelData, s: str, compat: list[str]) -> list[str]:
    """T^exam_s : compatibles avec E_e = 1 et d_s ∈ 𝒟_e — absorbe A.2 (et exam ≠ sup de A.4)."""
    return [e for e in compat if m.E[e] and m.d[s] in m.Dom[e]]


# --------------------------------------------------------------------------
# §2.3  Contraintes impératives — vérification directe et étiquetée
# --------------------------------------------------------------------------
def violations(m: ModelData, X: Solution) -> list[str]:
    v = []
    # A.0 couverture exacte
    for s in m.S:
        if s not in X:
            v.append(f"A.0 {s}: aucune pré-soutenance")
        elif (X[s].fin is not None) != m.elig[s]:
            v.append(f"A.0 {s}: finale {'manquante' if m.elig[s] else 'interdite'}")
    for s, x in X.items():
        if not m.P[x.pres]:
            v.append(f"A.1 {s}: {x.pres} non habilité à présider")
        if not (m.E[x.exam] and m.d[s] in m.Dom[x.exam]):
            v.append(f"A.2 {s}: {x.exam} non habilité ou hors domaine {m.d[s]}")
        if x.pres == x.exam:
            v.append(f"A.3 {s}: président = examinateur")
        if x.fin is not None and m.sup[s] in (x.pres, x.exam):
            v.append(f"A.4 {s}: l'encadrant fait partie du binôme")
        # A.5 continuité : garantie par la représentation (un seul couple par étudiant)
    pi = defaultdict(int)          # π_{e,t,k}
    day_T = defaultdict(int)       # Σ_k π_{e,t,k}
    room = defaultdict(int)        # Σ_s 𝕀(room_s = r ∧ day = t ∧ slot = k)
    day_R = defaultdict(int)
    for s, phase, t, k, r in sessions(m, X):
        D_phase = m.D_pre if phase == "pre" else m.D_fin
        if t not in D_phase or k not in m.K:
            v.append(f"B.1 {s}/{phase}: jour {t} ou créneau {k} hors période")
        if (t, k) not in m.A_S[s]:
            v.append(f"B.2 {s}/{phase}: étudiant indisponible ({t},{k})")
        for e in set(jury(m, s, X[s], phase)):
            if (t, k) not in m.A_T[e]:
                v.append(f"B.3 {s}/{phase}: {e} indisponible ({t},{k})")
            pi[(e, t, k)] += 1
            day_T[(e, t)] += 1
        if phase == "fin":
            if r not in m.A_R or (t, k) not in m.A_R[r]:
                v.append(f"B.4 {s}: salle {r} indisponible ({t},{k})")
            room[(r, t, k)] += 1
            day_R[(r, t)] += 1
        elif r is not None:
            v.append(f"A.0 {s}: salle attribuée à une pré-soutenance")
    v += [f"C.1 {e}: {n} séances au créneau ({t},{k})" for (e, t, k), n in pi.items() if n > 1]
    v += [f"C.2 {r}: {n} finales au créneau ({t},{k})" for (r, t, k), n in room.items() if n > 1]
    # C.3 étudiant : garanti par construction (une séance par phase, D^pre ∩ D^fin = ∅)
    v += [f"D.1 {e}: {n} > cap {m.cap_T[e]} le jour {t}" for (e, t), n in day_T.items() if n > m.cap_T[e]]
    v += [f"D.2 {r}: {n} > cap {m.cap_R[r]} le jour {t}" for (r, t), n in day_R.items() if n > m.cap_R[r]]
    return v


# --------------------------------------------------------------------------
# §3.2  Les cinq critères, calculés par le modèle
# --------------------------------------------------------------------------
def _groups(slots: set[int]) -> int:
    """Nombre de fronts montants α_k = 1 ∧ α_{k-1} = 0 (blocs maximaux consécutifs)."""
    return sum(1 for k in slots if k - 1 not in slots)


def objectives(m: ModelData, X: Solution) -> dict:
    K_et = defaultdict(set)                    # K_{e,t} = {k | π_{e,t,k} = 1}
    load = {e: 0 for e in m.T}                 # Load(e)
    a_pre = defaultdict(set)                   # α^pre_{sup,t,·}
    a_fin = defaultdict(set)                   # α^fin_{sup,t,r,·}
    for s, phase, t, k, r in sessions(m, X):
        for e in set(jury(m, s, X[s], phase)):
            K_et[(e, t)].add(k)
            load[e] += 1
        if phase == "pre":
            a_pre[(m.sup[s], t)].add(k)
        else:
            a_fin[(m.sup[s], t, r)].add(k)
    groups_pre, groups_fin = defaultdict(int), defaultdict(int)
    for (sp, _), ks in a_pre.items():
        groups_pre[sp] += _groups(ks)
    for (sp, _, _), ks in a_fin.items():
        groups_fin[sp] += _groups(ks)
    return {
        "teacher_presence_days": len(K_et),                                              # f1 = Σ u_{e,t}
        "teacher_idle_slots": sum(max(ks) - min(ks) + 1 - len(ks) for ks in K_et.values()),   # f2
        "teacher_load_range": max(load.values()) - min(load.values()),                   # f3
        "supervisor_group_breaks": sum(max(0, g - 1) for g in groups_pre.values())
                                 + sum(max(0, g - 1) for g in groups_fin.values()),      # f4
        "distinct_jury_pairs": len({(x.pres, x.exam) for x in X.values()}),              # f5
    }


# --------------------------------------------------------------------------
# Export au format solution 4.0
# --------------------------------------------------------------------------
def to_solution(m: ModelData, X: Solution) -> dict:
    out = []
    for s, phase, t, k, r in sessions(m, X):
        out.append({"student_id": s, "phase": "predefence" if phase == "pre" else "final", "day": t, "slot": k,
                    "room_id": r, "president_id": X[s].pres, "examiner_id": X[s].exam})
    out.sort(key=lambda x: (x["phase"] != "predefence", x["day"], x["slot"], x["student_id"]))
    return {"schema_version": "4.0", "instance_id": m.instance_id, "sessions": out}
