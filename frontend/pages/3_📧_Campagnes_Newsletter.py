import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
import sys
import os
import time # 👈 Ajout obligatoire pour la pause de sécurité
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from app.utils.email_sender import envoyer_email_marketing # 👈 La vraie fonction d'envoi

# Connexion aux dossiers de l'application
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from app.models.database import SessionLocal, Prospect, Devis

st.set_page_config(page_title="Campagnes Marketing", page_icon="📧", layout="wide")
st.title("📧 Campagne Mensuelle - Prospects à Froid")
st.markdown("Relancez intelligemment vos contacts inactifs avec des messages personnalisés par l'IA.")

db: Session = SessionLocal()

try:
    # 1. On cherche UNIQUEMENT les prospects froids (qui ne sont pas "Client")
    prospects_froids = db.query(Prospect).filter(Prospect.status.notin_(["Client", "CLIENT"])).all()

    if not prospects_froids:
        st.success("🎉 Bonne nouvelle : vous n'avez aucun prospect à froid. Tout le monde est client !")
    else:
        # --- Statistiques ---
        st.metric("🎯 Contacts dans la base de relance", len(prospects_froids))
        
        # --- Affichage de la liste ---
        data = []
        for p in prospects_froids:
            data.append({
                "Nom": p.nom or "Client Web",
                "Email": p.email or "Non renseigné",
                "Statut": p.status,
                "Date de création": p.date_creation.strftime("%d/%m/%Y") if p.date_creation else "N/A"
            })
        
        st.dataframe(pd.DataFrame(data), width="stretch")
        st.divider()

        # --- Panneau de contrôle IA ---
        st.subheader("🤖 Lancer la newsletter du mois")
        
        promo_du_mois = st.text_input(
            "Quelle est l'offre ou la nouveauté de ce mois-ci ?", 
            value="-15% sur la livraison pour votre prochaine location"
        )
        
        if st.button("🚀 Générer et envoyer les emails personnalisés", type="primary"):
            
            # Initialisation de l'IA (On remet le bon modèle !)
            llm = ChatGoogleGenerativeAI(
                model="gemini-3.6-flash", 
                google_api_key=os.getenv("GOOGLE_API_KEY"),
                temperature=0.7
            )
            
            st.write("### 📬 Aperçu des envois en direct :")
            barre_progression = st.progress(0)
            emails_envoyes = 0
            
            for index, prospect in enumerate(prospects_froids):
                if not prospect.email or "non_renseigne" in prospect.email:
                    continue
                
                dernier_devis = db.query(Devis).filter(Devis.prospect_id == prospect.prospect_id).first()
                materiel_recherche = "du matériel de chantier"
                if dernier_devis and dernier_devis.produit_id:
                    materiel_recherche = f"notre matériel (Devis {dernier_devis.devis_id})"

                system_prompt = "Tu es le responsable marketing de 'Location Pro'. Ton but est de rédiger un email très court (3 phrases maximum) pour relancer un ancien contact."
                user_prompt = f"Le prospect s'appelle {prospect.nom}. Dans le passé, il s'est intéressé à : {materiel_recherche}. Inclus cette offre du mois de manière naturelle : '{promo_du_mois}'. Sois professionnel, chaleureux et persuasif."
                
             # L'IA rédige l'email sur mesure
                reponse_ia = llm.invoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt)
                ])
                
                # 🛠️ EXTRACTION SÉCURISÉE DU TEXTE (Evite l'erreur builtins.list)
                if isinstance(reponse_ia.content, list):
                    texte_email = "\n".join([
                        item.get("text", str(item)) if isinstance(item, dict) else str(item) 
                        for item in reponse_ia.content
                    ])
                else:
                    texte_email = str(reponse_ia.content)

                sujet_email = f"Une offre spéciale pour vous, {prospect.nom} !"
                
                # 👇 ENVOI RÉEL SÉCURISÉ 👇
                envoyer_email_marketing(email_client=prospect.email, sujet=sujet_email, corps=texte_email)
                
                with st.expander(f"✉️ Email envoyé pour {prospect.nom} ({prospect.email})", expanded=False):
                    st.write(texte_email)
                    st.caption("✅ Envoyé avec succès ! (Vrai email)")
                
                emails_envoyes += 1
                barre_progression.progress((index + 1) / len(prospects_froids))
                
                # Pause pour ne pas bloquer l'API gratuite de Google
                time.sleep(4) 
                
            st.success(f"🎉 Campagne terminée avec succès ! {emails_envoyes} emails personnalisés ont été envoyés.")

except Exception as e:
    st.error(f"Une erreur s'est produite : {e}")
finally:
    db.close()