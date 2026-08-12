import streamlit as st
import requests
import uuid

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
    with st.chat_message("assistant"):
        with st.form("formulaire_client"):
            st.write("### 📝 Informations de facturation")
            devis = st.session_state.donnees_devis
            
            st.info(f"📦 Produit : {devis.get('produit')} \n\n💶 Total : {devis.get('montant')} € HT")
            
            nom_client = st.text_input("Nom & Prénom *")
            email_client = st.text_input("Adresse Email *")
            entreprise_client = st.text_input("Nom de l'entreprise (Optionnel)")
            
            bouton_valider = st.form_submit_button("Générer mon devis en PDF")
            
            if bouton_valider:
                if nom_client and email_client:
                    st.success("✅ Informations validées ! Création du devis en cours...")
                    
                    # --- NOUVEAU CODE : L'appel vers l'API FastAPI ---
                    url_finalisation = API_URL.replace("/chat/", "/chat/finaliser_devis")
                    
                    payload_devis = {
                        "prospect_id": st.session_state.prospect_id,
                        "nom": nom_client,
                        "email": email_client,
                        "entreprise": entreprise_client,
                        "produit": devis.get("produit", "Matériel"),
                        "montant": float(devis.get("montant", 0)),
                        "duree": devis.get("duree", "Non précisée")
                    }
                    
                    try:
                        requests.post(url_finalisation, json=payload_devis)
                    except Exception as e:
                        st.error("Erreur lors de la création du devis sur le serveur.")
                    # --------------------------------------------------
                    
                    st.session_state.attente_formulaire = False
                    message_succes = f"✅ Parfait {nom_client.split()[0]} ! Le devis a été généré et sera envoyé à l'adresse {email_client}."
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
                
        except Exception as e:
            reponse_ia = "❌ Impossible de joindre le backend. FastAPI est-il lancé ?"

    with st.chat_message("assistant"):
        st.markdown(reponse_ia)
        
    st.session_state.messages.append({"role": "assistant", "content": reponse_ia})
    
    # Si le formulaire a été déclenché, on force le rafraîchissement pour l'afficher instantanément
    if st.session_state.attente_formulaire:
        st.rerun()