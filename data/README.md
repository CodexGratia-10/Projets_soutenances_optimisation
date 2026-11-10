# Données synthétiques V4 — dictionnaire et usage

Outils de résolution de problèmes d’optimisation  
Année académique 2026 - 2027  
Université d’Abomey-Calavi  
Institut de Formation et de Recherche en Informatique (IFRI)  
Licence 3 en Intelligence Artificielle  
Chargé du cours : Dr Ing. (MC) Houndji Vinasetan Ratheil — https://ratheil.info

Ce jeu est entièrement fictif. Il ne décrit aucun établissement, aucune règle officielle ni aucune personne réelle. Les identifiants anonymes sont créés pour ce projet. L'encadrant est aussi le rapporteur : il s'agit d'une seule personne.

## Collection

- 10 petites instances : 12 à 20 étudiants (`small_01.json` à `small_10.json`).
- 10 moyennes : 40 à 58 étudiants (`medium_01.json` à `medium_10.json`).
- 10 grandes : 100 à 136 étudiants (`large_01.json` à `large_10.json`).
- Chaque cohorte comporte des étudiants admissibles et non admissibles à la phase finale.
- `manifest.json` et `manifest.csv` donnent les effectifs, les paramètres, la graine et le SHA-256 de chaque fichier.
- Les variantes changent les disponibilités, les nombres de domaines/enseignants/salles, l'admissibilité, les plafonds journaliers, les périodes communes. Deux instances de même effectif ne sont pas des copies.

## Dictionnaire compact

| Champ | Sens |
|---|---|
| `schema_version` | Version du contrat, chaîne `4.0` |
| `instance_id`, `size`, `seed` | Identifiant, classe de taille et graine de génération |
| `days` | Nombre de jours ; indices entiers de 0 à `days-1` |
| `slots_per_day` | Nombre de créneaux égaux par jour ; indices de 0 à `slots_per_day-1` |
| `predefence_days` | Jours autorisés pour toutes les pré-soutenances ; tableau non vide d’indices uniques |
| `final_defence_days` | Jours autorisés pour toutes les finales ; tableau non vide d’indices uniques |
| `domains` | Identifiants des domaines scientifiques |
| `teachers[].id` | Identifiant d'un enseignant |
| `teachers[].domains` | Domaines que cet enseignant peut examiner |
| `teachers[].eligible_roles` | Rôles autorisés : `president`, `examiner` ; liste éventuellement vide |
| `max_sessions_per_day` | Plafond quotidien : toutes les séances pour un enseignant ; finales uniquement pour une salle |
| `students[].domain` | Domaine scientifique du projet de l'étudiant |
| `students[].supervisor_id` | Enseignant encadrant, qui est également rapporteur à la finale |
| `students[].eligible_final` | Booléen : vrai exige une finale, faux interdit une finale |
| `availability` | Liste de jours et de leurs créneaux disponibles ; absence = indisponibilité |
| `sessions[].student_id`, `phase` | Étudiant et phase de la séance |
| `sessions[].day`, `slot` | Jour et créneau choisis |
| `sessions[].room_id` | Champ obligatoire : `null` pour une pré-soutenance en ligne ; identifiant de salle pour une finale |
| `sessions[].president_id`, `examiner_id` | Composition choisie du binôme de jury |

Tous les étudiants doivent passer exactement une pré-soutenance en ligne, sans salle. Aucune disponibilité, occupation ou limite quotidienne de salle ne s’applique à cette phase. Les pré-soutenances de participants distincts peuvent avoir lieu simultanément, indépendamment du nombre de salles. La liste des salles reste présente dans les données et ne sert qu’aux finales.

Tous les étudiants doivent passer exactement une pré-soutenance. Seuls les admissibles doivent passer exactement une finale. Le binôme président/examinateur est choisi par votre méthode, puis reste identique entre les deux phases. L'encadrant n'est pas imposé comme participant à la pré-soutenance. À la finale, les trois enseignants sont distincts. Seul l'examinateur a une obligation de correspondance avec le domaine. Le président doit être habilité à ce rôle, sans obligation de correspondance de domaine.

