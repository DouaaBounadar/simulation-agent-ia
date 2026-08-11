import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def envoyer_alerte_commercial(prospect_nom: str, prospect_id: str, motif: str):
    """
    Envoie un email à l'équipe commerciale pour une demande de négociation.
    """
    # ⚙️ Configuration (À remplacer par vos vrais accès plus tard)
    expediteur = "bot@votre-entreprise.com"
    destinataire = "ventes@votre-entreprise.com"
    
    sujet = f"🚨 A RAPPELER : Négociation en cours avec {prospect_nom}"
    
    corps_message = f"""
    Bonjour l'équipe,
    
    L'agent IA a besoin de votre aide pour clôturer une vente. Le client trouve le prix trop cher et souhaite négocier.
    
    👤 Client (ID) : {prospect_id}
    📝 Motif : {motif}
    
    Merci de le recontacter au plus vite pour ne pas perdre la vente !
    
    Cordialement,
    Votre Assistant IA 🤖
    """
    
    # 🛠️ Création de l'email
    msg = MIMEMultipart()
    msg['From'] = expediteur
    msg['To'] = destinataire
    msg['Subject'] = sujet
    msg.attach(MIMEText(corps_message, 'plain'))
    
    try:
        # 🟢 MODE SIMULATION (Pour tester sans bloquer l'application)
        print("="*50)
        print(f"📧 [SIMULATION EMAIL] - Message prêt à partir :")
        print(f"De : {expediteur} | À : {destinataire}")
        print(f"Sujet : {sujet}")
        print("="*50)
        
        # 🔴 MODE RÉEL (À décommenter quand vous aurez un vrai mot de passe d'application Google/Outlook)
        # mot_de_passe = "votre_mot_de_passe_securise"
        # server = smtplib.SMTP('smtp.gmail.com', 587)
        # server.starttls()
        # server.login(expediteur, mot_de_passe)
        # server.send_message(msg)
        # server.quit()
        
        return True
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi de l'email : {e}")
        return False