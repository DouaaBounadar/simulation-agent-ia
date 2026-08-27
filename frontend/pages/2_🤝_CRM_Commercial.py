import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import sys
import os
import time

# Ajout du chemin pour importer les modules de l'application
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from app.models.database import SessionLocal, Prospect, Devis

st.set_page_config(page_title="CRM Commercial", page_icon="🎯", layout="wide")

# --- INJECTION CSS PREMIUM (Thème Ventes & Énergie) ---
st.markdown("""
    <style>
        /* Animation d'entrée douce */
        @keyframes slideIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .stApp {
            animation: slideIn 0.6s ease-out;
            background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%);
        }

        /* Nettoyage de l'UI Streamlit */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}

        /* Cartes KPIs "Pipeline" (Bordure Orange dynamique) */
        div[data-testid="metric-container"] {
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(8px);
            border: 1px solid rgba(255, 255, 255, 0.6);
            padding: 20px;
            border-radius: 16px;
            box-shadow: 0 8px 20px -4px rgba(0, 0, 0, 0.08);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border-left: 6px solid #f97316; /* Orange commercial */
        }
        div[data-testid="metric-container"]:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 25px -5px rgba(249, 115, 22, 0.15);
            border-left: 6px solid #fb923c;
        }

        /* Typographie des KPIs */
        div[data-testid="stMetricLabel"] > div > div > p {
            font-size: 1.1rem !important;
            font-weight: 700 !important;
            color: #475569 !important;
        }
        div[data-testid="stMetricValue"] > div {
            font-size: 2.2rem !important;
            font-weight: 900 !important;
            color: #1e293b !important;
        }

        /* Design des boutons d'action */
        .stButton > button {
            border-radius: 10px !important;
            font-weight: 700 !important;
            padding: 12px !important;
            transition: all 0.3s ease !important;
            border: none !important;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        }
        .stButton > button:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 15px rgba(0, 0, 0, 0.1);
        }
        
        /* Personnalisation des titres */
        h1, h2, h3 {
            color: #0f172a !important;
            font-weight: 800 !important;
            letter-spacing: -0.5px !important;
        }
    </style>
""", unsafe_allow_html=True)

st.markdown("<h1>🎯 Espace Commercial & Négociations</h1>", unsafe_allow_html=True)
st.markdown("### Gérez votre pipeline, relancez vos prospects et clôturez vos ventes.")

db: Session = SessionLocal()

try:
    # --- 1. RÉCUPÉRATION DES DONNÉES ---
    prospects = db.query(Prospect).filter(
        Prospect.status.notin_(["Client", "Perdu", "CLIENT"]),
        Prospect.nom != "Client Web Anonyme",
        Prospect.nom != "Client WhatsApp"
    ).all()
    
    if not prospects:
        st.success("🎉 Excellent travail ! Votre liste de relance est totalement vide.")
    else:
        # --- 2. LES KPIs DU COMMERCIAL ---
        ca_potentiel = sum([float(p.montant_en_cours) for p in prospects if p.montant_en_cours])
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("🔥 Opportunités en cours", len(prospects))
        with col2:
            st.metric("💰 Portefeuille Négociation", f"{ca_potentiel:,.2f} €")
        
        st.divider()

       # --- 3. AFFICHAGE DU TABLEAU ---
        st.markdown("### 📋 Pipeline de Relances")
        data = []
        for p in prospects:
            data.append({
                "ID": str(p.prospect_id),
                "Client": p.nom or "Inconnu",
                "Email": p.email or "-",
                "Téléphone": p.telephone or "-",
                "Statut Actuel": p.status,
                "Montant Potentiel": f"{p.montant_en_cours} €" if p.montant_en_cours else "0 €",
                "Date de Relance": p.date_relance.strftime("%d/%m/%Y") if p.date_relance else "À définir"
            })
            
        df = pd.DataFrame(data)
        # Utilisation de width="stretch" au lieu de use_container_width
        st.dataframe(df.drop(columns=["ID"]), width="stretch")

        st.divider()

        # --- 4. PANNEAU D'ACTIONS INTERACTIF ---
        st.markdown("### ⚡ Centre d'Action Rapide")
        st.caption("Sélectionnez un contact après votre appel téléphonique pour mettre à jour son statut.")
        
        options_prospects = {f"{p['Client']} [{p['ID'][:6]}] ({p['Montant Potentiel']})": p['ID'] for p in data}
        
        col_select, col_actions = st.columns([1, 2])
        
        with col_select:
            choix = st.selectbox("Dossier client traité :", list(options_prospects.keys()))
            prospect_id_choisi = options_prospects[choix]
            
        with col_actions:
            st.write("") 
            st.write("")
            btn_col1, btn_col2, btn_col3 = st.columns(3)
            
            with btn_col1:
                if st.button("📞 Repoussé à demain", use_container_width=True):
                    prospect_db = db.query(Prospect).filter(Prospect.prospect_id == prospect_id_choisi).first()
                    prospect_db.date_relance = datetime.now() + timedelta(days=1)
                    db.commit()
                    st.info(f"🗓️ Relance de {prospect_db.nom} planifiée pour demain.")
                    time.sleep(1.5)
                    st.rerun()
                    
            with btn_col2:
                if st.button("✅ CONTRAT SIGNÉ", type="primary", use_container_width=True):
                    prospect_db = db.query(Prospect).filter(Prospect.prospect_id == prospect_id_choisi).first()
                    prospect_db.status = "Client"
                    
                    devis_lies = db.query(Devis).filter(Devis.prospect_id == prospect_id_choisi).all()
                    for d in devis_lies:
                        d.status = "Accepté"
                        d.date_acceptation = datetime.now()
                        
                    db.commit()
                    st.balloons()
                    st.success(f"🏆 Incroyable ! {prospect_db.nom} est officiellement devenu client.")
                    time.sleep(2)
                    st.rerun()
            
            with btn_col3:
                if st.button("❌ Négociation Perdue", use_container_width=True):
                    prospect_db = db.query(Prospect).filter(Prospect.prospect_id == prospect_id_choisi).first()
                    prospect_db.status = "Perdu"
                    
                    devis_lies = db.query(Devis).filter(Devis.prospect_id == prospect_id_choisi).all()
                    for d in devis_lies:
                        if d.status != "Accepté":
                            d.status = "Rejeté"
                            d.date_rejet = datetime.now()
                            
                    db.commit()
                    st.warning(f"🚫 Dossier fermé. Le prospect {prospect_db.nom} est classé comme perdu.")
                    time.sleep(1.5)
                    st.rerun()

except Exception as e:
    st.error(f"Une erreur système est survenue : {e}")
finally:
    db.close()