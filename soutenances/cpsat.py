"""Solveur d'optimisation par Programmation par Contraintes booléenne (Google OR-Tools CP-SAT).

Ce module implémente la PARTIE II de MODELISATION_ET_METHODE_OPTIMISATION.md :
  - §5.1 Pré-calcul et filtrage statique des domaines admissibles
  - §5.2 Expansion booléenne des variables de décision (One-Hot)
  - §5.3 Élimination des redondances et canalisation directe vers π_{e,t,k}
  - §5.4 Linéarisation compacte et exacte des 5 objectifs (f1, f2, f3, f4, f5)
  - §5.5 Variables d'écart souples (slacks ξ_e) pour régulariser la charge
  - §6 Résolution structurée en 2 temps : Affectation complète (Faisabilité) puis Optimisation
"""
from __future__ import annotations

import time
from collections import defaultdict

from ortools.sat.python import cp_model

from .model import (
    Decision,
    ModelData,
    T_compat,
    T_exam,
    T_pres,
    W_fin,
    W_pre,
)
from .schedule import PartialSolution


class _SolutionRecorder(cp_model.CpSolverSolutionCallback):
    """Callback temps réel pour intercepter chaque solution valide et mesurer first_feasible."""

    def __init__(self, solver: CPSATSolver, start_time: float):
        super().__init__()
        self.solver = solver
        self.start_time = start_time
        self.first_feasible_seconds: float | None = None
        self.best_schedule: PartialSolution | None = None

    def on_solution_callback(self) -> None:
        now = time.perf_counter()
        if self.first_feasible_seconds is None:
            self.first_feasible_seconds = now - self.start_time
        self.best_schedule = self.solver._extract_solution(self)


