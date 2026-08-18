import os
import google.generativeai as genai
from dotenv import load_dotenv

# Charge les variables du fichier .env
load_dotenv()

# Configure la clé API
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Demande à Google la liste de vos modèles
print("--- MODÈLES GEMINI DISPONIBLES ---")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)
print("----------------------------------")