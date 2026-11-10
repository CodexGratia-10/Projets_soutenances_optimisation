"""Méthode de référence : affectation gloutonne des variables du modèle pur.

Point de départ : la formulation de la PARTIE I (module `model`). Chaque
étudiant s porte le vecteur de variables (pres_s, exam_s, day^pre_s,
slot^pre_s [, day^fin_s, slot^fin_s, room_s]). La méthode affecte ces vecteurs
un étudiant à la fois, sans retour arrière global :

0. Réduction des domaines (§5.1) : 𝒲^pre_s, 𝒲^fin_s, T^pres_s, T^exam_s.
   Les contraintes A.1, A.2, A.4, B.1, B.2, B.4 et B.3(sup) sont alors
   satisfaites par construction.
1. Ordre des variables (« domaine le plus petit d'abord ») :
   s ∈ S_elig avant s ∉ S_elig, puis |{(e1,e2) ∈ T^pres_s × T^exam_s, e1 ≠ e2}|
   croissant, puis |𝒲^pre_s| + |𝒲^fin_s| croissant, puis rang dans le fichier.
2. Ordre des valeurs du jury : couples (e1, e2) avec e1 ≠ e2 (A.3), par
   Load(e1) + Load(e2) courant croissant, puis rang dans le fichier.
3. Ordre des valeurs temporelles : premier (t,k) ∈ 𝒲^pre_s puis premier
   (t,k,r) ∈ 𝒲^fin_s, dans l'ordre chronologique (salles dans l'ordre du
   fichier), qui satisfait les contraintes dynamiques B.3, C.1, C.2, D.1, D.2.
   Le couple est conservé pour les deux phases : A.5 par construction.
4. Réparation limitée : éjection d'un seul étudiant déjà affecté (au plus
   `max_ejections`, du plus récent au plus ancien), affectation de l'étudiant
   bloqué, réaffectation de l'éjecté ; restauration exacte en cas d'échec.
5. Arrêt : X complet, échec de la réparation ou budget de temps atteint.

Aucune source d'aléa : la méthode est déterministe.
"""
from __future__ import annotations

import time

from .model import Decision, ModelData, T_compat, T_exam, T_pres, W_fin, W_pre
from .schedule import PartialSolution


class Baseline:
    name = "baseline_glouton"
    deterministic = True

    def __init__(self, m: ModelData, max_ejections: int = 200):
        self.m = m
        self.max_ejections = max_ejections
        self.Wp, self.Wf, self.pairs = {}, {}, {}
        for s in m.S:
            self.Wp[s], self.Wf[s] = W_pre(m, s), W_fin(m, s)
            compat = T_compat(m, s, self.Wp[s], self.Wf[s])
            self.pairs[s] = [(e1, e2) for e1 in T_pres(m, compat) for e2 in T_exam(m, s, compat) if e1 != e2]
        self.order = sorted(m.S, key=lambda s: (not m.elig[s], len(self.pairs[s]),
                                                len(self.Wp[s]) + len(self.Wf[s]), m.rank[s]))

    # ------------------------------------------------------------ affectation
    def _first_pre(self, X: PartialSolution, s, e1, e2):
        for t, k in self.Wp[s]:
            if X.teacher_ok(e1, t, k) and X.teacher_ok(e2, t, k):
                return t, k
        return None

    def _first_fin(self, X: PartialSolution, s, e1, e2):
        sp = self.m.sup[s]
        for t, k, r in self.Wf[s]:
            if (X.room_ok(r, t, k) and X.teacher_ok(sp, t, k)
                    and X.teacher_ok(e1, t, k) and X.teacher_ok(e2, t, k)):
                return t, k, r
        return None

    def insert(self, X: PartialSolution, s: str) -> bool:
        rank = self.m.rank
        for e1, e2 in sorted(self.pairs[s], key=lambda p: (X.load[p[0]] + X.load[p[1]], rank[p[0]], rank[p[1]])):
            pre = self._first_pre(X, s, e1, e2)
            if pre is None:
                continue
            fin = None
            if self.m.elig[s]:
                # D^pre ∩ D^fin = ∅ : le choix de la pré-soutenance n'affecte pas les jours de finale.
                fin = self._first_fin(X, s, e1, e2)
                if fin is None:
                    continue
            X.assign(s, Decision(e1, e2, pre, fin))
            return True
        return False

    # ------------------------------------------------------------- réparation
    def repair(self, X: PartialSolution, s: str, done: list[str], deadline: float) -> bool:
        for victim in reversed(done[-self.max_ejections:]):
            if time.perf_counter() > deadline:
                return False
            old = X.unassign(victim)
            if self.insert(X, s):
                if self.insert(X, victim):
                    done.remove(victim)
                    done.append(victim)
                    return True
                X.unassign(s)
            X.assign(victim, old)          # restauration exacte
        return False

    # ------------------------------------------------------------------ solve
    def solve(self, time_limit: float, start: float) -> dict:
        deadline = start + time_limit
        X = PartialSolution(self.m)
        done: list[str] = []
        repairs, status = 0, "COMPLETE"
        for s in self.order:
            if time.perf_counter() > deadline:
                status = "TIME_LIMIT"
                break
            if self.insert(X, s):
                done.append(s)
                continue
            repairs += 1
            if self.repair(X, s, done, deadline):
                done.append(s)
                continue
            status = "TIME_LIMIT" if time.perf_counter() > deadline else "NO_SOLUTION"
            break
        return {"schedule": X, "status": status, "repairs": repairs, "placed": len(done)}