class CPSATSolver:
    name = "cpsat_ortools"
    deterministic = False

    def __init__(
        self,
        m: ModelData,
        seed: int = 0,
        threads: int = 1,
    ):
        self.m = m
        self.seed = seed
        self.threads = threads

        # 1. Domaines réduits par arc-consistance (§5.1)
        self.Wp: dict[str, list[tuple[int, int]]] = {}
        self.Wf: dict[str, list[tuple[int, int, str]]] = {}
        self.T_pres_s: dict[str, list[str]] = {}
        self.T_exam_s: dict[str, list[str]] = {}
        self.pairs_s: dict[str, list[tuple[str, str]]] = {}

        for s in m.S:
            self.Wp[s] = W_pre(m, s)
            self.Wf[s] = W_fin(m, s)
            compat = T_compat(m, s, self.Wp[s], self.Wf[s])
            self.T_pres_s[s] = T_pres(m, compat)
            self.T_exam_s[s] = T_exam(m, s, compat)
            self.pairs_s[s] = [
                (e1, e2)
                for e1 in self.T_pres_s[s]
                for e2 in self.T_exam_s[s]
                if e1 != e2
            ]

        # 2. Construction du modèle CP-SAT simplifié
        self.model = cp_model.CpModel()
        self._build_variables()
        self._add_hard_constraints()
        self._add_objectives()

    # --------------------------------------------------------------------------
    # §5.2 Expansion booléenne des variables de décision
    # --------------------------------------------------------------------------
    def _build_variables(self) -> None:
        m = self.m
        self.p: dict[tuple[str, str], cp_model.IntVar] = {}
        self.x: dict[tuple[str, str], cp_model.IntVar] = {}
        self.y_pre: dict[tuple[str, tuple[int, int]], cp_model.IntVar] = {}
        self.y_fin: dict[tuple[str, tuple[int, int, str]], cp_model.IntVar] = {}

        for s in m.S:
            # Président (A.1, A.5)
            for e in self.T_pres_s[s]:
                self.p[(s, e)] = self.model.NewBoolVar(f"pres_{s}_{e}")
            self.model.AddExactlyOne(self.p[(s, e)] for e in self.T_pres_s[s])

            # Examinateur (A.2, A.5)
            for e in self.T_exam_s[s]:
                self.x[(s, e)] = self.model.NewBoolVar(f"exam_{s}_{e}")
            self.model.AddExactlyOne(self.x[(s, e)] for e in self.T_exam_s[s])

            # Créneau pré-soutenance (B.1, B.2)
            for w in self.Wp[s]:
                self.y_pre[(s, w)] = self.model.NewBoolVar(f"pre_{s}_{w[0]}_{w[1]}")
            self.model.AddExactlyOne(self.y_pre[(s, w)] for w in self.Wp[s])

            # Créneau finale (B.1, B.2, B.4) si admissible
            if m.elig[s]:
                for w in self.Wf[s]:
                    self.y_fin[(s, w)] = self.model.NewBoolVar(
                        f"fin_{s}_{w[0]}_{w[1]}_{w[2]}"
                    )
                self.model.AddExactlyOne(self.y_fin[(s, w)] for w in self.Wf[s])

    # --------------------------------------------------------------------------
    # §2.3 & §5.3 Contraintes dures et canalisation compacte
    # --------------------------------------------------------------------------
    def _add_hard_constraints(self) -> None:
        m = self.m

        # A.3 & A.4 Disjonction interne du jury (Président ≠ Examinateur)
        for s in m.S:
            common = set(self.T_pres_s[s]) & set(self.T_exam_s[s])
            for e in common:
                self.model.Add(self.p[(s, e)] + self.x[(s, e)] <= 1)

        # C.2 Non-chevauchement des salles physiques (finales)
        fin_by_room_slot = defaultdict(list)
        fin_by_room_day = defaultdict(list)
        for s in m.S_elig:
            for w in self.Wf[s]:
                t, k, r = w
                fin_by_room_slot[(r, t, k)].append(self.y_fin[(s, w)])
                fin_by_room_day[(r, t)].append(self.y_fin[(s, w)])

        for rtk, y_vars in fin_by_room_slot.items():
            self.model.AddAtMostOne(y_vars)

        # D.2 Plafond journalier des salles
        for rt, y_vars in fin_by_room_day.items():
            self.model.Add(sum(y_vars) <= m.cap_R[rt[0]])

        # Agrégation de la finale au créneau (t, k) pour chaque étudiant admissible
        self.z_fin: dict[tuple[str, int, int], cp_model.IntVar] = {}
        for s in m.S_elig:
            by_tk = defaultdict(list)
            for w in self.Wf[s]:
                by_tk[(w[0], w[1])].append(self.y_fin[(s, w)])
            for (t, k), y_vars in by_tk.items():
                if len(y_vars) == 1:
                    self.z_fin[(s, t, k)] = y_vars[0]
                else:
                    z_var = self.model.NewBoolVar(f"z_fin_{s}_{t}_{k}")
                    self.model.Add(z_var == sum(y_vars))
                    self.z_fin[(s, t, k)] = z_var

        # Précalcul unique de role_s_e (président OU examinateur)
        self.role_s_e: dict[tuple[str, str], cp_model.IntVar] = {}
        for s in m.S:
            cand_t = set(self.T_pres_s[s]) | set(self.T_exam_s[s])
            for e in cand_t:
                has_p = (s, e) in self.p
                has_x = (s, e) in self.x
                if has_p and has_x:
                    rv = self.model.NewBoolVar(f"r_{s}_{e}")
                    self.model.Add(rv == self.p[(s, e)] + self.x[(s, e)])
                    self.role_s_e[(s, e)] = rv
                elif has_p:
                    self.role_s_e[(s, e)] = self.p[(s, e)]
                else:
                    self.role_s_e[(s, e)] = self.x[(s, e)]

        # B.3 Clauses directes d'incompatibilité de l'enseignant
        for s in m.S:
            cand_t = set(self.T_pres_s[s]) | set(self.T_exam_s[s])
            for t, k in self.Wp[s]:
                y_var = self.y_pre[(s, (t, k))]
                for e in cand_t:
                    if (t, k) not in m.A_T[e]:
                        self.model.AddAtMostOne([self.role_s_e[(s, e)], y_var])

        for s in m.S_elig:
            sp = m.sup[s]
            cand_t = (set(self.T_pres_s[s]) | set(self.T_exam_s[s])) - {sp}
            fin_slots = {(w[0], w[1]) for w in self.Wf[s]}
            for t, k in fin_slots:
                zv = self.z_fin[(s, t, k)]
                for e in cand_t:
                    if (t, k) not in m.A_T[e]:
                        self.model.AddAtMostOne([self.role_s_e[(s, e)], zv])

        # Canalisation de la participation (uniquement pour les créneaux disponibles)
        tau_pre = defaultdict(list)
        tau_fin = defaultdict(list)

        for s in m.S:
            cand_t = set(self.T_pres_s[s]) | set(self.T_exam_s[s])
            for t, k in self.Wp[s]:
                y_var = self.y_pre[(s, (t, k))]
                for e in cand_t:
                    if (t, k) in m.A_T[e]:
                        tau = self.model.NewBoolVar("")
                        self.model.AddMultiplicationEquality(
                            tau, [self.role_s_e[(s, e)], y_var]
                        )
                        tau_pre[(e, t, k)].append(tau)

        for s in m.S_elig:
            sp = m.sup[s]
            cand_t = (set(self.T_pres_s[s]) | set(self.T_exam_s[s])) - {sp}
            fin_slots = {(w[0], w[1]) for w in self.Wf[s]}
            for t, k in fin_slots:
                zv = self.z_fin[(s, t, k)]
                tau_fin[(sp, t, k)].append(zv)
                for e in cand_t:
                    if (t, k) in m.A_T[e]:
                        tau = self.model.NewBoolVar("")
                        self.model.AddMultiplicationEquality(
                            tau, [self.role_s_e[(s, e)], zv]
                        )
                        tau_fin[(e, t, k)].append(tau)

        # C.1 Non-chevauchement des enseignants & définition de π_{e,t,k}
        self.pi: dict[tuple[str, int, int], cp_model.IntVar] = {}
        for e in m.T:
            for t in m.D:
                tau_map = tau_pre if t in m.D_pre else tau_fin
                for k in m.K:
                    active = tau_map.get((e, t, k), [])
                    if not active:
                        continue
                    self.model.AddAtMostOne(active)
                    pi_var = self.model.NewBoolVar(f"pi_{e}_{t}_{k}")
                    self.model.Add(pi_var == sum(active))
                    self.pi[(e, t, k)] = pi_var

        # D.1 Plafond journalier de chaque enseignant
        for e in m.T:
            for t in m.D:
                pi_day = [
                    self.pi[(e, t, k)] for k in m.K if (e, t, k) in self.pi
                ]
                if pi_day:
                    self.model.Add(sum(pi_day) <= m.cap_T[e])

    # --------------------------------------------------------------------------
    # §5.4 Linéarisation compacte et exacte des 5 objectifs
    # --------------------------------------------------------------------------
    def _add_objectives(self) -> None:
        m = self.m
        k_max = len(m.K)

        # -------------------------------------------------- f1 : teacher_presence_days
        self.u: dict[tuple[str, int], cp_model.IntVar] = {}
        for e in m.T:
            for t in m.D:
                pi_day = [
                    self.pi[(e, t, k)] for k in m.K if (e, t, k) in self.pi
                ]
                if pi_day:
                    u_var = self.model.NewBoolVar(f"u_{e}_{t}")
                    self.model.AddMaxEquality(u_var, pi_day)
                    self.u[(e, t)] = u_var

        f1_expr = sum(self.u.values()) if self.u else 0

        # -------------------------------------------------- f2 : teacher_idle_slots
        idle_terms = []
        for (e, t), u_var in self.u.items():
            pi_day = [
                (k, self.pi[(e, t, k)]) for k in m.K if (e, t, k) in self.pi
            ]
            first_k = self.model.NewIntVar(0, k_max - 1, f"first_{e}_{t}")
            last_k = self.model.NewIntVar(0, k_max - 1, f"last_{e}_{t}")
            span = self.model.NewIntVar(0, k_max, f"span_{e}_{t}")

            for k, pi_v in pi_day:
                self.model.Add(first_k <= k).OnlyEnforceIf(pi_v)
                self.model.Add(last_k >= k).OnlyEnforceIf(pi_v)

            self.model.Add(span >= last_k - first_k + 1).OnlyEnforceIf(u_var)
            self.model.Add(span == 0).OnlyEnforceIf(u_var.Not())

            idle_et = span - sum(pi_v for _, pi_v in pi_day)
            idle_terms.append(idle_et)

        f2_expr = sum(idle_terms) if idle_terms else 0

        # -------------------------------------------------- f3 : teacher_load_range & slacks
        self.load: dict[str, cp_model.LinearExpr] = {}
        for e in m.T:
            pi_all = [
                self.pi[(e, t, k)]
                for t in m.D
                for k in m.K
                if (e, t, k) in self.pi
            ]
            self.load[e] = sum(pi_all) if pi_all else 0

        max_possible = 2 * len(m.S)
        l_min = self.model.NewIntVar(0, max_possible, "L_min")
        l_max = self.model.NewIntVar(0, max_possible, "L_max")

        for e in m.T:
            self.model.Add(self.load[e] >= l_min)
            self.model.Add(self.load[e] <= l_max)

        f3_expr = l_max - l_min

        l_bar = (2 * len(m.S) + 3 * len(m.S_elig)) / max(1, len(m.T))
        delta_target = max(2, int(round(0.35 * l_bar)))
        threshold = int(l_bar) + delta_target

        slack_terms = []
        for e in m.T:
            xi = self.model.NewIntVar(0, max_possible, f"xi_{e}")
            self.model.Add(self.load[e] <= threshold + xi)
            slack_terms.append(xi)

        slack_expr = sum(slack_terms) if slack_terms else 0

        # -------------------------------------------------- f4 : supervisor_group_breaks
        brk_terms = []
        by_sup_pre = defaultdict(list)
        for s in m.S:
            by_sup_pre[m.sup[s]].append(s)

        for sup, sup_students in by_sup_pre.items():
            beta_pre_sup = []
            for t in m.D_pre:
                for k in m.K:
                    cand_y = [
                        self.y_pre[(s, (t, k))]
                        for s in sup_students
                        if (s, (t, k)) in self.y_pre
                    ]
                    if not cand_y:
                        continue
                    alpha_k = self.model.NewBoolVar(f"ap_{sup}_{t}_{k}")
                    self.model.AddMaxEquality(alpha_k, cand_y)

                    cand_prev = [
                        self.y_pre[(s, (t, k - 1))]
                        for s in sup_students
                        if (s, (t, k - 1)) in self.y_pre
                    ]
                    beta_k = self.model.NewBoolVar(f"bp_{sup}_{t}_{k}")
                    if not cand_prev:
                        self.model.Add(beta_k == alpha_k)
                    else:
                        alpha_prev = self.model.NewBoolVar(f"ap_prev_{sup}_{t}_{k}")
                        self.model.AddMaxEquality(alpha_prev, cand_prev)
                        self.model.Add(beta_k >= alpha_k - alpha_prev)
                    beta_pre_sup.append(beta_k)

            if beta_pre_sup:
                g_pre = sum(beta_pre_sup)
                brk = self.model.NewIntVar(0, len(beta_pre_sup), f"brk_pre_{sup}")
                self.model.Add(brk >= g_pre - 1)
                self.model.Add(brk >= 0)
                brk_terms.append(brk)

        by_sup_fin = defaultdict(list)
        for s in m.S_elig:
            by_sup_fin[m.sup[s]].append(s)

        for sup, sup_students in by_sup_fin.items():
            beta_fin_sup = []
            for t in m.D_fin:
                for r in m.R:
                    for k in m.K:
                        w = (t, k, r)
                        cand_y = [
                            self.y_fin[(s, w)]
                            for s in sup_students
                            if (s, w) in self.y_fin
                        ]
                        if not cand_y:
                            continue
                        alpha_k = (
                            cand_y[0]
                            if len(cand_y) == 1
                            else self.model.NewBoolVar(f"af_{sup}_{t}_{r}_{k}")
                        )
                        if len(cand_y) > 1:
                            self.model.Add(alpha_k == sum(cand_y))

                        w_prev = (t, k - 1, r)
                        cand_prev = [
                            self.y_fin[(s, w_prev)]
                            for s in sup_students
                            if (s, w_prev) in self.y_fin
                        ]
                        beta_k = self.model.NewBoolVar(f"bf_{sup}_{t}_{r}_{k}")
                        if not cand_prev:
                            self.model.Add(beta_k >= alpha_k)
                        else:
                            alpha_prev = (
                                cand_prev[0]
                                if len(cand_prev) == 1
                                else self.model.NewBoolVar(
                                    f"af_prev_{sup}_{t}_{r}_{k}"
                                )
                            )
                            if len(cand_prev) > 1:
                                self.model.Add(alpha_prev == sum(cand_prev))
                            self.model.Add(beta_k >= alpha_k - alpha_prev)
                        beta_fin_sup.append(beta_k)

            if beta_fin_sup:
                g_fin = sum(beta_fin_sup)
                brk = self.model.NewIntVar(0, len(beta_fin_sup), f"brk_fin_{sup}")
                self.model.Add(brk >= g_fin - 1)
                self.model.Add(brk >= 0)
                brk_terms.append(brk)

        f4_expr = sum(brk_terms) if brk_terms else 0

        # -------------------------------------------------- f5 : distinct_jury_pairs (inversion rapide)
        gamma_pairs = {}
        for s in m.S:
            for e1, e2 in self.pairs_s[s]:
                pair = (e1, e2)
                if pair not in gamma_pairs:
                    gamma_pairs[pair] = self.model.NewBoolVar(f"g_{e1}_{e2}")
                self.model.Add(
                    gamma_pairs[pair] >= self.p[(s, e1)] + self.x[(s, e2)] - 1
                )

        f5_expr = sum(gamma_pairs.values()) if gamma_pairs else 0

        # -------------------------------------------------- Fonction Objectif Globale
        self.model.Minimize(
            100 * f1_expr
            + 10 * f2_expr
            + 5 * f3_expr
            + 8 * f4_expr
            + 15 * f5_expr
            + 20 * slack_expr
        )

    # --------------------------------------------------------------------------
    # Phase 1 : Affectation complète interne (Faisabilité pure)
    # --------------------------------------------------------------------------
    def _compute_initial_assignment(self, deadline: float) -> PartialSolution | None:
        """Construit une solution initiale sans dépasser l'échéance fournie."""
        m = self.m
        sched = PartialSolution(m)
        order = sorted(
            m.S,
            key=lambda s: (
                not m.elig[s],
                len(self.pairs_s[s]),
                len(self.Wp[s]) + len(self.Wf[s]),
                m.rank[s],
            ),
        )

        def first_pre(X: PartialSolution, s: str, e1: str, e2: str):
            for t, k in self.Wp[s]:
                if time.perf_counter() >= deadline:
                    return None
                if X.teacher_ok(e1, t, k) and X.teacher_ok(e2, t, k):
                    return t, k
            return None

        def first_fin(X: PartialSolution, s: str, e1: str, e2: str):
            sp = m.sup[s]
            for t, k, r in self.Wf[s]:
                if time.perf_counter() >= deadline:
                    return None
                if (
                    X.room_ok(r, t, k)
                    and X.teacher_ok(sp, t, k)
                    and X.teacher_ok(e1, t, k)
                    and X.teacher_ok(e2, t, k)
                ):
                    return t, k, r
            return None

        def insert(X: PartialSolution, s: str) -> bool:
            if time.perf_counter() >= deadline:
                return False
            for e1, e2 in sorted(
                self.pairs_s[s],
                key=lambda p: (
                    X.load[p[0]] + X.load[p[1]],
                    m.rank[p[0]],
                    m.rank[p[1]],
                ),
            ):
                if time.perf_counter() >= deadline:
                    return False
                pre = first_pre(X, s, e1, e2)
                if pre is None:
                    continue
                fin = None
                if m.elig[s]:
                    fin = first_fin(X, s, e1, e2)
                    if fin is None:
                        continue
                X.assign(s, Decision(e1, e2, pre, fin))
                return True
            return False

        done: list[str] = []
        pending = list(order)
        max_repairs = 200
        repairs = 0

        while pending:
            if time.perf_counter() >= deadline:
                return None
            cur = pending.pop(0)
            if insert(sched, cur):
                done.append(cur)
            else:
                placed = False
                for victim in reversed(done):
                    if time.perf_counter() >= deadline or repairs >= max_repairs:
                        break
                    repairs += 1
                    state = sched.backup()
                    sched.unassign(victim)
                    if insert(sched, cur) and insert(sched, victim):
                        placed = True
                        done.append(cur)
                        break
                    sched.restore(state)
                if not placed:
                    return None

        return sched if sched.is_complete() else None

    # --------------------------------------------------------------------------
    # Extraction d'une solution valide depuis le solveur
    # --------------------------------------------------------------------------
    def _extract_solution(
        self, response: cp_model.CpSolverSolutionCallback | cp_model.CpSolver
    ) -> PartialSolution:
        schedule = PartialSolution(self.m)
        val = response.Value if hasattr(response, "Value") else response.value

        for s in self.m.S:
            pres = None
            for e in self.T_pres_s[s]:
                if val(self.p[(s, e)]) == 1:
                    pres = e
                    break

            exam = None
            for e in self.T_exam_s[s]:
                if val(self.x[(s, e)]) == 1:
                    exam = e
                    break

            pre = None
            for w in self.Wp[s]:
                if val(self.y_pre[(s, w)]) == 1:
                    pre = w
                    break

            fin = None
            if self.m.elig[s]:
                for w in self.Wf[s]:
                    if val(self.y_fin[(s, w)]) == 1:
                        fin = w
                        break

            if pres is not None and exam is not None and pre is not None:
                schedule.assign(s, Decision(pres, exam, pre, fin))

        return schedule

    # --------------------------------------------------------------------------
    # Résolution en 2 temps sous budget strict de 60 secondes
    # --------------------------------------------------------------------------
    def solve(self, time_limit: float, start: float) -> dict:
        # Une échéance unique couvre la construction initiale ET la recherche CP-SAT.
        deadline = start + max(0.0, time_limit)

        # Phase 1 : affectation constructive, interrompue à l'échéance.
        initial_sched = self._compute_initial_assignment(deadline) if time.perf_counter() < deadline else None
        first_feasible = None

        if initial_sched is not None and initial_sched.is_complete():
            first_feasible = time.perf_counter() - start
            best_sched = initial_sched
            # Injection de l'affectation dans le modèle CP-SAT comme point de départ
            for s in self.m.S:
                dec = initial_sched.X[s]
                for e in self.T_pres_s[s]:
                    self.model.AddHint(self.p[(s, e)], 1 if e == dec.pres else 0)
                for e in self.T_exam_s[s]:
                    self.model.AddHint(self.x[(s, e)], 1 if e == dec.exam else 0)
                for w in self.Wp[s]:
                    self.model.AddHint(self.y_pre[(s, w)], 1 if w == dec.pre else 0)
                if self.m.elig[s]:
                    for w in self.Wf[s]:
                        self.model.AddHint(
                            self.y_fin[(s, w)], 1 if w == dec.fin else 0
                        )
        else:
            best_sched = None

        # Phase 2 : Optimisation des critères par CP-SAT
        solver = cp_model.CpSolver()
        solver.parameters.random_seed = self.seed
        solver.parameters.num_search_workers = self.threads
        solver.parameters.cp_model_probing_level = 0

        remaining = deadline - time.perf_counter()
        recorder = _SolutionRecorder(self, start)
        if best_sched is not None:
            recorder.best_schedule = best_sched
            recorder.first_feasible_seconds = first_feasible

        # Vérifier la cohérence syntaxique du modèle avant de lancer le solveur.
        # Cela permet de distinguer un modèle invalide d'une preuve d'infaisabilité.
        model_error = self.model.Validate()
        status_code = cp_model.MODEL_INVALID if model_error else None
        if not model_error and remaining > 0.01:
            # Ne jamais lancer CP-SAT avec un budget artificiel après l'échéance.
            solver.parameters.max_time_in_seconds = remaining
            status_code = solver.Solve(self.model, recorder)

        # Récupération de la meilleure solution complète déjà connue.
        if recorder.best_schedule is not None and recorder.best_schedule.is_complete():
            best_sched = recorder.best_schedule
        elif status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            best_sched = self._extract_solution(solver)

        has_complete = best_sched is not None and best_sched.is_complete()
        if status_code == cp_model.MODEL_INVALID:
            status_str = "MODEL_INVALID"
        elif status_code == cp_model.INFEASIBLE:
            # Une affectation initiale complète et indépendante existe : le modèle CP-SAT
            # contredit alors la faisabilité métier et doit être signalé comme tel.
            status_str = "MODEL_CONFLICT" if has_complete else "INFEASIBLE"
        elif has_complete:
            if status_code == cp_model.OPTIMAL:
                status_str = "OPTIMAL"
            elif status_code in (None, cp_model.UNKNOWN):
                status_str = "FEASIBLE_TIME_LIMIT"
            else:
                status_str = "FEASIBLE"
            if first_feasible is None:
                first_feasible = recorder.first_feasible_seconds or (time.perf_counter() - start)
        else:
            status_str = "TIME_LIMIT" if status_code in (None, cp_model.UNKNOWN) else "NO_SOLUTION"
            first_feasible = None

        # Garantir un objet Planning partiel dans tous les cas sans solution complète.
        # Ce repli commun couvre aussi MODEL_INVALID et INFEASIBLE.
        if best_sched is None:
            best_sched = PartialSolution(self.m)

        return {
            "schedule": best_sched,
            "status": status_str,
            "first_feasible_seconds": first_feasible,
            "placed": len(best_sched.X),
            "repairs": 0,
        }
