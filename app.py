import os
import pandas as pd
import numpy as np
import pyvista as pv
from trame.app import get_server
from trame.ui.vuetify import SinglePageLayout
from trame.widgets import vuetify
from trame.widgets import vtk as vtk_widgets

# =====================================================================
# CONFIGURATION SERVEUR & RENDER
# =====================================================================
# Indispensable pour que VTK fonctionne sur un serveur sans écran physique
pv.OFF_SCREEN = True

server = get_server()
state, ctrl = server.state, server.controller

# =====================================================================
# EXTRACTION DES DONNÉES DEPUIS LES CSV (Correction du séparateur)
# =====================================================================
print("Extraction des données CSV en cours...")
df_collar = pd.read_csv('collar.csv', sep=';')
df_survey = pd.read_csv('survey.csv', sep=';')
df_litho = pd.read_csv('litho.csv', sep=';')
df_assay = pd.read_csv('assay.csv', sep=';')

# --- Mode test optionnel : décommente pour limiter à N sondages ---
df_collar = df_collar.head(100)

# Nettoyage
colonne_soc = 'SOCIETY'
if colonne_soc not in df_collar.columns:
    df_collar[colonne_soc] = 'CMO'
    
df_collar = df_collar.dropna(subset=['XCOLLAR', 'YCOLLAR', 'ZCOLLAR'])
df_collar['TYPE'] = df_collar['TYPE'].astype(str).str.strip().str.upper()

# =====================================================================
# INITIALISATION DE LA SCÈNE 3D (Mode Invisible)
# =====================================================================
# L'argument off_screen=True empêche l'ouverture d'une fenêtre locale
plotter = pv.Plotter(off_screen=True)
plotter.set_background('white')

# Affichage des collets
points = df_collar[['XCOLLAR', 'YCOLLAR', 'ZCOLLAR']].values
cloud = pv.PolyData(points)
plotter.add_mesh(cloud, color='red', point_size=5, render_points_as_spheres=True)

# =====================================================================
# CALCULS DES SONDAGES & LITHOLOGIES
# =====================================================================
df_survey = df_survey.sort_values(by=['BHID', 'AT'])

def calculer_xyz(profondeur, df_s, cx, cy, cz):
    if profondeur <= 0: return cx, cy, cz
    x, y, z, last_at = cx, cy, cz, 0.0
    for _, r in df_s.iterrows():
        at, brg, dip = r['AT'], r['BRG'], abs(r['DIP'])
        if profondeur <= at:
            d = profondeur - last_at
            x += d * np.cos(np.radians(dip)) * np.sin(np.radians(brg))
            y += d * np.cos(np.radians(dip)) * np.cos(np.radians(brg))
            z -= d * np.sin(np.radians(dip))
            return x, y, z
        d = at - last_at
        if d > 0:
            x += d * np.cos(np.radians(dip)) * np.sin(np.radians(brg))
            y += d * np.cos(np.radians(dip)) * np.cos(np.radians(brg))
            z -= d * np.sin(np.radians(dip))
        last_at = at
    return x, y, z

print("Modélisation en cours...")
couleurs = {'GRE': 'orange', 'PEL': 'brown', 'ST': 'gray', 'RC': 'yellow'}
cylindres = []

for idx, row in df_collar.iterrows():
    bhid = row['BHID']
    cx, cy, cz = row['XCOLLAR'], row['YCOLLAR'], row['ZCOLLAR']
    s_trou = df_survey[df_survey['BHID'] == bhid]
    l_trou = df_litho[df_litho['BHID'] == bhid]
    
    if s_trou.empty or l_trou.empty: continue
        
    for _, l in l_trou.iterrows():
        pf, pt, code = l['FROM'], l['TO'], l['CODE']
        if pd.isna(pf) or pd.isna(pt) or pf >= pt: continue
        
        xf, yf, zf = calculer_xyz(pf, s_trou, cx, cy, cz)
        xt, yt, zt = calculer_xyz(pt, s_trou, cx, cy, cz)
        
        ligne = pv.Line((xf, yf, zf), (xt, yt, zt))
        cyl = ligne.tube(radius=2.0)
        plotter.add_mesh(cyl, color=couleurs.get(code, 'lightgray'))

# Surfaces topo
fichiers_vtp = ["AF.vtp", "BKR.vtp", "BN.vtp", "GT.vtp"]
for f in fichiers_vtp:
    try:
        surf = pv.read(f)
        plotter.add_mesh(surf, color='saddlebrown', opacity=0.7)
    except: pass
    
try:
    trav = pv.read("Travaux_Miniers.vtp")
    plotter.add_mesh(trav, color='dimgray', opacity=0.85)
except: pass

plotter.show_grid(color='black')
plotter.reset_camera()

# =====================================================================
# INTERFACE TRAME (WEB)
# =====================================================================
with SinglePageLayout(server) as layout:
    layout.icon.click = ctrl.view_reset_camera
    layout.title.set_text("Modèle Géologique 3D - CMO")
    
    with layout.content:
        with vuetify.VContainer(fluid=True, classes="pa-0 fill-height"):
            # Affiche la vue 3D dans le navigateur
            view = vtk_widgets.VtkLocalView(plotter.render_window)
            ctrl.view_update = view.update

if __name__ == "__main__":
    # Récupération automatique du port attribué par SnapDeploy
    port_deploy = int(os.environ.get("PORT", 8080))
    server.start(port=port_deploy, host="0.0.0.0")
