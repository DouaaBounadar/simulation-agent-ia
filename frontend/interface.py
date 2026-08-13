import uuid

import requests
import streamlit as st
import sys
import os
import uuid
import requests
import streamlit as st

# 🚨 L'astuce pour permettre l'importation du dossier 'app' depuis 'frontend'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configuration de la page
st.set_page_config(page_title="Location Pro IA", page_icon="🏗️")
st.title("🤖 Assistant Commercial - Location Pro")

# Configuration de la page
st.set_page_config(page_title="Location Pro IA", page_icon="🏗️")
st.title("🤖 Assistant Commercial - Location Pro")

# Initialisation de la session
if "prospect_id" not in st.session_state:
    st.session_state.prospect_id = str(uuid.uuid4())
    st.session_state.messages = []
    # Nouvelles variables pour gérer le formulaire
    st.session_state.attente_formulaire = False 
    st.session_state.donnees_devis = {}

# URL de votre backend FastAPI
API_URL = "http://127.0.0.1:8000/chat/"

# 1. Affichage de l'historique des messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 2. AFFICHAGE DU FORMULAIRE (S'il a été déclenché par l'IA)
if st.session_state.attente_formulaire:
    from app.models.database import SessionLocal, Produit
    
    with st.chat_message("assistant"):
        st.write("### 📝 Informations de facturation")
        devis_ia = st.session_state.donnees_devis
        
        # --- 🚀 NOUVEAUTÉ : On récupère le VRAI catalogue depuis la BDD ---
        db_front = SessionLocal()
        produits_dispos = db_front.query(Produit).all()
        noms_produits = [p.nom for p in produits_dispos]
        db_front.close()
        
        # On essaie de pré-sélectionner ce que l'IA a compris, sinon le premier produit
        ia_produit = devis_ia.get('produit', '')
        index_prod = noms_produits.index(ia_produit) if ia_produit in noms_produits else 0
        
        with st.form("formulaire_client"):
            st.info("💡 Sélectionnez le matériel exact et la durée pour calculer le tarif officiel.")
            
            # --- LES NOUVEAUX MENUS DÉROULANTS ---
            produit_choisi = st.selectbox("📦 Matériel souhaité", noms_produits, index=index_prod)
            duree_choisie = st.selectbox(
                    "⏱️ Durée de location", 
                    ["1 jour", "3 jours", "1 semaine", "2 semaines", "1 mois", "6 mois", "1 an"]
                )
            
            st.divider()
            nom_client = st.text_input("Nom & Prénom *")
            email_client = st.text_input("Adresse Email *")
            entreprise_client = st.text_input("Nom de l'entreprise (Optionnel)")
            
            bouton_valider = st.form_submit_button("Générer mon devis officiel")
            
            if bouton_valider:
                if nom_client and email_client:
                    st.success("✅ Création du devis en cours...")
                    
                    url_finalisation = API_URL.replace("/chat/", "/chat/finaliser_devis")
                    
                    # --- LE NOUVEAU PAYLOAD (avec les données validées par l'humain) ---
                    payload_devis = {
                        "prospect_id": st.session_state.prospect_id,
                        "nom": nom_client,
                        "email": email_client,
                        "entreprise": entreprise_client,
                        "produit": produit_choisi,     # 👈 La valeur du menu déroulant
                        "montant": 0,                  # 👈 Le backend recalculera le vrai prix
                        "duree": duree_choisie         # 👈 La valeur du menu déroulant
                    }
                    
                    try:
                        import requests
                        requests.post(url_finalisation, json=payload_devis)
                    except Exception:
                        st.error("Erreur lors de la création du devis sur le serveur.")
                    
                    st.session_state.attente_formulaire = False
                    message_succes = f"✅ Parfait {nom_client.split()[0]} ! Le devis a été généré en brouillon pour la direction."
                    st.session_state.messages.append({"role": "assistant", "content": message_succes})
                    st.rerun()
                else:
                    st.error("⚠️ Veuillez remplir votre nom et votre adresse email.")

# 3. Champ de saisie (On le cache si le formulaire est ouvert)
elif prompt := st.chat_input("Que souhaitez-vous louer aujourd'hui ? (ex: Nacelle ciseaux 12m)"):
    
    with st.chat_message("user"):
        st.markdown(prompt)
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.spinner("L'agent réfléchit..."):
        try:
            payload = {
                "prospect_id": st.session_state.prospect_id,
                "message": prompt
            }
            reponse = requests.post(API_URL, json=payload)
            
            if reponse.status_code == 200:
                donnees = reponse.json() # On extrait le dictionnaire (C'est votre ancienne 'reponse_api')
                reponse_ia = donnees.get("reponse_agent", "")
                
                # NOUVEAU : On écoute le signal caché !
                if donnees.get("action") == "afficher_formulaire":
                    st.session_state.attente_formulaire = True
                    st.session_state.donnees_devis = donnees.get("donnees_devis", {})
            else:
                reponse_ia = f"❌ Erreur du serveur ({reponse.status_code})."
                
        except Exception:
            reponse_ia = "❌ Impossible de joindre le backend. FastAPI est-il lancé ?"

    with st.chat_message("assistant"):
        st.markdown(reponse_ia)
        
    st.session_state.messages.append({"role": "assistant", "content": reponse_ia})
    
    # Si le formulaire a été déclenché, on force le rafraîchissement pour l'afficher instantanément
    if st.session_state.attente_formulaire:
        st.rerun()