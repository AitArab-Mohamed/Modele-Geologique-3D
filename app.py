import os
import pandas as pd
import numpy as np
import pyvista as pv
from trame.app import get_server
from trame.ui.vuetify import SinglePageLayout
from trame.widgets import pyvista as pv_widgets

# =====================================================================
# 1 & 2. EXTRACTION DES DONNÉES DEPUIS LES CSV
# =====================================================================
print("Extraction des données CSV en cours...")
df_collar = pd.read_csv('collar.csv')
df_survey = pd.read_csv('survey.csv')
df_litho = pd.read_csv('litho.csv')
df_assay = pd.read_csv('assay.csv')

# Nettoyage global
colonne_soc = 'SOCIETY' 
df_collar = df_collar.dropna(subset=['XCOLLAR', 'YCOLLAR', 'ZCOLLAR'])
df_collar['TYPE'] = df_collar['TYPE'].astype(str).str.strip().str.upper()
df_collar = df_collar[df_collar['TYPE'].isin(['DD', 'RC', 'ROC'])]
df_collar[colonne_soc] = df_collar[colonne_soc].astype(str).str.strip().str.upper()

types_uniques = df_collar['TYPE'].dropna().unique().tolist()
soc_uniques = df_collar[colonne_soc].dropna().unique().tolist()

# =====================================================================
# 3. INITIALISATION DE LA SCÈNE ET DES COLLETS
# =====================================================================
plotter = pv.Plotter()
plotter.set_background('white')
plotter.add_axes() 

points = df_collar[['XCOLLAR', 'YCOLLAR', 'ZCOLLAR']].values
cloud = pv.PolyData(points)
plotter.add_mesh(cloud, color='red', point_size=5, render_points_as_spheres=True)

# =====================================================================
# 4. FONCTION DE CALCUL DES TRAJECTOIRES 3D (DESURVEYING)
# =====================================================================
df_survey = df_survey.sort_values(by=['BHID', 'AT'])

def calculer_xyz_a_profondeur(profondeur_cible, df_surveys_trou, cx, cy, cz):
    if profondeur_cible <= 0:
        return cx, cy, cz
        
    current_x, current_y, current_z = cx, cy, cz
    last_at = 0.0
    
    for _, s_row in df_surveys_trou.iterrows():
        at = s_row['AT']
        brg = s_row['BRG']
        dip = abs(s_row['DIP'])
        
        if profondeur_cible <= at:
            delta = profondeur_cible - last_at
            current_x += delta * np.cos(np.radians(dip)) * np.sin(np.radians(brg))
            current_y += delta * np.cos(np.radians(dip)) * np.cos(np.radians(brg))
            current_z -= delta * np.sin(np.radians(dip))
            return current_x, current_y, current_z
            
        delta = at - last_at
        if delta > 0:
            current_x += delta * np.cos(np.radians(dip)) * np.sin(np.radians(brg))
            current_y += delta * np.cos(np.radians(dip)) * np.cos(np.radians(brg))
            current_z -= delta * np.sin(np.radians(dip))
        last_at = at
        
    if profondeur_cible > last_at:
        delta = profondeur_cible - last_at
        dernier_survey = df_surveys_trou.iloc[-1]
        brg_final = dernier_survey['BRG']
        dip_final = abs(dernier_survey['DIP'])
        current_x += delta * np.cos(np.radians(dip_final)) * np.sin(np.radians(brg_final))
        current_y += delta * np.cos(np.radians(dip_final)) * np.cos(np.radians(brg_final))
        current_z -= delta * np.sin(np.radians(dip_final))
        
    return current_x, current_y, current_z

intervalles_donnees = []

# =====================================================================
# 5. MODÉLISATION DE LA LITHOLOGIE
# =====================================================================
couleurs_litho = {
    'GRE': 'orange', 'PEL': 'brown', 'ST': 'gray', 
    'RC': 'yellow', 'PG': 'purple', 'RAS': 'white'
}

cylindres_litho_groupes = {} 

