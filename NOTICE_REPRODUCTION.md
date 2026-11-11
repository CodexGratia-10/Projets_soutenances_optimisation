# Planification des soutenances — Notice de reproduction

Code du groupe pour le projet de planification des soutenances (L3 IA, IFRI / UAC).

## Prérequis
- Python ≥ 3.10
- Dépendance du solveur CP-SAT : `python -m pip install -r requirements.txt`. La méthode de référence et le validateur officiel n'ont **aucune dépendance externe**.
- Exécution sur un seul thread par processus (conforme au protocole).

## Organisation du code
Le code suit scrupuleusement la formulation de `MODELISATION_ET_METHODE_OPTIMISATION.md` et reprend l'intégralité de sa notation.

| Fichier / Dossier | Rôle | Section du document théorique |
|---|---|---|
| `soutenances/model.py` | Modèle pur : données, variables `Decision`, contraintes étiquetées A.0 à D.2 (`violations`), critères f1 à f5 (`objectives`), domaines pré-calculés $\mathcal{W}^{pre}$, $\mathcal{W}^{fin}$, $T^{pres}$, $T^{exam}$ | §2.1 à 2.3, §3.2, §5.1 |
| `soutenances/schedule.py` | Solution partielle avec suivi incrémental de $\pi_{e,t,k}$ : tests dynamiques B.3, C.1, C.2, D.1, D.2 | §2.3 C, D |
| `soutenances/baseline.py` | Méthode de référence : affectation gloutonne des variables du modèle et réparation limitée | (Section Référence) |
| `soutenances/cpsat.py` | Méthode d'optimisation en 2 temps : formulation CP-SAT (OR-Tools), affectation constructive initiale bornée par l'échéance puis optimisation dans le temps restant | PARTIE II (§5, §6) |
| `soutenances/runner.py` | Chronométrage strict (budget 60 s), contrôle du modèle, export, validation officielle du fichier relu depuis le disque, comparaison modèle / validateur, écriture CSV | Protocole §5 du sujet |
| `run.py` | Point d'entrée en ligne de commande pour résoudre un cas ou une campagne complète | |
| `tests/test_validator.py` | Tests du validateur officiel : schéma, contraintes, métriques et CLI | Sujet |
| `tests/test_baseline.py` | Tests des domaines, contraintes, égalité des critères modèle / validateur, réparation, export et bout en bout | |
| `tests/test_cpsat.py` | Tests de restauration d'état, d'affectation initiale et de respect d'une échéance CP-SAT (OR-Tools requis) | |
| `resultats/baseline/` | Campagne complète de référence : `resultats.csv`, `journal.jsonl`, 30 fichiers `solutions/` et 30 rapports `validations/` | §5 du sujet |

## Commandes de reproduction

Depuis la racine du projet :
```sh
# 1. Lancer l'ensemble des tests unitaires
# OR-Tools est requis pour exécuter les tests spécifiques à CP-SAT.
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v

# 2. Résoudre une instance avec la méthode de référence (Baseline)
python run.py solve data/small_01.json --method baseline --out resultats/essai

# 3. Exécuter la campagne complète sur les 30 instances avec la méthode de référence
python run.py campaign --method baseline --out resultats/baseline

# 4. Résoudre une instance avec la méthode d'optimisation (CP-SAT) sur les graines 0..4
python run.py solve data/small_01.json --method cpsat --seeds 0 1 2 3 4 --threads 1 --out resultats/essai_cpsat

# 5. Exécuter la campagne complète sur les 30 instances avec CP-SAT (graines 0, 1, 2, 3, 4, 1 thread)
python run.py campaign --method cpsat --seeds 0 1 2 3 4 --threads 1 --out resultats/cpsat
```

Sorties produites dans le dossier `--out` :
- `resultats.csv` : une ligne par exécution, colonnes conformes au gabarit officiel `templates/resultats.csv` ;
- `solutions/<instance>__<méthode>__<graine>.json` : plannings complets acceptés par le validateur officiel ;
- `invalid/…invalid.json` : plannings complets rejetés par le validateur officiel ;
- `validations/…validation.json` : rapport du validateur officiel sur le fichier **relu depuis le disque** ;
- `partial/` : planning incomplet éventuel, conservé pour diagnostic ;
- `journal.jsonl` : environnement matériel, temps de lecture / construction / recherche / export / validation, nombre de réparations.

## Méthode de référence (`baseline_glouton`, déterministe)
La méthode affecte, étudiant par étudiant, les variables du modèle pur ($pres_s, exam_s$, jour et créneau de pré-soutenance, puis jour, créneau et salle de finale).
0. **Domaines réduits (§5.1)** : $\mathcal{W}^{pre}_s$, $\mathcal{W}^{fin}_s$, $T^{pres}_s$, $T^{exam}_s$. Les contraintes A.1, A.2, A.4, B.1, B.2, B.4 et la disponibilité de l'encadrant (B.3) sont satisfaites par construction.
1. **Ordre des étudiants**, du plus contraint au moins contraint : $s \in S_{elig}$ d'abord, puis nombre croissant de couples $(e_1, e_2)$ avec $e_1 \neq e_2$, puis $|\mathcal{W}^{pre}_s| + |\mathcal{W}^{fin}_s|$ croissant, puis ordre du fichier pour départager.
2. **Ordre des couples de jury** : $Load(e_1) + Load(e_2)$ courant croissant, puis ordre du fichier.
3. **Premier placement compatible** : premier $(t,k)$ de $\mathcal{W}^{pre}_s$, puis premier $(t,k,r)$ de $\mathcal{W}^{fin}_s$ dans l'ordre chronologique, qui respectent les contraintes dynamiques B.3, C.1, C.2, D.1 et D.2. Le même couple sert aux deux phases, donc A.5 est garantie par construction.
4. **Réparation limitée** : on retire un étudiant déjà placé (au plus 200 candidats, du plus récent au plus ancien), on place l'étudiant bloqué, puis on réinsère l'étudiant retiré. En cas d'échec, l'état précédent est restauré.
5. **Arrêt** : planning complet (`COMPLETE`), échec (`NO_SOLUTION`) ou budget de 60 s (`TIME_LIMIT`).

**Contrôles** : avant l'export, `violations` vérifie toutes les contraintes du modèle et `objectives` calcule $f_1$ à $f_5$. Après l'export, le validateur officiel recalcule les mêmes valeurs sur le fichier. Le journal enregistre `model_f`, `model_violations` et `model_validator_agree`.

## Budget et mesures
Le chronomètre démarre après la lecture du JSON. `build_seconds` couvre le prétraitement et la construction du modèle ; `search_seconds` couvre la recherche. Pour CP-SAT, une échéance unique borne aussi bien l'affectation constructive initiale que la recherche du solveur : aucun temps minimal artificiel n'est ajouté après épuisement du budget. L'export et la validation sont mesurés à part, dans le journal, hors budget. Comme la méthode de référence est déterministe, il y a une seule exécution par instance et la colonne `seed` vaut `deterministe`.

