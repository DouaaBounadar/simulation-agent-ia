import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
import sys
import os
from datetime import datetime

# 🚨 L'astuce DOIT être placée AVANT les imports de 'app' !
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.utils.email_sender import envoyer_devis_client
from app.models.database import SessionLocal, Prospect, Devis

st.set_page_config(page_title="Dashboard Directeur", page_icon="📊", layout="wide")

# ... (le reste du code ne change pas) ...

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
        # On cherche désormais les statuts "Brouillon"
        devis_attente = db.query(Devis).filter(Devis.status == "Brouillon").count()
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
                       .filter(Devis.status == "Brouillon").all()
                       
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
            st.dataframe(df, width="stretch")
            
           # --- 3. ACTIONS DE VALIDATION ---
            st.subheader("Actions rapides")
            col_action1, col_action2, col_action3 = st.columns([2, 1, 1])
            
            with col_action1:
                devis_a_valider = st.selectbox("Sélectionner un devis :", [d["ID Devis"] for d in data])
                
            with col_action2:
                st.write("") # Pour aligner verticalement
                st.write("")
                if st.button("✅ Valider et Envoyer", type="primary"):
                    # 1. On cherche le devis et le prospect dans la base de données
                    devis_db = db.query(Devis).filter(Devis.devis_id == devis_a_valider).first()
                    
                    if devis_db:
                        prospect_db = db.query(Prospect).filter(Prospect.prospect_id == devis_db.prospect_id).first()
                        
                        try:
                            # 2. On construit le chemin absolu du PDF
                            dossier_racine = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
                            chemin_pdf = os.path.join(dossier_racine, "generated_pdfs", f"{devis_db.devis_id}.pdf")
                            
                            # 🔍 Vérification du fichier
                            if not os.path.exists(chemin_pdf):
                                st.error(f"❌ Le fichier PDF est introuvable ici : {chemin_pdf}")
                                st.caption("💡 *Note : Créez un NOUVEAU devis depuis l'agent pour tester !*")
                                st.stop()
                            else:
                                st.success(f"📄 PDF trouvé avec succès : `{devis_db.devis_id}.pdf`")
                            
                            # 3. 📧 On envoie l'email officiel au client (UNE SEULE FOIS ! 🎯)
                            envoyer_devis_client(prospect_db.email, prospect_db.nom, chemin_pdf)
                            
                            # 4. 💾 On met à jour la base de données
                            devis_db.status = "Envoyé"
                            devis_db.date_envoi = datetime.now()
                            db.commit()
                            
                            # 5. On affiche un succès et on rafraîchit la page
                            st.success(f"✅ Le devis {devis_a_valider} a été officiellement validé et envoyé à {prospect_db.email} !")
                            
                            # Pause d'une seconde pour que le directeur ait le temps de lire le message vert
                            import time
                            time.sleep(1.5)
                            st.rerun() # Rafraîchit l'interface pour faire disparaître le devis de la liste
                            
                        except Exception as e:
                            st.error(f"❌ Erreur lors de la validation : {e}")

            with col_action3:
                st.write("") # Pour aligner verticalement
                st.write("")
                if st.button("❌ Refuser (Erreur)"):
                    devis_db = db.query(Devis).filter(Devis.devis_id == devis_a_valider).first()
                    if devis_db:
                        # On annule simplement le devis dans la base de données
                        devis_db.status = "Annulé"
                        db.commit()
                        st.warning(f"🚫 Le devis {devis_a_valider} a été rejeté. Il n'a pas été envoyé au client.")
                        
                        import time
                        time.sleep(1.5)
                        st.rerun() # Disparaît du tableau de bord

    except Exception as e:
        st.error(f"Erreur lors de la connexion à la base de données : {e}")
    finally:
        db.close()