for index, row in df_collar.iterrows():
    bhid = row['BHID']
    bh_type = row.get('TYPE', 'Inconnu')
    bh_soc = row.get(colonne_soc, 'Inconnu')
    cx, cy, cz = row['XCOLLAR'], row['YCOLLAR'], row['ZCOLLAR']
    
    surveys_trou = df_survey[df_survey['BHID'] == bhid]
    lithos_trou = df_litho[df_litho['BHID'] == bhid]
    
    if surveys_trou.empty or lithos_trou.empty:
        continue
        
    for _, l_row in lithos_trou.iterrows():
        prof_from, prof_to, code = l_row['FROM'], l_row['TO'], l_row['CODE']
        
        if pd.isna(prof_from) or pd.isna(prof_to) or prof_from >= prof_to:
            continue
            
        x_from, y_from, z_from = calculer_xyz_a_profondeur(prof_from, surveys_trou, cx, cy, cz)
        x_to, y_to, z_to = calculer_xyz_a_profondeur(prof_to, surveys_trou, cx, cy, cz)
        
        ligne_intervalle = pv.Line((x_from, y_from, z_from), (x_to, y_to, z_to))
        cylindre = ligne_intervalle.tube(radius=2.0)
        
        cx_mid = (x_from + x_to) / 2
        cy_mid = (y_from + y_to) / 2
        cz_mid = (z_from + z_to) / 2
        intervalles_donnees.append((cx_mid, cy_mid, cz_mid, f"Sondage: {bhid}\nMetrage: {prof_from}m a {prof_to}m\nLitho: {code}"))
        
        cle = (bh_type, bh_soc, code)
        if cle not in cylindres_litho_groupes:
            cylindres_litho_groupes[cle] = []
        cylindres_litho_groupes[cle].append(cylindre)

acteurs_litho_dict = {} 

for (bh_type, bh_soc, code), liste_cylindres in cylindres_litho_groupes.items():
    if len(liste_cylindres) > 0:
        bloc_fusionne = pv.MultiBlock(liste_cylindres).combine()
        couleur = couleurs_litho.get(code, 'lightgray')
        act = plotter.add_mesh(bloc_fusionne, color=couleur)
        act.SetVisibility(False) 
        
        cle_groupe = (bh_type, bh_soc)
        if cle_groupe not in acteurs_litho_dict:
            acteurs_litho_dict[cle_groupe] = []
        acteurs_litho_dict[cle_groupe].append(act)

# =====================================================================
# 6. MODÉLISATION DES TENEURS ET FILTRES DYNAMIQUES
# =====================================================================
cylindres_par_groupe = {}

for index, row in df_collar.iterrows():
    bhid = row['BHID']
    bh_type = row.get('TYPE', 'Inconnu')
    bh_soc = row.get(colonne_soc, 'Inconnu')
    cle = (bh_type, bh_soc)
    
    if cle not in cylindres_par_groupe:
        cylindres_par_groupe[cle] = []
        
    cx, cy, cz = row['XCOLLAR'], row['YCOLLAR'], row['ZCOLLAR']
    
    surveys_trou = df_survey[df_survey['BHID'] == bhid]
    assays_trou = df_assay[df_assay['BHID'] == bhid]
    
    if surveys_trou.empty or assays_trou.empty:
        continue
        
    for _, a_row in assays_trou.iterrows():
        prof_from, prof_to, teneur = a_row['FROM'], a_row['TO'], a_row['Cu']
        if pd.isna(prof_from) or pd.isna(prof_to) or pd.isna(teneur):
            continue
            
        x_from, y_from, z_from = calculer_xyz_a_profondeur(prof_from, surveys_trou, cx, cy, cz)
        x_to, y_to, z_to = calculer_xyz_a_profondeur(prof_to, surveys_trou, cx, cy, cz)
        
        ligne_intervalle = pv.Line((x_from, y_from, z_from), (x_to, y_to, z_to))
        cylindre = ligne_intervalle.tube(radius=2.0) 
        cylindre.cell_data['Teneur'] = [teneur] * cylindre.n_cells
        cylindres_par_groupe[cle].append(cylindre)
        
        cx_mid = (x_from + x_to) / 2
        cy_mid = (y_from + y_to) / 2
        cz_mid = (z_from + z_to) / 2
        intervalles_donnees.append((cx_mid, cy_mid, cz_mid, f"Sondage: {bhid}\nMetrage: {prof_from}m a {prof_to}m\nCuivre: {teneur}%"))

