import json
import os

nb = {
    "cells": [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "# Analyse Expérimentale et Comparaison Statistique\n",
                "## Projet d'Optimisation des Jurys et Calendriers de Soutenances (IFRI / UAC)\n",
                "\n",
                "Ce notebook consolide et analyse les résultats expérimentaux obtenus sur les 30 instances de référence, ",
                "comparant la **méthode de référence gloutonne (Baseline)** et la **méthode d'optimisation CP-SAT (Google OR-Tools)**.\n",
                "\n",
                "### Protocoles expérimentaux :\n",
                "- **Instances** : 30 instances synthétiques (10 Petites, 10 Moyennes, 10 Grandes, 12 à 136 étudiants)\n",
                "- **Budget temps** : 60 secondes maximum par instance\n",
                "- **Répétitions stochastiques** : 5 graines (0 à 4) pour CP-SAT, 1 exécution déterministe pour Baseline\n",
                "- **Total exécutions analysées** : 180 runs vérifiés par `validator.py`"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "import os\n",
                "import pandas as pd\n",
                "import numpy as np\n",
                "import matplotlib.pyplot as plt\n",
                "import seaborn as sns\n",
                "\n",
                "# Charger les données consolidées\n",
                "df = pd.read_csv('resultats/resultats_globaux.csv')\n",
                "print(f'Total exécutions chargées : {len(df)}')\n",
                "df.head()"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 1. Taux de Faisabilité et Statuts d'Arrêt\n",
                "Vérification des taux d'acceptation par le validateur officiel."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "from analyser_resultats import analyser_faisabilite\n",
                "df_fais = analyser_faisabilite(df)\n",
                "df_fais"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 2. Tableaux Comparatifs Agrégés ($f_1$ à $f_5$ et Temps)\n",
                "Calcul des médianes, étendues [min, max] et gains relatifs."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "from analyser_resultats import calculer_statistiques_agregées\n",
                "df_stats = calculer_statistiques_agregées(df)\n",
                "df_stats"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 3. Détail Instance par Instance (Médianes & Étendues)\n"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "from analyser_resultats import calculer_recapitulatif_instances\n",
                "df_inst = calculer_recapitulatif_instances(df)\n",
                "df_inst.head(10)"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 4. Visualisation Graphique des Performances"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "from IPython.display import Image, display\n",
                "figures = [\n",
                "    ('fig1_temps_resolution.png', 'Figure 1 : Évolution des temps de résolution'),\n",
                "    ('fig2_presence_attente.png', 'Figure 2 : Jours de présence (f1) et Créneaux d attente (f2)'),\n",
                "    ('fig3_equilibre_paires.png', 'Figure 3 : Écart de charge (f3) et Paires distinctes (f5)'),\n",
                "    ('fig4_dispersion_encadrant.png', 'Figure 4 : Ruptures de séries des encadrants (f4)'),\n",
                "    ('fig5_compromis_f1_f2.png', 'Figure 5 : Analyse du compromis bi-critère f1 vs f2')\n",
                "]\n",
                "for fig_name, title in figures:\n",
                "    fig_path = os.path.join('rapport', 'figures', fig_name)\n",
                "    if os.path.exists(fig_path):\n",
                "        print(f'=== {title} ===')\n",
                "        display(Image(filename=fig_path))\n"
            ]
        }
    ],
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3"
        },
        "language_info": {
            "name": "python",
            "version": "3.12"
        }
    },
    "nbformat": 4,
    "nbformat_minor": 4
}

out_path = os.path.join(os.path.dirname(__file__), "analyse_resultats.ipynb")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=2, ensure_ascii=False)

print(f"Jupyter Notebook successfully written to {out_path}")
