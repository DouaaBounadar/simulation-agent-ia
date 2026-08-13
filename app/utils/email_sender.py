import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv  # Permet de lire le fichier .env

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