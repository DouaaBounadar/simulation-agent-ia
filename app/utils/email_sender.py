import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
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
def envoyer_devis_client(email_client: str, nom_client: str, chemin_pdf: str):
    """Envoie le devis PDF généré au client par email."""
    
    # Récupération sécurisée des identifiants
    email_expediteur = os.getenv("EMAIL_SENDER")
    mot_de_passe = os.getenv("EMAIL_PASSWORD")
    
    if not email_expediteur or not mot_de_passe:
        print("❌ Erreur : Les variables EMAIL_SENDER ou EMAIL_PASSWORD sont introuvables dans le fichier .env")
        return
    
    # Création du message
    msg = MIMEMultipart()
    msg['From'] = email_expediteur
    msg['To'] = email_client
    msg['Subject'] = "Votre devis de location - Location Pro 🏗️"
    
    # Corps du texte
    corps = f"""Bonjour {nom_client.split()[0]},

Suite à notre échange, veuillez trouver ci-joint votre devis de location au format PDF.

Toute l'équipe de Location Pro reste à votre disposition.

Cordialement,
L'Assistant Commercial IA 🤖"""
    
    msg.attach(MIMEText(corps, 'plain'))
    
    # Ajout de la pièce jointe (Le PDF)
    try:
        with open(chemin_pdf, "rb") as f:
            piece_jointe = MIMEApplication(f.read(), _subtype="pdf")
            piece_jointe.add_header(
                'Content-Disposition', 
                'attachment', 
                filename=os.path.basename(chemin_pdf)
            )
            msg.attach(piece_jointe)
            
        # Envoi via le serveur Gmail
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email_expediteur, mot_de_passe)
        server.send_message(msg)
        server.quit()
        print(f"✅ Email envoyé avec succès avec le PDF à {email_client}")
        
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi de l'email : {e}")