meshes_originaux = {}
acteurs_gisement = {}

for cle, liste_cylindres in cylindres_par_groupe.items():
    if liste_cylindres:
        mesh = pv.MultiBlock(liste_cylindres).combine()
        meshes_originaux[cle] = mesh
        acteurs_gisement[cle] = plotter.add_mesh(mesh.copy(), scalars='Teneur', cmap='jet')

# --- PARAMETRES DE FILTRES ---
etat_filtres = {
    'types': {t: True for t in types_uniques},
    'societes': {s: True for s in soc_uniques},
    'mode_litho': False,
    'teneur_inf': True,
    'teneur_sup': True
}

def appliquer_tous_les_filtres(*args):
    for cle, mesh_orig in meshes_originaux.items():
        t_val, s_val = cle
        actor = acteurs_gisement[cle]
        
        if etat_filtres['mode_litho']:
            actor.SetVisibility(False)
            continue
            
        if not etat_filtres['types'][t_val] or not etat_filtres['societes'][s_val]:
            actor.SetVisibility(False)
            continue
            
        inf_coche = etat_filtres['teneur_inf']
        sup_coche = etat_filtres['teneur_sup']
        
        if inf_coche and sup_coche:
            actor.mapper.dataset = mesh_orig
            actor.SetVisibility(True)
        elif sup_coche:
            try:
                mesh_filtre = mesh_orig.threshold(0.3, scalars='Teneur')
                if mesh_filtre.n_points > 0:
                    actor.mapper.dataset = mesh_filtre
                    actor.SetVisibility(True)
                else:
                    actor.SetVisibility(False)
            except Exception:
                actor.SetVisibility(False)
        elif inf_coche:
            try:
                mesh_filtre = mesh_orig.threshold([-100.0, 0.2999], scalars='Teneur')
                if mesh_filtre.n_points > 0:
                    actor.mapper.dataset = mesh_filtre
                    actor.SetVisibility(True)
                else:
                    actor.SetVisibility(False)
            except Exception:
                actor.SetVisibility(False)
        else:
            actor.SetVisibility(False)
            
    for cle, liste_acteurs in acteurs_litho_dict.items():
        t_val, s_val = cle
        est_visible = etat_filtres['mode_litho'] and etat_filtres['types'][t_val] and etat_filtres['societes'][s_val]
        for act in liste_acteurs:
            act.SetVisibility(est_visible)

# --- DESIGN DE L'INTERFACE DES FILTRES ---
y_current = 100  

def callback_switch_vue(etat_coche):
    etat_filtres['mode_litho'] = etat_coche
    appliquer_tous_les_filtres()

plotter.add_checkbox_button_widget(callback_switch_vue, value=False, position=(20, y_current), size=20)
plotter.add_text("MODE LITHOLOGIE", position=(50, y_current+2), font_size=10, color='darkgreen')
y_current += 40 

def callback_soc(s_val):
    def cb(etat_coche):
        etat_filtres['societes'][s_val] = etat_coche
        appliquer_tous_les_filtres()
    return cb

for s_val in reversed(soc_uniques):
    plotter.add_checkbox_button_widget(callback_soc(s_val), value=True, position=(20, y_current), size=16)
    plotter.add_text(str(s_val), position=(45, y_current+1), font_size=8, color='black')
    y_current += 25 
plotter.add_text("SOCIÉTÉ :", position=(20, y_current), font_size=10, color='darkred')
y_current += 35  

def callback_type(t_val):
    def cb(etat_coche):
        etat_filtres['types'][t_val] = etat_coche
        appliquer_tous_les_filtres()
    return cb

for t_val in reversed(types_uniques):
    plotter.add_checkbox_button_widget(callback_type(t_val), value=True, position=(20, y_current), size=16)
    plotter.add_text(str(t_val), position=(45, y_current+1), font_size=8, color='black')
    y_current += 25
plotter.add_text("SONDAGE :", position=(20, y_current), font_size=10, color='darkblue')
y_current += 35

def callback_teneur_inf(etat_coche):
    etat_filtres['teneur_inf'] = etat_coche
    appliquer_tous_les_filtres()

def callback_teneur_sup(etat_coche):
    etat_filtres['teneur_sup'] = etat_coche
    appliquer_tous_les_filtres()

