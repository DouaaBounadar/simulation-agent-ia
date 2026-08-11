import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv# Permet de lire le fichier .env

# On charge les variables cachées du fichier .env
load_dotenv()

def envoyer_alerte_commercial(prospect_nom: str, prospect_id: str, motif: str):
    # ⚙️ Récupération sécurisée depuis le .env
    expediteur = os.getenv("EMAIL_SENDER")
    mot_de_passe = os.getenv("EMAIL_PASSWORD")
    destinataire = expediteur # On s'envoie l'email à nous-même pour tester
    
    if not expediteur or not mot_de_passe:
        print("❌ ERREUR : Les identifiants email sont introuvables dans le fichier .env")
        return False
        
    sujet = f"🚨 A RAPPELER : Négociation en cours avec {prospect_nom}"
    
    corps_message = f"""
    Bonjour l'équipe,
    
    L'agent IA a besoin de votre aide pour clôturer une vente.
    
    👤 Client : {prospect_nom} (ID: {prospect_id})
    📝 Motif : {motif}
    
    Merci de le recontacter au plus vite !
    """
    
    msg = MIMEMultipart()
    msg['From'] = expediteur
    msg['To'] = destinataire
    msg['Subject'] = sujet
    msg.attach(MIMEText(corps_message, 'plain'))
    
    try:
        print("⏳ Tentative d'envoi de l'email en cours...")
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(expediteur, mot_de_passe)
        server.send_message(msg)
        server.quit()
        
        print("✅ SUCCESS : L'email a bien été envoyé !")
        return True
    
    except Exception as e:
        print(f"❌ ERREUR d'envoi : {e}")
        return False