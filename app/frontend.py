import streamlit as st
import requests
import uuid

# Configuration de la page
st.set_page_config(page_title="Location Pro IA", page_icon="🏗️")
st.title("🤖 Assistant Commercial - Location Pro")

# Initialisation de la session (pour se souvenir de l'utilisateur)
if "prospect_id" not in st.session_state:
    st.session_state.prospect_id = str(uuid.uuid4())
    st.session_state.messages = []

# URL de votre backend FastAPI
API_URL = "http://127.0.0.1:8000/chat/"

# Affichage de l'historique des messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Champ de saisie pour l'utilisateur
if prompt := st.chat_input("Que souhaitez-vous louer aujourd'hui ? (ex: Nacelle ciseaux 12m)"):
    
    # 1. Afficher le message de l'utilisateur
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Sauvegarder dans l'historique local
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # 2. Envoyer la requête au Backend (FastAPI)
    with st.spinner("L'agent réfléchit..."):
        try:
            payload = {
                "prospect_id": st.session_state.prospect_id,
                "message": prompt
            }
            reponse = requests.post(API_URL, json=payload)
            
            if reponse.status_code == 200:
                donnees = reponse.json()
                reponse_ia = donnees["reponse_agent"]
            else:
                reponse_ia = f"❌ Erreur du serveur ({reponse.status_code}). Vérifiez que FastAPI tourne."
                
        except Exception as e:
            reponse_ia = "❌ Impossible de joindre le backend. FastAPI est-il lancé ?"

    # 3. Afficher la réponse de l'IA
    with st.chat_message("assistant"):
        st.markdown(reponse_ia)
        
    # Sauvegarder dans l'historique local
    st.session_state.messages.append({"role": "assistant", "content": reponse_ia})