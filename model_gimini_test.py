import google.generativeai as genai
import os

# Assurez-vous que votre clé API est bien configurée ici
genai.configure(api_key="VOTRE_CLE_API_GOOGLE") 

print("Modèles disponibles pour la génération de texte :")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)