#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyser_resultats.py
---------------------
Script d'analyse statistique et de génération des graphiques comparatifs
pour le projet d'optimisation de planification des soutenances (IFRI / UAC).

Génère :
- Tableaux statistiques consolidés (taux de faisabilité, médianes, étendues, gains relatifs)
- Export des tableaux au format Markdown et LaTeX
- Graphiques haute définition (PNG 300 DPI et PDF vectoriels)
"""

import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Configuration esthétique des graphiques
plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['figure.autolayout'] = True
sns.set_theme(style="whitegrid", palette="deep")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTATS_DIR = os.path.join(BASE_DIR, "resultats")
RAPPORT_DIR = os.path.join(BASE_DIR, "rapport")
FIG_DIR = os.path.join(RAPPORT_DIR, "figures")
TAB_DIR = os.path.join(RAPPORT_DIR, "tableaux")

os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(TAB_DIR, exist_ok=True)


def charger_donnees():
    """Charge et fusionne les données de résultats et de manifest."""
    csv_path = os.path.join(RESULTATS_DIR, "resultats_globaux.csv")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Le fichier {csv_path} est introuvable. Lancez la consolidation.")
    
    df = pd.read_csv(csv_path)
    
    # Ordonnancement logique des tailles
    size_cat = pd.CategoricalDtype(categories=['small', 'medium', 'large'], ordered=True)
    df['size'] = df['size'].astype(size_cat)
    
    return df


def analyser_faisabilite(df):
    """Calcule les taux de faisabilité et synthétise les statuts par méthode et par taille."""
    rows = []
    for (size, method), grp in df.groupby(['size', 'method'], observed=True):
        total_runs = len(grp)
        valid_runs = (grp['valid'] == True).sum()
        feas_rate = (valid_runs / total_runs) * 100.0
        nb_instances = grp['instance_id'].nunique()
        inst_with_valid = grp[grp['valid'] == True]['instance_id'].nunique()
        
        status_counts = grp['stop_status'].value_counts().to_dict()
        complete_cnt = status_counts.get('COMPLETE', 0)
        over_budget_cnt = status_counts.get('COMPLETE_OVER_BUDGET', 0)
        
        rows.append({
            'Taille': size.capitalize(),
            'Méthode': 'Baseline' if 'baseline' in method else 'CP-SAT',
            'Instances': nb_instances,
            'Inst. Valides': inst_with_valid,
            'Nb Runs': total_runs,
            'Runs Valides': valid_runs,
            'Taux Faisabilité (%)': f"{feas_rate:.1f}%",
            'Statut COMPLETE': complete_cnt,
            'Statut OVER_BUDGET': over_budget_cnt
        })
        
    df_faisabilite = pd.DataFrame(rows)
    return df_faisabilite


def calculer_statistiques_agregées(df):
    """
    Calcule pour chaque méthode et chaque taille la médiane et l'étendue (min, max),
    ainsi que la moyenne et l'écart-type pour f1..f5 et pour le temps total.
    """
    criteres = {
        'teacher_presence_days': 'f1_Presence',
        'teacher_idle_slots': 'f2_Attente',
        'teacher_load_range': 'f3_EquilibreCharge',
        'supervisor_group_breaks': 'f4_RupturesEncadrant',
        'distinct_jury_pairs': 'f5_PairesJurys',
        'total_seconds': 'Temps_Total_s'
    }
    
    records = []
    
    for size in ['small', 'medium', 'large']:
        sub = df[df['size'] == size]
        base_sub = sub[sub['method'].str.contains('baseline')]
        cpsat_sub = sub[sub['method'].str.contains('cpsat')]
        
        for col, label in criteres.items():
            # Baseline (1 run par instance)
            b_vals = base_sub[col].dropna()
            b_med = b_vals.median()
            b_min = b_vals.min()
            b_max = b_vals.max()
            b_mean = b_vals.mean()
            
            # CP-SAT (agrégation par médiane d'instance d'abord sur les 5 graines)
            c_inst_meds = cpsat_sub.groupby('instance_id')[col].median()
            c_med = c_inst_meds.median()
            c_min = cpsat_sub[col].min()
            c_max = cpsat_sub[col].max()
            c_mean = cpsat_sub[col].mean()
            
            # Gain relatif (%) = (Baseline - CP-SAT) / Baseline * 100
            # Positif = amélioration (car on minimise)
            if col != 'total_seconds':
                gain_rel = ((b_med - c_med) / b_med * 100.0) if b_med > 0 else 0.0
                gain_str = f"{gain_rel:+.1f}%"
            else:
                gain_str = "N/A (Budget 60s)"
                
            records.append({
                'Taille': size.capitalize(),
                'Critère': label,
                'Base Médiane': b_med,
                'Base Étendue': f"[{b_min:.1f} - {b_max:.1f}]" if isinstance(b_min, float) else f"[{b_min} - {b_max}]",
                'Base Moyenne': f"{b_mean:.2f}",
                'CP-SAT Médiane': c_med,
                'CP-SAT Étendue': f"[{c_min:.1f} - {c_max:.1f}]" if isinstance(c_min, float) else f"[{c_min} - {c_max}]",
                'CP-SAT Moyenne': f"{c_mean:.2f}",
                'Amélioration Médiane (%)': gain_str
            })
            
    return pd.DataFrame(records)


def calculer_recapitulatif_instances(df):
    """Calcule le tableau instance par instance : comparaison Baseline vs CP-SAT (médiane & étendue)."""
    instances = df['instance_id'].unique()
    rows = []
    
    for inst in sorted(instances):
        sub = df[df['instance_id'] == inst]
        base_row = sub[sub['method'].str.contains('baseline')].iloc[0]
        cpsat_rows = sub[sub['method'].str.contains('cpsat')]
        
        row = {
            'instance_id': inst,
            'size': base_row['size'],
            'students': base_row['students'],
            # f1
            'f1_base': base_row['teacher_presence_days'],
            'f1_cpsat_med': cpsat_rows['teacher_presence_days'].median(),
            'f1_cpsat_etendue': f"[{cpsat_rows['teacher_presence_days'].min()}-{cpsat_rows['teacher_presence_days'].max()}]",
            # f2
            'f2_base': base_row['teacher_idle_slots'],
            'f2_cpsat_med': cpsat_rows['teacher_idle_slots'].median(),
            'f2_cpsat_etendue': f"[{cpsat_rows['teacher_idle_slots'].min()}-{cpsat_rows['teacher_idle_slots'].max()}]",
            # f3
            'f3_base': base_row['teacher_load_range'],
            'f3_cpsat_med': cpsat_rows['teacher_load_range'].median(),
            'f3_cpsat_etendue': f"[{cpsat_rows['teacher_load_range'].min()}-{cpsat_rows['teacher_load_range'].max()}]",
            # f4
            'f4_base': base_row['supervisor_group_breaks'],
            'f4_cpsat_med': cpsat_rows['supervisor_group_breaks'].median(),
            'f4_cpsat_etendue': f"[{cpsat_rows['supervisor_group_breaks'].min()}-{cpsat_rows['supervisor_group_breaks'].max()}]",
            # f5
            'f5_base': base_row['distinct_jury_pairs'],
            'f5_cpsat_med': cpsat_rows['distinct_jury_pairs'].median(),
            'f5_cpsat_etendue': f"[{cpsat_rows['distinct_jury_pairs'].min()}-{cpsat_rows['distinct_jury_pairs'].max()}]",
            # Temps
            't_base': f"{base_row['total_seconds']:.3f}",
            't_cpsat_first_med': f"{cpsat_rows['first_feasible_seconds'].median():.2f}",
            't_cpsat_tot_med': f"{cpsat_rows['total_seconds'].median():.2f}"
        }
        rows.append(row)
        
    return pd.DataFrame(rows)


def exporter_tableaux(df_faisabilite, df_stats, df_inst):
    """Exporte les tableaux en formats Markdown et LaTeX pour le rapport."""
    # 1. Faisabilité
    md_fais = df_faisabilite.to_markdown(index=False)
    with open(os.path.join(TAB_DIR, "tableau_faisabilite.md"), "w", encoding="utf-8") as f:
        f.write(md_fais)
    with open(os.path.join(TAB_DIR, "tableau_faisabilite.tex"), "w", encoding="utf-8") as f:
        f.write(df_faisabilite.to_latex(index=False))
        
    # 2. Statistiques agrégées
    md_stats = df_stats.to_markdown(index=False)
    with open(os.path.join(TAB_DIR, "tableau_comparatif_synthese.md"), "w", encoding="utf-8") as f:
        f.write(md_stats)
    with open(os.path.join(TAB_DIR, "tableau_comparatif_synthese.tex"), "w", encoding="utf-8") as f:
        f.write(df_stats.to_latex(index=False))
        
    # 3. Détail instances
    md_inst = df_inst.to_markdown(index=False)
    with open(os.path.join(TAB_DIR, "tableau_detail_instances.md"), "w", encoding="utf-8") as f:
        f.write(md_inst)
    with open(os.path.join(TAB_DIR, "tableau_detail_instances.tex"), "w", encoding="utf-8") as f:
        f.write(df_inst.to_latex(index=False))
        
    print(f"Tableaux exportés avec succès dans {TAB_DIR}")


def generer_graphiques(df):
    """Génère tous les graphiques haute définition pour le rapport."""
    print("Génération des figures...")
    
    # -------------------------------------------------------------------------
    # FIGURE 1 : Temps de calcul selon le nombre d'étudiants
    # -------------------------------------------------------------------------
    plt.figure(figsize=(10, 5.5), dpi=300)
    
    cpsat_df = df[df['method'].str.contains('cpsat')].copy()
    base_df = df[df['method'].str.contains('baseline')].copy()
    
    # Agréger par instance pour CP-SAT
    cpsat_agg = cpsat_df.groupby(['instance_id', 'students', 'size']).agg({
        'total_seconds': ['median', 'min', 'max'],
        'first_feasible_seconds': ['median', 'min', 'max']
    }).reset_index()
    cpsat_agg.columns = ['instance_id', 'students', 'size', 'tot_med', 'tot_min', 'tot_max', 'first_med', 'first_min', 'first_max']
    cpsat_agg = cpsat_agg.sort_values(by='students')
    
    base_sorted = base_df.sort_values(by='students')
    
    plt.plot(cpsat_agg['students'], cpsat_agg['tot_med'], 'o-', color='#d95f02', linewidth=2.2, label="CP-SAT : Temps total d'optimisation (médiane)")
    plt.fill_between(cpsat_agg['students'], cpsat_agg['tot_min'], cpsat_agg['tot_max'], color='#d95f02', alpha=0.15, label="CP-SAT : Étendue totale [min, max]")
    
    plt.plot(cpsat_agg['students'], cpsat_agg['first_med'], 's--', color='#7570b3', linewidth=2.0, label="CP-SAT : Temps jusqu'au 1er faisable (médiane)")
    plt.plot(base_sorted['students'], base_sorted['total_seconds'], '^:', color='#1b9e77', linewidth=2.0, label="Baseline : Construction gloutonne")
    
    plt.axhline(60.0, color='red', linestyle='--', linewidth=1.5, alpha=0.8, label="Budget officiel strict (60 s)")
    
    plt.title("Évolution des temps de résolution en fonction de la taille d'instance (12 à 136 étudiants)", fontsize=13, fontweight='bold', pad=12)
    plt.xlabel("Nombre d'étudiants à planifier ($N$)", fontsize=11)
    plt.ylabel("Temps de calcul en secondes (échelle log)", fontsize=11)
    plt.yscale('log')
    plt.grid(True, which="both", ls="--", alpha=0.5)
    plt.legend(frameon=True, facecolor='white', framealpha=0.9, fontsize=9.5, loc='center right')
    
    fig1_path_png = os.path.join(FIG_DIR, "fig1_temps_resolution.png")
    fig1_path_pdf = os.path.join(FIG_DIR, "fig1_temps_resolution.pdf")
    plt.savefig(fig1_path_png, bbox_inches='tight')
    plt.savefig(fig1_path_pdf, bbox_inches='tight')
    plt.close()
    
    # -------------------------------------------------------------------------
    # FIGURE 2 : Boxplots comparatifs de f1 (Présence) et f2 (Attente)
    # -------------------------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), dpi=300)
    
    # Préparer les données pour Seaborn
    df_plot = df.copy()
    df_plot['Méthode'] = df_plot['method'].apply(lambda x: 'Baseline' if 'baseline' in x else 'CP-SAT')
    df_plot['Classe'] = df_plot['size'].map({'small': 'Petite (12-20)', 'medium': 'Moyenne (40-58)', 'large': 'Grande (100-136)'})
    palette = {'Baseline': '#1b9e77', 'CP-SAT': '#d95f02'}
    
    # Subplot 1 : f1
    sns.boxplot(ax=axes[0], data=df_plot, x='Classe', y='teacher_presence_days', hue='Méthode', palette=palette, width=0.55)
    axes[0].set_title("(A) $f_1$ : Jours de mobilisation des enseignants (à minimiser)", fontsize=12, fontweight='bold')
    axes[0].set_xlabel("Taille d'instance", fontsize=11)
    axes[0].set_ylabel("Total jours de présence", fontsize=11)
    axes[0].legend(title="Méthode", frameon=True)
    
    # Subplot 2 : f2
    sns.boxplot(ax=axes[1], data=df_plot, x='Classe', y='teacher_idle_slots', hue='Méthode', palette=palette, width=0.55)
    axes[1].set_title("(B) $f_2$ : Créneaux d'attente des enseignants (à minimiser)", fontsize=12, fontweight='bold')
    axes[1].set_xlabel("Taille d'instance", fontsize=11)
    axes[1].set_ylabel("Total créneaux d'attente (trous)", fontsize=11)
    axes[1].legend(title="Méthode", frameon=True)
    
    plt.suptitle("Comparaison Baseline vs CP-SAT : Mobilisation ($f_1$) et Attente ($f_2$)", fontsize=14, fontweight='bold', y=1.02)
    fig2_path_png = os.path.join(FIG_DIR, "fig2_presence_attente.png")
    fig2_path_pdf = os.path.join(FIG_DIR, "fig2_presence_attente.pdf")
    plt.savefig(fig2_path_png, bbox_inches='tight')
    plt.savefig(fig2_path_pdf, bbox_inches='tight')
    plt.close()

    # -------------------------------------------------------------------------
    # FIGURE 3 : Boxplots comparatifs de f3 (Écart de charge) et f5 (Paires jurys)
    # -------------------------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), dpi=300)
    
    # Subplot 1 : f3
    sns.boxplot(ax=axes[0], data=df_plot, x='Classe', y='teacher_load_range', hue='Méthode', palette=palette, width=0.55)
    axes[0].set_title("(A) $f_3$ : Écart de charge entre enseignants (à minimiser)", fontsize=12, fontweight='bold')
    axes[0].set_xlabel("Taille d'instance", fontsize=11)
    axes[0].set_ylabel("Écart max - min de charge", fontsize=11)
    axes[0].legend(title="Méthode", frameon=True)
    
    # Subplot 2 : f5
    sns.boxplot(ax=axes[1], data=df_plot, x='Classe', y='distinct_jury_pairs', hue='Méthode', palette=palette, width=0.55)
    axes[1].set_title("(B) $f_5$ : Paires distinctes de jurys (à minimiser)", fontsize=12, fontweight='bold')
    axes[1].set_xlabel("Taille d'instance", fontsize=11)
    axes[1].set_ylabel("Nombre de couples (P, E) distincts", fontsize=11)
    axes[1].legend(title="Méthode", frameon=True)
    
    plt.suptitle("Comparaison Baseline vs CP-SAT : Équilibre ($f_3$) et Réutilisation des Jurys ($f_5$)", fontsize=14, fontweight='bold', y=1.02)
    fig3_path_png = os.path.join(FIG_DIR, "fig3_equilibre_paires.png")
    fig3_path_pdf = os.path.join(FIG_DIR, "fig3_equilibre_paires.pdf")
    plt.savefig(fig3_path_png, bbox_inches='tight')
    plt.savefig(fig3_path_pdf, bbox_inches='tight')
    plt.close()

    # -------------------------------------------------------------------------
    # FIGURE 4 : Dispersion des étudiants par encadrant (f4)
    # -------------------------------------------------------------------------
    plt.figure(figsize=(8, 5.5), dpi=300)
    sns.boxplot(data=df_plot, x='Classe', y='supervisor_group_breaks', hue='Méthode', palette=palette, width=0.5)
    plt.title("Comparaison de $f_4$ : Ruptures de séries des encadrants (à minimiser)", fontsize=13, fontweight='bold', pad=12)
    plt.xlabel("Taille d'instance", fontsize=11)
    plt.ylabel("Nombre total de ruptures de séries", fontsize=11)
    plt.legend(title="Méthode", frameon=True)
    
    fig4_path_png = os.path.join(FIG_DIR, "fig4_dispersion_encadrant.png")
    fig4_path_pdf = os.path.join(FIG_DIR, "fig4_dispersion_encadrant.pdf")
    plt.savefig(fig4_path_png, bbox_inches='tight')
    plt.savefig(fig4_path_pdf, bbox_inches='tight')
    plt.close()

    # -------------------------------------------------------------------------
    # FIGURE 5 : Analyse du compromis bi-critère (f1 Présence vs f2 Attente)
    # -------------------------------------------------------------------------
    plt.figure(figsize=(9, 6), dpi=300)
    
    # Pour chaque instance, prendre la médiane CP-SAT et la valeur Baseline
    agg_scatter = df.groupby(['instance_id', 'method', 'size', 'students'], observed=True).agg({
        'teacher_presence_days': 'median',
        'teacher_idle_slots': 'median'
    }).reset_index()
    agg_scatter['Méthode'] = agg_scatter['method'].apply(lambda x: 'Baseline' if 'baseline' in x else 'CP-SAT')
    
    # Tracer des flèches allant de Baseline vers CP-SAT pour chaque instance
    base_pts = agg_scatter[agg_scatter['Méthode'] == 'Baseline'].set_index('instance_id')
    cpsat_pts = agg_scatter[agg_scatter['Méthode'] == 'CP-SAT'].set_index('instance_id')
    
    for inst in base_pts.index:
        x0 = base_pts.loc[inst, 'teacher_presence_days']
        y0 = base_pts.loc[inst, 'teacher_idle_slots']
        x1 = cpsat_pts.loc[inst, 'teacher_presence_days']
        y1 = cpsat_pts.loc[inst, 'teacher_idle_slots']
        plt.annotate('', xy=(x1, y1), xytext=(x0, y0),
                     arrowprops=dict(arrowstyle="->", color="gray", lw=0.9, alpha=0.5, shrinkA=3, shrinkB=3))
        
    sns.scatterplot(data=agg_scatter, x='teacher_presence_days', y='teacher_idle_slots', 
                    hue='Méthode', style='size', palette=palette, s=90, alpha=0.9)
                    
    plt.title("Compromis bi-critère : Mobilisation ($f_1$) vs Attente ($f_2$)\n(Les flèches indiquent la transition Baseline $\\to$ CP-SAT)", 
              fontsize=12, fontweight='bold', pad=12)
    plt.xlabel("Jours de présence des enseignants ($f_1$)", fontsize=11)
    plt.ylabel("Créneaux d'attente ($f_2$)", fontsize=11)
    plt.legend(frameon=True, bbox_to_anchor=(1.02, 1), loc='upper left')
    
    fig5_path_png = os.path.join(FIG_DIR, "fig5_compromis_f1_f2.png")
    fig5_path_pdf = os.path.join(FIG_DIR, "fig5_compromis_f1_f2.pdf")
    plt.savefig(fig5_path_png, bbox_inches='tight')
    plt.savefig(fig5_path_pdf, bbox_inches='tight')
    plt.close()
    
    print(f"Graphiques générés avec succès dans {FIG_DIR}")


def main():
    print("=" * 70)
    print("ANALYSE DES RÉSULTATS DU PROJET DE PLANIFICATION DES SOUTENANCES")
    print("=" * 70)
    
    df = charger_donnees()
    print(f"Données chargées : {len(df)} exécutions sur {df['instance_id'].nunique()} instances.")
    
    df_fais = analyser_faisabilite(df)
    print("\n--- SYNTHÈSE DE FAISABILITÉ ---")
    print(df_fais.to_string(index=False))
    
    df_stats = calculer_statistiques_agregées(df)
    print("\n--- STATISTIQUES COMPARATIVES AGRÉGÉES ---")
    print(df_stats.to_string(index=False))
    
    df_inst = calculer_recapitulatif_instances(df)
    
    exporter_tableaux(df_fais, df_stats, df_inst)
    generer_graphiques(df)
    
    print("\nAnalyse terminée avec succès.")


if __name__ == '__main__':
    main()
