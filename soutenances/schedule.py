"""Solution partielle X avec suivi incrémental des termes dynamiques du modèle.

Les contraintes A.* et B.* sont absorbées par les domaines réduits (§5.1) ;
seules restent à tester, au moment de chaque affectation, les contraintes qui
dépendent des autres étudiants :
  - B.3 pour pres_s et exam_s (leur disponibilité dépend du créneau choisi) ;
  - C.1 via π_{e,t,k} ;  C.2 via l'occupation des salles ;
  - D.1 via Σ_k π_{e,t,k} ;  D.2 via le nombre de finales par salle et par jour.
"""
from __future__ import annotations

from collections import defaultdict

from .model import Decision, ModelData, Solution, jury, sessions, to_solution


class PartialSolution:
    def __init__(self, m: ModelData):
        self.m = m
        self.X: Solution = {}
        self.pi: set[tuple] = set()                     # {(e,t,k) | π_{e,t,k} = 1}
        self.day_T: dict[tuple, int] = defaultdict(int)  # Σ_k π_{e,t,k}
        self.room: set[tuple] = set()                    # {(r,t,k) occupés}
        self.day_R: dict[tuple, int] = defaultdict(int)  # finales par (r,t)
        self.load: dict[str, int] = {e: 0 for e in m.T}  # Load(e)

    def backup(self) -> tuple:
        """Capture un instantané complet pour une réparation réversible."""
        return (
            dict(self.X),
            set(self.pi),
            dict(self.day_T),
            set(self.room),
            dict(self.day_R),
            dict(self.load),
        )

    def restore(self, state: tuple) -> None:
        """Restaure exactement un instantané produit par :meth:`backup`."""
        X, pi, day_T, room, day_R, load = state
        self.X = dict(X)
        self.pi = set(pi)
        self.day_T = defaultdict(int, day_T)
        self.room = set(room)
        self.day_R = defaultdict(int, day_R)
        self.load = dict(load)

    # -- tests dynamiques
    def teacher_ok(self, e: str, t: int, k: int) -> bool:
        """B.3 ∧ C.1 ∧ D.1 pour l'enseignant e au créneau (t,k)."""
        return ((t, k) in self.m.A_T[e] and (e, t, k) not in self.pi
                and self.day_T[(e, t)] < self.m.cap_T[e])

    def room_ok(self, r: str, t: int, k: int) -> bool:
        """C.2 ∧ D.2 (B.4 est déjà garanti par 𝒲^fin_s)."""
        return (r, t, k) not in self.room and self.day_R[(r, t)] < self.m.cap_R[r]

    # -- affectation / désaffectation des variables d'un étudiant
    def _apply(self, s: str, x: Decision, sign: int) -> None:
        for _, phase, t, k, r in sessions(self.m, {s: x}):
            for e in jury(self.m, s, x, phase):
                (self.pi.add if sign > 0 else self.pi.discard)((e, t, k))
                self.day_T[(e, t)] += sign
                self.load[e] += sign
            if r is not None:
                (self.room.add if sign > 0 else self.room.discard)((r, t, k))
                self.day_R[(r, t)] += sign

    def assign(self, s: str, x: Decision) -> None:
        self._apply(s, x, +1)
        self.X[s] = x

    def unassign(self, s: str) -> Decision:
        x = self.X.pop(s)
        self._apply(s, x, -1)
        return x

    def is_complete(self) -> bool:
        return len(self.X) == len(self.m.S)

    def to_solution(self) -> dict:
        return to_solution(self.m, self.X)