plotter.add_checkbox_button_widget(callback_teneur_inf, value=True, position=(20, y_current), size=16)
plotter.add_text("Cu < 0.3 %", position=(45, y_current+1), font_size=8, color='black')
y_current += 25

plotter.add_checkbox_button_widget(callback_teneur_sup, value=True, position=(20, y_current), size=16)
plotter.add_text("Cu >= 0.3 %", position=(45, y_current+1), font_size=8, color='black')
y_current += 25

plotter.add_text("TENEUR Cu :", position=(20, y_current), font_size=10, color='darkorange')
y_current += 35

# =====================================================================
# 7. SURFACES TOPOGRAPHIQUES ET TRAVAUX MINIERS (LECTURE DES .VTP)
# =====================================================================
fichiers_vtp = ["AF.vtp", "BKR.vtp", "BN.vtp", "GT.vtp"] 

for nom_fichier in fichiers_vtp:
    try:
        surface_mnt = pv.read(nom_fichier)
        plotter.add_mesh(surface_mnt, color='saddlebrown', opacity=0.7, show_edges=False, pickable=False)
    except Exception as e:
        print(f"Fichier topo ignoré: {nom_fichier} ({e})")

try:
    mesh_travaux = pv.read("Travaux_Miniers.vtp")
    acteur_travaux = plotter.add_mesh(mesh_travaux, color='dimgray', opacity=0.85, smooth_shading=True)
    
    def callback_toggle_travaux(etat_coche):
        acteur_travaux.SetVisibility(etat_coche)
        
    plotter.add_checkbox_button_widget(callback_toggle_travaux, value=True, position=(20, y_current), size=20)
    plotter.add_text("TRAVAUX MINIERS", position=(50, y_current+2), font_size=10, color='darkred')
except Exception as e:
    print(f"Fichier travaux miniers ignoré ({e})")

# =====================================================================
# 8. INTERFACE, POINTAGE ET DÉPLOIEMENT TRAME
# =====================================================================
plotter.enable_trackball_style()

b = plotter.bounds
boite_invisible = pv.Box(bounds=(b[0]-5, b[1]+5, b[2]-5, b[3]+5, b[4]-5, b[5]+5))
plotter.add_mesh(boite_invisible, opacity=0.0, pickable=False) 

plotter.show_grid(
    color='black',
    xtitle='X (Est)',
    ytitle='Y (Nord)',
    ztitle='Z (Élévation)',
    grid=True,
    location='outer',
    font_size=10
)

# Légende
legend_entries = [["LITHOLOGIE", "white"]] + [[code, color] for code, color in couleurs_litho.items()]
plotter.add_legend(
    legend_entries, 
    bcolor='white', 
    border=True, 
    face='rectangle', 
    size=(0.12, 0.28), 
    loc='upper right'
)

# Outil de pointage
matrice_centres = np.array([ [d[0], d[1], d[2]] for d in intervalles_donnees ])
textes_infos = [ d[3] for d in intervalles_donnees ]

def callback_identification(point):
    if len(matrice_centres) == 0: 
        return
    dist = np.linalg.norm(matrice_centres - point, axis=1)
    idx = np.argmin(dist)
    if dist[idx] < 200.0:
        plotter.add_text(
            textes_infos[idx], 
            name='label_pick', 
            position='center_right', 
            font_size=12, 
            color='darkblue',
            shadow=True
        )

plotter.enable_point_picking(
    callback=callback_identification,
    show_message=False, 
    color='magenta',
    point_size=8,
    use_picker=True,
    left_clicking=True
)

plotter.add_text("Cliquez sur un sondage pour l'inspecter", position='lower_right', font_size=9, color='gray')

# --- INTÉGRATION DU SERVEUR TRAME POUR LE CLOUD (RENDER.COM) ---
server = get_server("Gisement_Web")
state, ctrl = server.state, server.controller

with SinglePageLayout(server) as layout:
    layout.title.set_text("Modèle Géologique 3D Interactif - CMO")
    
    with layout.content:
        view = pv_widgets.VtkRemoteView(plotter, interactive_ratio=1)
        ctrl.on_server_ready.add(view.update)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    server.start(port=port, host="0.0.0.0")