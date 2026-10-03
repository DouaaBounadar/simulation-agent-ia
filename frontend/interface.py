import uuid
import sys
import os
import requests
import streamlit as st

# 🚨 L'astuce pour permettre l'importation du dossier 'app' depuis 'frontend'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configuration de la page
st.set_page_config(page_title="Location Pro IA", page_icon="🏗️")
st.title("🤖 Assistant Commercial - Location Pro")

# Initialisation de la session (simplifiée)
if "prospect_id" not in st.session_state:
    st.session_state.prospect_id = str(uuid.uuid4())
    st.session_state.messages = []

# URL de votre backend FastAPI
API_URL = "http://127.0.0.1:8000/chat/"

# 1. Affichage de l'historique des messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 2. Champ de saisie direct (Plus de formulaire !)
if prompt := st.chat_input("Que souhaitez-vous louer aujourd'hui ? (ex: Nacelle ciseaux 12m)"):
    
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
                donnees = reponse.json() 
                reponse_ia = donnees.get("reponse_agent", "")
                
                # Sécurité si la réponse est une liste
                if isinstance(reponse_ia, list) and len(reponse_ia) > 0:
                    reponse_ia = reponse_ia[0].get("text", reponse_ia)
                    
            else:
                reponse_ia = f"❌ Erreur du serveur ({reponse.status_code})."
                
        except Exception:
            reponse_ia = "❌ Impossible de joindre le backend. FastAPI est-il lancé ?"

    with st.chat_message("assistant"):
        st.markdown(reponse_ia)
        
    st.session_state.messages.append({"role": "assistant", "content": reponse_ia})