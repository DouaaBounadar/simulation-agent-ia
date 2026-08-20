import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import sys
import os

# Ajout du chemin pour importer les modules de l'application
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from app.models.database import SessionLocal, Prospect, Devis

st.set_page_config(page_title="CRM Commercial", page_icon="🤝", layout="wide")
st.title("🤝 Espace Commercial - Relances et Négociations")
st.markdown("Suivez vos prospects et clôturez vos ventes.")

db: Session = SessionLocal()

try:
    # --- 1. RÉCUPÉRATION DES DONNÉES ---
    # On affiche uniquement les prospects en cours de négociation (Qualifié, Devis, À rappeler)
    prospects = db.query(Prospect).filter(
        Prospect.status.notin_(["Client", "Perdu"])
    ).all()
    
    if not prospects:
        st.success("🎉 Aucun prospect à relancer. Votre liste est vide !")
    else:
        # --- 2. LES KPIs DU COMMERCIAL ---
        ca_potentiel = sum([float(p.montant_en_cours) for p in prospects if p.montant_en_cours])
        
        col1, col2, col3 = st.columns(3)
        col1.metric("🎯 Prospects à traiter", len(prospects))
        col2.metric("💰 Portefeuille en négociation", f"{ca_potentiel:,.2f} €")
        
        st.divider()

       # --- 3. AFFICHAGE DU TABLEAU ---
        st.subheader("📋 Liste des tâches et relances")
        data = []
        for p in prospects:
            data.append({
                "ID": str(p.prospect_id),
                "Client": p.nom or "Inconnu",
                "Email": p.email or "-",           # 👈 Colonne Email
                "Téléphone": p.telephone or "-",   # 👈 Colonne Téléphone
                "Statut Actuel": p.status,
                "Montant Potentiel": f"{p.montant_en_cours} €" if p.montant_en_cours else "0 €",
                "Date de Relance": p.date_relance.strftime("%d/%m/%Y") if p.date_relance else "À définir"
            })
            
        df = pd.DataFrame(data)
        st.dataframe(df.drop(columns=["ID"]), use_container_width=True) # On cache l'ID complexe à l'écran

        st.divider()

        # --- 4. PANNEAU D'ACTIONS INTERACTIF ---
        st.subheader("⚡ Actions rapides sur un prospect")
        
        # On crée un dictionnaire pour lier le nom affiché à l'ID technique du prospect
        options_prospects = {f"{p['Client']} ({p['Montant Potentiel']})": p['ID'] for p in data}
        
        col_select, col_actions = st.columns([1, 2])
        
        with col_select:
            choix = st.selectbox("Sélectionnez le client que vous venez de contacter :", list(options_prospects.keys()))
            prospect_id_choisi = options_prospects[choix]
            
        with col_actions:
            st.write("") # Espacement
            st.write("")
            btn_col1, btn_col2, btn_col3 = st.columns(3)
            
            # Action 1 : L'appel a été fait, on décale la date
            with btn_col1:
                if st.button("📞 J'ai appelé (Relancer demain)", use_container_width=True):
                    prospect_db = db.query(Prospect).filter(Prospect.prospect_id == prospect_id_choisi).first()
                    prospect_db.date_relance = datetime.now() + timedelta(days=1)
                    db.commit()
                    st.success(f"Appel noté ! Relance de {prospect_db.nom} reportée à demain.")
                    import time; time.sleep(1); st.rerun()
                    
            # Action 2 : LE CLIENT DIT OUI (Victoire !)
            with btn_col2:
                if st.button("✅ Contrat Signé !", type="primary", use_container_width=True):
                    prospect_db = db.query(Prospect).filter(Prospect.prospect_id == prospect_id_choisi).first()
                    prospect_db.status = "Client"
                    
                    # On met à jour les devis de ce prospect pour dire qu'ils sont acceptés
                    devis_lies = db.query(Devis).filter(Devis.prospect_id == prospect_id_choisi).all()
                    for d in devis_lies:
                        d.status = "Accepté"
                        d.date_acceptation = datetime.now()
                        
                    db.commit()
                    st.balloons()
                    st.success(f"Félicitations ! {prospect_db.nom} devient un Client.")
                    import time; time.sleep(2); st.rerun()
            
            # Action 3 : LE CLIENT DIT NON (Perdu)
            with btn_col3:
                if st.button("❌ Refusé (Perdu)", use_container_width=True):
                    prospect_db = db.query(Prospect).filter(Prospect.prospect_id == prospect_id_choisi).first()
                    prospect_db.status = "Perdu"
                    
                    devis_lies = db.query(Devis).filter(Devis.prospect_id == prospect_id_choisi).all()
                    for d in devis_lies:
                        if d.status != "Accepté":
                            d.status = "Rejeté"
                            d.date_rejet = datetime.now()
                            
                    db.commit()
                    st.warning(f"C'est noté. Le prospect {prospect_db.nom} a été classé comme perdu.")
                    import time; time.sleep(1); st.rerun()

except Exception as e:
    st.error(f"Une erreur est survenue : {e}")
finally:
    db.close()