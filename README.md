# Outils de résolution de problèmes d’optimisation

Année académique 2026 - 2027  
Université : Université d’Abomey-Calavi  
Établissement : Institut de Formation et de Recherche en Informatique (IFRI)  
Grade : Licence 3 en Intelligence Artificielle  
Chargé du cours : Dr Ing. (MC) Houndji Vinasetan Ratheil, https://ratheil.info

## Projet 2026-2027 / Planification automatique de soutenances

Version 4.0


## Commencer
1. Lire Sujet_etudiant_jurys_et_soutenances.pdf (le Word contient le même sujet).
2. Lire data/README.md : sens des champs et conventions.
3. Examiner examples/demo_instance.json et examples/demo_solution.json, petit exemple indépendant des 30 instances.
4. Exécuter : python validator.py examples/demo_instance.json examples/demo_solution.json
5. Ouvrir visualiseur.html dans un navigateur récent, puis cliquer « Mini-démo » ou importer une instance et une solution.

Python 3.10 ou ultérieur suffit pour le validateur. Aucune bibliothèque supplémentaire n’est nécessaire. Le visualiseur ne nécessite ni serveur, ni connexion Internet, ni installation. Les fichiers sont lus localement, sans envoi de données.

## Contenu
- Sujet étudiant : objectifs, contraintes, critères, expérimentation, livrables, barème.
- data/ : 30 instances JSON, manifeste JSON/CSV et dictionnaire français.
- instance.schema.json et solution.schema.json : formats machine ; validator.py complète les règles structurelles avec les contraintes métier.
- schema_contract.md : contrat technique détaillé en anglais, équivalent des règles françaises.
- examples/ : petite démonstration et gabarit de solution vide à compléter.
- templates/resultats.csv : en-tête pour consigner chaque exécution.
- tests/ : tests du validateur ; lancer python -m unittest discover -s tests -v.
- visualiseur.html : vues par salle, enseignant ou étudiant, filtres, frise, tableau, diagnostics et cinq indicateurs.

## Produire et vérifier une solution
Depuis le dossier extrait :
python validator.py data/small_01.json mon_planning.json

Le fichier mon_planning.json doit suivre solution.schema.json. Il porte l’identifiant exact de l’instance. Aucun champ de commentaire ou de résultat expérimental ne doit être ajouté à ce JSON ; conserver ces informations dans le CSV de résultats.
Le gabarit vide n’est pas une solution valide. Un planning invalide n’a pas de métriques comparables.

Les jours et créneaux sont des indices entiers à partir de zéro, sans correspondance imposée avec une date réelle ou une heure. Chaque séance dure exactement un créneau, pour les deux phases. Les jours communs de pré-soutenance sont donnés par predefence_days ; ceux des soutenances finales par final_defence_days. Ces deux périodes sont non vides, disjointes et ordonnées : tous les jours de pré-soutenance précèdent les jours de soutenance finale. Il n’y a ni durée à renseigner ni délai individuel à choisir. L’admissibilité finale est une donnée fournie ; elle n’est pas une décision de l’algorithme.

Les 30 données sont synthétiques et réalisables. Aucune solution de ces 30 cas ni aucun solveur n’est fourni. La mini-démo de trois étudiants sert uniquement à comprendre les formats et l’outil.

## Utiliser le visualiseur
Après extraction du ZIP, ouvrir visualiseur.html dans un navigateur sur ordinateur. Charger d’abord une instance JSON, puis le planning JSON correspondant. Changer les filtres et vues pour examiner les affectations et cliquer sur une séance pour ses détails. Le bouton d’effacement retire les fichiers de la session. Les indicateurs portent sur le planning complet, même lorsqu’une vue est filtrée.
Les diagnostics JavaScript facilitent l’exploration ; le validateur Python constitue le contrôle de référence.

## Pré-soutenances en ligne
Les pré-soutenances ne mobilisent aucune salle : room_id vaut null. Les disponibilités, occupations et plafonds des salles concernent seulement les soutenances finales. Les enseignants et étudiants doivent rester disponibles et ne peuvent participer à deux séances simultanées. Des jurys distincts peuvent tenir plusieurs pré-soutenances en parallèle.

Tous les champs numériques sont écrits comme des entiers JSON, sans point décimal ni notation exponentielle. Ne pas mélanger les versions 3 et 4 des instances, solutions et outils.

La capacité des salles ne constitue pas une donnée ni une contrainte du projet.