Chaque séance occupe exactement un seul créneau, quelle que soit sa phase. Une séance au créneau `slot` occupe l'intervalle `[slot, slot+1)`. Deux séances successives aux créneaux 0 et 1 ne se chevauchent pas. Le dernier créneau d'un jour est une position de début valide.

Les deux périodes sont communes à tous les étudiants. Les tableaux `predefence_days` et `final_defence_days` sont non vides, contiennent des indices de jour valides et sans doublon, sont disjoints et respectent `max(predefence_days) < min(final_defence_days)`. Une pré-soutenance est obligatoirement placée dans le premier tableau, une finale dans le second. Il n'y a pas de délai individuel entre les phases : la séparation temporelle est déterminée par les périodes communes. Les tableaux peuvent être non triés et non contigus ; un jour entre deux indices présents mais absent du tableau est interdit. Les jours de l'horizon hors de ces périodes ne peuvent accueillir aucune séance.

Le créneau occupé doit être disponible pour chaque participant. Une salle doit être disponible seulement pour une finale. Les enseignants et les étudiants restent soumis à l’absence de chevauchement, y compris en ligne. Les pauses et périodes indisponibles situées entre la première et la dernière intervention d'un enseignant comptent comme temps creux dans le critère retenu. Pour un enseignant et un jour : `dernier_créneau − premier_créneau + 1 − nombre_de_séances`.


## Regroupement par encadrant

Pour les pré-soutenances en ligne, prendre les créneaux DISTINCTS des étudiants de chaque encadrant pour chaque jour. Un groupe est une suite maximale de créneaux consécutifs. Deux pré-soutenances simultanées d’étudiants d’un même encadrant occupent un seul créneau pour ce calcul, même si leurs jurys sont différents. Il n’y a aucune salle en ligne fictive ni ordre artificiel entre passages simultanés. Les séances d’un autre encadrant n’interrompent pas une suite.

Pour les finales, un groupe est une suite de séances immédiatement adjacentes du même encadrant, dans la même salle et le même jour. Pour chaque encadrant et chaque phase, sommer ses groupes sur les jours (et les salles pour les finales), puis contribuer `max(0, nombre_de_groupes − 1)`. Le critère est la somme de ces contributions.

## Vérification et sortie

Depuis le dossier du projet :

```sh
python validator.py --instance-only data/small_01.json
python validator.py examples/demo_instance.json examples/demo_solution.json
python validator.py data/small_01.json submission.json
python -m unittest discover -s tests -v
```

Python 3.10 ou ultérieur ; aucune installation externe nécessaire. Le contrôle `--instance-only` vérifie la structure et les références, pas l'existence d'une solution. Le programme rend du JSON : `valid`, `errors`, `metrics`. Code de sortie 0 si valide, 1 si invalide ; une mauvaise utilisation des arguments produit le code 2 habituel d'argparse. Les métriques sont nulles pour toute solution invalide ou incomplète.

`examples/empty_solution.json` est un gabarit volontairement incomplet. Remplacer son `instance_id` et compléter `sessions`. `examples/demo_instance.json` et `demo_solution.json` forment une démonstration pédagogique de trois étudiants, hors des 30 instances à résoudre.

Les définitions détaillées des cinq critères figurent dans `../schema_contract.md`. Tous sont à minimiser ; aucune somme pondérée n'est imposée. Les JSON Schemas fournis facilitent l'édition, mais le validateur Python fait foi pour les bornes dynamiques, les références, l’appartenance et l’ordre des périodes communes, les doublons de clés JSON, la stricte distinction entre nombres entiers et décimaux, et les contraintes de planification. Il refuse les champs inconnus : ne pas ajouter des statistiques ou commentaires dans le fichier de solution.

Tous les nombres doivent être des lexèmes entiers JSON, sans point décimal ni exposant : écrire `3`, jamais `3.0` ni `3e0`. Ils sont bornés à 9007199254740991 pour être représentables exactement en Python et JavaScript ; les bornes propres à chaque champ restent applicables. Les limites pratiques du visualiseur sont distinctes de cette convention numérique.
