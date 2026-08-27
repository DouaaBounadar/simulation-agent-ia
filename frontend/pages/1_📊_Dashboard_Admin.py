import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
import sys
import os
from datetime import datetime
import time

# Permet l'import des modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from app.utils.email_sender import envoyer_devis_client
from app.models.database import SessionLocal, Prospect, Devis

st.set_page_config(page_title="Dashboard Directeur", page_icon="🚀", layout="wide")

# --- INJECTION CSS PREMIUM ---
st.markdown("""
    <style>
        /* 1. Animation d'entrée et fond moderne */
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(15px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .stApp {
            animation: fadeIn 0.8s ease-out;
            background: linear-gradient(135deg, #f6f8fb 0%, #e5ebf4 100%);
        }

        /* 2. Sidebar premium avec dégradé sombre */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
            border-right: 1px solid #334155;
        }
        [data-testid="stSidebar"] * {
            color: #f8fafc !important;
        }

        /* 3. Nettoyage de l'UI Streamlit */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}

        /* 4. Cartes KPIs style "Glassmorphism" avec bordures dynamiques */
        div[data-testid="metric-container"] {
            background: rgba(255, 255, 255, 0.8);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.5);
            padding: 20px;
            border-radius: 16px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05);
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            border-left: 6px solid #3b82f6; /* Bleu dynamique */
        }
        div[data-testid="metric-container"]:hover {
            transform: translateY(-7px) scale(1.02);
            box-shadow: 0 20px 25px -5px rgba(59, 130, 246, 0.15);
            border-left: 6px solid #8b5cf6; /* Devient Violet au survol */
        }
        
        /* Personnalisation des textes des KPIs */
        div[data-testid="stMetricLabel"] > div > div > p {
            font-size: 1.1rem !important;
            font-weight: 600 !important;
            color: #475569 !important;
        }
        div[data-testid="stMetricValue"] > div {
            font-size: 2.2rem !important;
            font-weight: 800 !important;
            color: #0f172a !important;
        }

        /* 5. Boutons d'action : Dégradé vibrant et effet néon */
        .stButton > button {
            background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
            color: white !important;
            border: none;
            border-radius: 12px !important;
            padding: 10px 24px;
            font-weight: 700 !important;
            letter-spacing: 0.5px;
            transition: all 0.3s ease !important;
        }
        .stButton > button:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 20px -5px rgba(139, 92, 246, 0.5);
        }

        /* 6. Typographie des titres */
        h1, h2, h3 {
            color: #1e293b !important;
            font-weight: 800 !important;
            letter-spacing: -0.5px !important;
        }
    </style>
""", unsafe_allow_html=True)

