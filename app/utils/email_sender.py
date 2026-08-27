import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv  # Permet de lire le fichier .env

# On charge les variables cachées du fichier .env
load_dotenv()

def envoyer_alerte_commercial(prospect_nom: str, prospect_id: str, motif: str, telephone: str = "Non renseigné", email: str = "Non renseigné"):
    # ⚙️ Récupération sécurisée depuis le .env (gardez vos lignes existantes ici)
    expediteur = os.getenv("EMAIL_SENDER")
    mot_de_passe = os.getenv("EMAIL_PASSWORD")
    destinataire = expediteur
    
    if not expediteur or not mot_de_passe:
        return False
        
    sujet = f"🚨 A RAPPELER : Négociation avec {prospect_nom}"
    
    corps_message = f"""
    Bonjour l'équipe,
    
    L'agent IA a besoin de votre aide pour clôturer une vente.
    
    👤 Client : {prospect_nom}
    📞 Téléphone : {telephone}
    ✉️ Email : {email}
    🆔 ID Système : {prospect_id}
    
    📝 Motif : {motif}
    
    Merci de le recontacter au plus vite !
    """
    # ... (gardez la suite de la fonction intacte pour l'envoi SMTP)
    
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
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

def envoyer_devis_client(email_client: str, nom_client: str, chemin_pdf: str):
    """Envoie le devis par email avec les boutons d'acceptation/refus."""
    email_expediteur = os.getenv("EMAIL_SENDER")
    mot_de_passe = os.getenv("EMAIL_PASSWORD")
    
    if not email_expediteur or not mot_de_passe:
        print("❌ Erreur : Les variables EMAIL_SENDER ou EMAIL_PASSWORD sont introuvables.")
        return False
        
    try:
        # On extrait le numéro du devis depuis le nom du fichier (ex: DEV-1234)
        devis_id = os.path.basename(chemin_pdf).replace('.pdf', '')

        msg = EmailMessage()
        msg['Subject'] = f"Votre devis de location - {devis_id}"
        msg['From'] = email_expediteur
        msg['To'] = email_client
        
        # --- LE NOUVEAU DESIGN HTML ---
        contenu_html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
                <h2 style="color: #1A365D;">Bonjour {nom_client},</h2>
                <p>Suite à notre échange, veuillez trouver ci-joint votre devis <strong>{devis_id}</strong> pour la location de matériel.</p>
                
                <div style="margin: 30px 0; padding: 20px; background-color: #f8f9fa; border-radius: 5px; text-align: center;">
                    <p style="margin-bottom: 20px; font-size: 16px;"><strong>Que souhaitez-vous faire ?</strong></p>
                    
                    <a href="http://127.0.0.1:8000/devis/{devis_id}/accepter" 
                       style="background-color: #28a745; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; margin-right: 15px; display: inline-block;">
                       ✅ J'accepte la location
                    </a>
                    
                    <a href="http://127.0.0.1:8000/devis/{devis_id}/refuser" 
                       style="background-color: #dc3545; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                       ❌ Je refuse le devis
                    </a>
                </div>
                
                <p>Si vous avez des questions, n'hésitez pas à répondre directement à cet email.</p>
                <br>
                <p>Cordialement,<br><strong>L'équipe Location Pro</strong></p>
            </body>
        </html>
        """
        
        msg.set_content("Veuillez activer l'affichage HTML pour lire cet email.")
        msg.add_alternative(contenu_html, subtype='html')

        # Ajout de la pièce jointe
        with open(chemin_pdf, 'rb') as f:
            pdf_data = f.read()
            msg.add_attachment(pdf_data, maintype='application', subtype='pdf', filename=os.path.basename(chemin_pdf))

        # Envoi
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(email_expediteur, mot_de_passe)
            smtp.send_message(msg)
            
        print(f"✅ Email officiel envoyé avec succès à {email_client}")
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi de l'email : {e}")
        return False
def envoyer_notification_directeur(devis_id: str, nom_client: str, montant: float, email_client: str = "Non renseigné", telephone_client: str = "Non renseigné"):
    """Envoie un email au directeur pour le prévenir qu'un devis attend sa validation."""
    email_directeur = os.getenv("EMAIL_SENDER")
    mot_de_passe = os.getenv("EMAIL_PASSWORD")
    
    if not email_directeur or not mot_de_passe:
        return False
        
    msg = EmailMessage()
    msg['Subject'] = f"🔔 Nouveau devis à valider : {devis_id}"
    msg['From'] = email_directeur
    msg['To'] = email_directeur
    
    contenu = f"""
    Bonjour,
    
    Un nouveau devis a été généré par l'agent IA et attend votre validation dans le Tableau de Bord.
    
    - Devis : {devis_id}
    - Client : {nom_client}
    - Email : {email_client}
    - Téléphone : {telephone_client}
    - Montant TTC : {montant} €
    
    Merci de vous connecter à l'interface d'administration pour valider ou refuser ce devis.
    """
    msg.set_content(contenu)
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(email_directeur, mot_de_passe)
            smtp.send_message(msg)
        print(f"✅ Notification envoyée au directeur pour le devis {devis_id}")
        return True
    except Exception as e:
        print(f"❌ Erreur notification directeur : {e}")
        return False
# À AJOUTER DANS app/utils/email_sender.py

def envoyer_email_relance(email_client: str, nom_client: str, numero_relance: int):
    """Envoie un email de relance personnalisé selon le délai."""
    
    if numero_relance == 1:
        sujet = "Votre devis Location Pro vous attend ! ⏳"
        corps = f"Bonjour {nom_client},\n\nNous vous avons fait parvenir votre devis il y a quelques heures. Avez-vous eu le temps d'y jeter un œil ?\nNotre équipe reste à votre disposition pour toute question."
    
    elif numero_relance == 2:
        sujet = "Avez-vous des questions sur votre devis ? 🤝"
        corps = f"Bonjour {nom_client},\n\nNous revenons vers vous concernant votre devis. Si vous avez besoin d'ajuster les quantités ou la durée, n'hésitez pas à nous le dire en répondant simplement à cet email !"
    
    elif numero_relance == 3:
        sujet = "Dernière relance concernant votre projet de location ⚠️"
        corps = f"Bonjour {nom_client},\n\nSans retour de votre part d'ici demain, nous clôturerons votre dossier et remettrons le matériel en disponibilité pour d'autres clients. Contactez-nous vite si votre projet est toujours d'actualité."
    else:
        return # Sécurité

    # ⚠️ Remplacez ceci par votre vrai code d'envoi d'email (SMTP)
    # Exemple si vous utilisez smtplib, ou juste un print pour l'instant :
    print(f"🚀 [EMAIL RÉEL ENVOYÉ] -> À: {email_client} | Sujet: {sujet}")
    # send_mail(email_client, sujet, corps) # Votre vraie fonction d'envoi
def envoyer_email_marketing(email_client: str, sujet: str, corps: str):
    """Envoie la newsletter générée par l'IA."""
    email_expediteur = os.getenv("EMAIL_SENDER")
    mot_de_passe = os.getenv("EMAIL_PASSWORD")
    
    if not email_expediteur or not mot_de_passe:
        print("❌ Erreur : Identifiants email introuvables.")
        return False
        
    msg = EmailMessage()
    msg['Subject'] = sujet
    msg['From'] = email_expediteur
    msg['To'] = email_client
    msg.set_content(corps)
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(email_expediteur, mot_de_passe)
            smtp.send_message(msg)
        print(f"✅ Newsletter envoyée avec succès à {email_client}")
        return True
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi de la newsletter : {e}")
        return False