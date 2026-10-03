import sys
import os
from datetime import datetime, timedelta

# Permet au script de trouver votre dossier 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from app.models.database import SessionLocal, Devis, Prospect, RelanceAuto, TacheCommercial, Conversation
# On importe la vraie fonction d'envoi d'email depuis ton fichier utils
from app.utils.email_sender import envoyer_email_relance 
from apscheduler.schedulers.background import BackgroundScheduler
import time

# ==========================================
# 📩 FONCTION SIMULÉE (WHATSAPP)
# ==========================================
# (Tu l'ajouteras plus tard si tu as une vraie API WhatsApp)

def envoyer_whatsapp_relance(telephone_client: str, nom_client: str, numero_relance: int, type_relance: str):
    """Gère l'envoi des messages WhatsApp (Abandon de conversation ou Relance Devis)."""
    
    if type_relance == "Abandon":
        if numero_relance == 1:
            msg = f"Bonjour {nom_client}, c'est l'assistant Location Pro 👋. On dirait que nous avons été coupés ! Avez-vous quelques minutes pour terminer de préparer votre devis ?"
        elif numero_relance == 2:
            msg = f"{nom_client}, votre dossier est en attente. Souhaitez-vous qu'un commercial vous appelle directement pour finaliser votre besoin ?"
            
    elif type_relance == "Devis":
        if numero_relance == 1:
            msg = f"Bonjour {nom_client} 👋, je vous ai envoyé votre devis par email. L'avez-vous bien reçu ?"
        elif numero_relance == 2:
            msg = f"{nom_client}, petit rappel pour votre devis de location. Vous pouvez me poser vos questions ici ou répondre à l'email ! 🤝"
        elif numero_relance == 3:
            msg = f"Dernière chance {nom_client} ⚠️ ! Sans validation de votre part, nous devrons annuler le devis demain pour libérer le matériel."

    print(f"💬 [WHATSAPP SIMULÉ au {telephone_client}] Message: {msg}")


# ==========================================
# 🤖 ROBOT PRINCIPAL DE RELANCE
# ==========================================

