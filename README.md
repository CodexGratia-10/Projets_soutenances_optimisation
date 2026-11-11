# Planification automatique de soutenances — Projet 2026–2027

**Université d'Abomey-Calavi · IFRI · Licence 3 Intelligence Artificielle**

Ce dépôt contient le modèle, deux méthodes de planification (une méthode gloutonne de référence et un solveur CP-SAT), les 30 instances du sujet, le validateur officiel fourni avec le projet et les tests associés.

## Démarrage rapide

Python 3.10 ou ultérieur est requis.

```bash
# Installer OR-Tools pour utiliser la méthode CP-SAT
python -m pip install -r requirements.txt

# Exécuter les tests
python -m unittest discover -s tests -v

# Valider l'exemple fourni
python validator.py examples/demo_instance.json examples/demo_solution.json

# Résoudre une instance avec la méthode de référence (sans dépendance externe)
python run.py solve data/small_01.json --method baseline --out resultats/essai

# Résoudre une instance avec CP-SAT (OR-Tools requis)
python run.py solve data/small_01.json --method cpsat --seeds 0 --threads 1 --out resultats/essai_cpsat
```

## Organisation du dépôt

- `soutenances/model.py` : données, domaines réduits, contraintes et calcul des critères.
- `soutenances/schedule.py` : état incrémental d'un planning partiel et instantanés pour les réparations.
- `soutenances/baseline.py` : méthode gloutonne déterministe de référence avec réparation limitée.
- `soutenances/cpsat.py` : formulation CP-SAT, affectation initiale et optimisation sous échéance.
- `soutenances/runner.py` et `run.py` : exécution, chronométrage, export CSV/JSONL et validation après relecture du fichier.
- `validator.py` : validateur de référence fourni avec le sujet.
- `tests/` : tests du validateur, du modèle, de la méthode de référence et des mécanismes CP-SAT.
- `data/` : 30 instances et manifeste.
- `examples/` : instance et solution de démonstration.
- `Exigences_projet_soutenances.md` et `MODELISATION_ET_METHODE_OPTIMISATION.md` : exigences et formulation détaillée.
- `NOTICE_REPRODUCTION.md` : commandes et protocole expérimental.

## Campagnes expérimentales

La campagne complète de référence :

```bash
python run.py campaign --method baseline --out resultats/baseline
```

La campagne CP-SAT avec cinq graines et un thread :

```bash
python run.py campaign --method cpsat --seeds 0 1 2 3 4 --threads 1 --out resultats/cpsat
```

Chaque exécution écrit une ligne dans `resultats.csv`, un événement dans `journal.jsonl`, une solution (ou un planning partiel de diagnostic) et un rapport du validateur. Utiliser un nouveau dossier `--out` pour chaque campagne : les CSV et journaux sont ajoutés aux fichiers existants et ne doivent pas être mélangés entre plusieurs campagnes indépendantes.

Le budget de résolution couvre la construction du modèle et la recherche. Pour CP-SAT, l'affectation constructive initiale et la recherche CP-SAT partagent une même échéance ; la recherche n'est pas démarrée si le budget est épuisé.

## Interprétation des statuts CP-SAT

- `OPTIMAL` : CP-SAT a prouvé l'optimalité.
- `FEASIBLE` : une solution complète a été trouvée, sans preuve d'optimalité.
- `FEASIBLE_TIME_LIMIT` : une solution complète (notamment l'affectation initiale) est disponible, mais le temps est épuisé avant preuve d'optimalité.
- `TIME_LIMIT` : le budget est épuisé sans planning complet.
- `NO_SOLUTION` : la recherche s'est terminée sans planning complet, sans preuve d'infaisabilité.
- `INFEASIBLE` : CP-SAT a prouvé l'infaisabilité du modèle encodé ; ce résultat doit être interprété avec prudence si la formulation est en cause.
- `MODEL_INVALID` : OR-Tools a rejeté la formulation.
- `MODEL_CONFLICT` : l'affectation constructive trouve un planning complet, mais CP-SAT déclare le modèle infaisable ; il faut alors investiguer une incohérence du modèle.
- Le suffixe `_INVALID_SOLUTION` signale qu'un planning complet a échoué à la validation officielle. Il est rangé dans `invalid/`, jamais dans `solutions/`.
- Le suffixe `_OVER_BUDGET` signale un dépassement mesuré du budget global.

Seuls les fichiers relus depuis le disque et acceptés par le validateur sont placés dans `solutions/`. Les plannings incomplets sont placés dans `partial/`, et les plannings complets rejetés par le validateur dans `invalid/`.

## Limites et livrables académiques

Ce dépôt de code et ses journaux ne remplacent pas le rapport final demandé par le sujet. Le rapport (8 à 12 pages), les supports de soutenance et le bilan de contribution de chaque membre doivent être préparés et vérifiés séparément. Les résultats historiques CP-SAT doivent être régénérés dans un dossier neuf avant toute comparaison : un journal ou un CSV cumulatif provenant de plusieurs campagnes ne constitue pas un échantillon expérimental propre.
