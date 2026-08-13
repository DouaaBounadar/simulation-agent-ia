import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
import sys
import os

# Astuce pour permettre l'importation du backend depuis le dossier frontend/pages
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.models.database import SessionLocal, Prospect, Devis

st.set_page_config(page_title="Dashboard Directeur", page_icon="📊", layout="wide")

# 🔒 Système de connexion basique
def check_password():
    """Vérifie le mot de passe avant d'afficher le contenu."""
    def password_entered():
        if st.session_state["password"] == "admin123": # ⚠️ Mot de passe en dur pour l'exemple
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # On efface le mot de passe de la session pour la sécurité
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Mot de passe Directeur", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Mot de passe Directeur", type="password", on_change=password_entered, key="password")
        st.error("Mot de passe incorrect")
        return False
    return True

if check_password():
    st.title("📊 Tableau de Bord Directeur")
    st.markdown("Bienvenue dans l'espace d'administration de Location Pro.")
    
    db: Session = SessionLocal()
    
    try:
        # --- 1. LES KPIs (Indicateurs clés) ---
        st.header("📈 Indicateurs Temps Réel")
        col1, col2, col3, col4 = st.columns(4)
        
        total_prospects = db.query(Prospect).count()
        devis_attente = db.query(Devis).filter(Devis.status == "Généré").count()
        devis_acceptes = db.query(Devis).filter(Devis.status == "Accepté").count()
        
        # Calcul du CA (Somme des devis acceptés)
        devis_valides = db.query(Devis).filter(Devis.status == "Accepté").all()
        chiffre_affaires = sum([d.prix_total_ttc for d in devis_valides if d.prix_total_ttc])

        with col1:
            st.metric(label="📥 Nouveaux Prospects", value=total_prospects)
        with col2:
            st.metric(label="📋 Devis à Valider", value=devis_attente)
        with col3:
            st.metric(label="✅ Locations (Mois)", value=devis_acceptes)
        with col4:
            st.metric(label="💰 Chiffre d'Affaires", value=f"{chiffre_affaires:,.2f} €")
            
        st.divider()

        # --- 2. LISTE DES DEVIS EN ATTENTE (Brouillons) ---
        st.header("📋 Devis en attente de validation")
        
        devis_list = db.query(Devis, Prospect).join(Prospect, Devis.prospect_id == Prospect.prospect_id)\
                       .filter(Devis.status == "Généré").all()
                       
        if not devis_list:
            st.info("Aucun devis en attente de validation. Bravo !")
        else:
            # On prépare les données pour un beau tableau
            data = []
            for d, p in devis_list:
                data.append({
                    "ID Devis": d.devis_id,
                    "Client": p.nom,
                    "Email": p.email,
                    "Total TTC": f"{d.prix_total_ttc} €",
                    "Date": d.date_creation.strftime("%d/%m/%Y") if d.date_creation else "N/A"
                })
            
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
            
            # --- 3. ACTIONS DE VALIDATION ---
            st.subheader("Actions rapides")
            col_action1, col_action2 = st.columns([1, 2])
            with col_action1:
                devis_a_valider = st.selectbox("Sélectionner un devis :", [d["ID Devis"] for d in data])
            with col_action2:
                st.write("") # Pour aligner verticalement
                st.write("")
                if st.button("✅ Valider et Envoyer (Simulation)", type="primary"):
                    # Ici, nous coderons l'Étape 5 plus tard !
                    st.success(f"Le devis {devis_a_valider} a été validé ! (Ceci est une simulation pour l'instant)")

    except Exception as e:
        st.error(f"Erreur lors de la connexion à la base de données : {e}")
    finally:
        db.close()