def lancer_robot():
    db = SessionLocal()
    maintenant = datetime.now()
    
    print("\n🤖 Démarrage du Robot de Relance Automatique (MODE TEST)...")
    
    # ---------------------------------------------------------
    # CAS 1 : DEVIS COMPLET (VALIDÉ OU REFUSÉ) -> PROMOTIONS (EMAIL)
    # ---------------------------------------------------------
    devis_termines = db.query(Devis).filter(Devis.status.in_(["Validé", "Refusé"])).all()
    for devis in devis_termines:
        prospect = db.query(Prospect).filter(Prospect.prospect_id == devis.prospect_id).first()
        if not prospect.email or not devis.date_envoi:
            continue
            
        temps_ecoule = maintenant - devis.date_envoi
        nb_promos = db.query(RelanceAuto).filter(RelanceAuto.devis_id == devis.devis_id, RelanceAuto.contenu_message.like("Promo%")).count()

        # Promo 1 : 5 minutes après validation/refus (Test)
        if nb_promos == 0 and temps_ecoule >= timedelta(minutes=5):
            envoyer_email_relance(prospect.email, prospect.nom, 1, "Promo")
            db.add(RelanceAuto(devis_id=devis.devis_id, date_planifiee=maintenant, statut="Envoyée", contenu_message="Promo-1"))
            db.commit()

        # Promo 2 : 10 minutes après validation/refus (Test)
        elif nb_promos == 1 and temps_ecoule >= timedelta(minutes=10):
            envoyer_email_relance(prospect.email, prospect.nom, 2, "Promo")
            db.add(RelanceAuto(devis_id=devis.devis_id, date_planifiee=maintenant, statut="Envoyée", contenu_message="Promo-2"))
            db.commit()


    # ---------------------------------------------------------
    # CAS 3 : DEVIS ENVOYÉ MAIS SANS RÉPONSE -> EMAIL + WHATSAPP
    # ---------------------------------------------------------
    devis_en_attente = db.query(Devis).filter(Devis.status == "Envoyé").all()
    for devis in devis_en_attente:
        prospect = db.query(Prospect).filter(Prospect.prospect_id == devis.prospect_id).first()
        if not devis.date_envoi:
            continue
            
        temps_ecoule = maintenant - devis.date_envoi
        nb_relances_devis = db.query(RelanceAuto).filter(RelanceAuto.devis_id == devis.devis_id, RelanceAuto.contenu_message.like("Devis%")).count()

        # Relance 1 (5 Minutes) : Email + WhatsApp
        if nb_relances_devis == 0 and temps_ecoule >= timedelta(minutes=5):
            if prospect.email: envoyer_email_relance(prospect.email, prospect.nom, 1, "Devis")
            if prospect.telephone: envoyer_whatsapp_relance(prospect.telephone, prospect.nom, 1, "Devis")
            db.add(RelanceAuto(devis_id=devis.devis_id, date_planifiee=maintenant, statut="Envoyée", contenu_message="Devis-1"))
            db.commit()

        # Relance 2 (30 Minutes) : Email + WhatsApp
        elif nb_relances_devis == 1 and temps_ecoule >= timedelta(minutes=30):
            if prospect.email: envoyer_email_relance(prospect.email, prospect.nom, 2, "Devis")
            if prospect.telephone: envoyer_whatsapp_relance(prospect.telephone, prospect.nom, 2, "Devis")
            db.add(RelanceAuto(devis_id=devis.devis_id, date_planifiee=maintenant, statut="Envoyée", contenu_message="Devis-2"))
            db.commit()

        # Relance 3 (45 Minutes) : Email + WhatsApp
        elif nb_relances_devis == 2 and temps_ecoule >= timedelta(minutes=45):
            if prospect.email: envoyer_email_relance(prospect.email, prospect.nom, 3, "Devis")
            if prospect.telephone: envoyer_whatsapp_relance(prospect.telephone, prospect.nom, 3, "Devis")
            db.add(RelanceAuto(devis_id=devis.devis_id, date_planifiee=maintenant, statut="Envoyée", contenu_message="Devis-3"))
            db.commit()

        # Abandon (60 Minutes) -> Tâche Commercial
        elif nb_relances_devis == 3 and temps_ecoule >= timedelta(minutes=60):
            print(f"🚨 [ALERTE] Aucune réponse de {prospect.nom} ! Transfert au commercial.")
            devis.status = "Sans Réponse"
            prospect.status = "À rappeler"
            db.add(TacheCommercial(prospect_id=prospect.prospect_id, titre=f"📞 Appeler M/Mme {prospect.nom} d'urgence", description="Client injoignable après devis.", date_echeance=maintenant, statut="À faire"))
            db.commit()


    # ---------------------------------------------------------
    # CAS 2 : CONVERSATION ABANDONNÉE -> WHATSAPP UNIQUEMENT
    # ---------------------------------------------------------
    conversations_en_cours = db.query(Conversation).join(Prospect).filter(Prospect.status == "Nouveau").all()
    for conv in conversations_en_cours:
        prospect = conv.prospect
        
        # On vérifie si un devis brouillon ou complet existe pour ce prospect, si oui ce n'est pas un abandon de conversation
        devis_existe = db.query(Devis).filter(Devis.prospect_id == prospect.prospect_id).first()
        if devis_existe:
            continue
            
        if conv.date_debut:
            temps_ecoule = maintenant - conv.date_debut
            nb_abandons = db.query(RelanceAuto).filter(RelanceAuto.prospect_id == prospect.prospect_id, RelanceAuto.contenu_message.like("Abandon%")).count()
            
            # Relance WhatsApp Abandon 1 (10 minutes)
            if nb_abandons == 0 and temps_ecoule >= timedelta(minutes=10):
                if prospect.telephone: envoyer_whatsapp_relance(prospect.telephone, prospect.nom, 1, "Abandon")
                db.add(RelanceAuto(prospect_id=prospect.prospect_id, date_planifiee=maintenant, statut="Envoyée", contenu_message="Abandon-1"))
                db.commit()

            # Relance WhatsApp Abandon 2 (20 minutes)
            elif nb_abandons == 1 and temps_ecoule >= timedelta(minutes=20):
                if prospect.telephone: envoyer_whatsapp_relance(prospect.telephone, prospect.nom, 2, "Abandon")
                db.add(RelanceAuto(prospect_id=prospect.prospect_id, date_planifiee=maintenant, statut="Envoyée", contenu_message="Abandon-2"))
                db.commit()

    db.close()

# --- INITIALISATION DU PLANIFICATEUR ---
planificateur = BackgroundScheduler()
planificateur.add_job(lancer_robot, 'interval', minutes=1)

if __name__ == "__main__":
    planificateur.start()
    print("⏰ Planificateur de relances démarré (MODE TEST). Appuyez sur Ctrl+C pour quitter.")
    try:
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        planificateur.shutdown()