def check_password():
    def password_entered():
        if st.session_state["password"] == "admin123":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.markdown("### 🔒 Accès Sécurisé - Direction")
        st.text_input("Mot de passe", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.markdown("### 🔒 Accès Sécurisé - Direction")
        st.text_input("Mot de passe", type="password", on_change=password_entered, key="password")
        st.error("Mot de passe incorrect")
        return False
    return True

if check_password():
    st.markdown("<h1>🚀 Centre de Pilotage <em>Location Pro</em></h1>", unsafe_allow_html=True)
    st.markdown("### Vision globale et validation des ventes")
    
    db: Session = SessionLocal()
    
    try:
        # --- 1. LES KPIs ---
        st.write("") # Espace
        col1, col2, col3, col4 = st.columns(4)
        
        total_prospects = db.query(Prospect).count()
        devis_attente = db.query(Devis).filter(Devis.status == "Brouillon").count()
        devis_acceptes = db.query(Devis).filter(Devis.status == "Accepté").count()
        
        devis_valides = db.query(Devis).filter(Devis.status == "Accepté").all()
        chiffre_affaires = sum([float(d.prix_total_ttc) for d in devis_valides if d.prix_total_ttc])

        with col1:
            st.metric(label="📥 Prospects Globaux", value=total_prospects)
        with col2:
            st.metric(label="⚡ Devis en Attente", value=devis_attente)
        with col3:
            st.metric(label="✅ Locations Validées", value=devis_acceptes)
        with col4:
            st.metric(label="💎 Chiffre d'Affaires", value=f"{chiffre_affaires:,.2f} €")
            
        st.divider()

        # --- 2. BARRE LATÉRALE ---
        st.sidebar.markdown("## 🎛️ Filtres Avancés")
        filtre_statut = st.sidebar.multiselect(
            "Visualiser par statut :",
            options=["Brouillon", "Envoyé", "Accepté", "Annulé", "Rejeté"],
            default=["Brouillon", "Accepté"] 
        )

        # --- 3. GRAPHIQUE VISUEL ---
        st.markdown("### 📊 Répartition des Revenus")
        tous_les_devis = db.query(Devis).filter(Devis.status.in_(filtre_statut)).all()
        
        if tous_les_devis:
            df_graph = pd.DataFrame([{
                "Statut": d.status, 
                "Montant": float(d.prix_total_ttc) if d.prix_total_ttc else 0.0
            } for d in tous_les_devis])
            
            df_groupe = df_graph.groupby("Statut").sum().reset_index()
            # Utilisation d'une couleur plus sympa pour le graphique
            st.bar_chart(data=df_groupe, x="Statut", y="Montant", width="stretch", color="#8b5cf6")
        else:
            st.info("Aucune donnée disponible pour ces filtres.")

        st.divider()

        # --- 4. TABLEAU INTERACTIF (Cases à cocher) ---
        st.markdown("### 📋 Validation Express")
        st.caption("Sélectionnez les contrats à approuver et validez-les en un seul clic.")
        
        devis_list = db.query(Devis, Prospect).join(Prospect, Devis.prospect_id == Prospect.prospect_id)\
                       .filter(Devis.status.in_(filtre_statut)).all()
                       
        if not devis_list:
            st.info("Tout est à jour ! Aucun devis ne correspond à ces critères.")
        else:
            data = []
            for d, p in devis_list:
                data.append({
                    "Approuver": False,
                    "ID Devis": d.devis_id,
                    "Client": p.nom,
                    "Total TTC (€)": float(d.prix_total_ttc) if d.prix_total_ttc else 0.0,
                    "Statut": d.status,
                    "Création": d.date_creation.strftime("%d/%m/%Y") if d.date_creation else "N/A"
                })
            
            df = pd.DataFrame(data)
            
            df_edite = st.data_editor(
                df,
                column_config={
                    "Approuver": st.column_config.CheckboxColumn("Approuver", default=False),
                    "Total TTC (€)": st.column_config.NumberColumn("Total TTC (€)", format="%.2f €")
                },
                disabled=["ID Devis", "Client", "Total TTC (€)", "Statut", "Création"], 
                hide_index=True,
                width="stretch"
            )
            
            # --- 5. ACTION DE VALIDATION MULTIPLE ---
            devis_selectionnes = df_edite[df_edite["Approuver"] == True]["ID Devis"].tolist()
            
            if len(devis_selectionnes) > 0:
                st.write("")
                if st.button(f"✨ Approuver et Envoyer ({len(devis_selectionnes)} devis)"):
                    with st.spinner('🚀 Sécurisation et envoi des contrats en cours...'):
                        for devis_id in devis_selectionnes:
                            devis_db = db.query(Devis).filter(Devis.devis_id == devis_id).first()
                            prospect_db = db.query(Prospect).filter(Prospect.prospect_id == devis_db.prospect_id).first()
                            
                            dossier_racine = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
                            chemin_pdf = os.path.join(dossier_racine, "generated_pdfs", f"{devis_id}.pdf")
                            
                            if os.path.exists(chemin_pdf):
                                envoyer_devis_client(prospect_db.email, prospect_db.nom, chemin_pdf)
                                devis_db.status = "Envoyé"
                                devis_db.date_envoi = datetime.now()
                            else:
                                st.error(f"Fichier manquant pour le devis {devis_id}")
                                
                        db.commit()
                    st.success("🎉 Opération réussie ! Les clients ont reçu leurs contrats.")
                    time.sleep(2)
                    st.rerun()

    except Exception as e:
        st.error(f"Erreur système critique : {e}")
    finally:
        db.close()