import sys
import os
from datetime import datetime, timedelta

# Permet au script de trouver votre dossier 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from app.models.database import SessionLocal, Devis, Prospect, RelanceAuto, TacheCommercial,Conversation
from app.utils.email_sender import envoyer_email_relance

def lancer_robot():
    db = SessionLocal()
    maintenant = datetime.now()
    
    print("🤖 Démarrage du Robot de Relance Automatique...")
    
    # 1. On cherche TOUS les devis qui ont le statut "Envoyé"
    devis_en_attente = db.query(Devis).filter(Devis.status == "Envoyé").all()
    
    if not devis_en_attente:
        print("💤 Aucun devis en attente de réponse. Le robot se rendort.")
        
    for devis in devis_en_attente:
        prospect = db.query(Prospect).filter(Prospect.prospect_id == devis.prospect_id).first()
        date_envoi = devis.date_envoi
        
        if not date_envoi:
            continue
            
        temps_ecoule = maintenant - date_envoi
        
        # On compte combien de relances ont DÉJÀ été envoyées pour ce devis
        nb_relances = db.query(RelanceAuto).filter(
            RelanceAuto.devis_id == devis.devis_id,
            RelanceAuto.statut == "Envoyée"
        ).count()

        # --- RELANCE 1 (8 Heures) ---
        if nb_relances == 0 and temps_ecoule >= timedelta(hours=8):
            print(f"📧 [ACTION] Envoi Relance 1 (8h) pour {prospect.nom}")
            
            # 👇 L'EMAIL PART VRAIMENT ICI 👇
            envoyer_email_relance(prospect.email, prospect.nom, 1)
            
            nouvelle_relance = RelanceAuto(devis_id=devis.devis_id, date_planifiee=maintenant, statut="Envoyée", contenu_message="Relance 1 (8h)")
            db.add(nouvelle_relance)
            db.commit()

        # --- RELANCE 2 (3 Jours) ---
        elif nb_relances == 1 and temps_ecoule >= timedelta(days=3):
            print(f"📧 [ACTION] Envoi Relance 2 (3 jours) pour {prospect.nom}")
            
            # 👇 L'EMAIL PART VRAIMENT ICI 👇
            envoyer_email_relance(prospect.email, prospect.nom, 2)
            
            nouvelle_relance = RelanceAuto(devis_id=devis.devis_id, date_planifiee=maintenant, statut="Envoyée", contenu_message="Relance 2 (3j)")
            db.add(nouvelle_relance)
            db.commit()

        # --- RELANCE 3 (7 Jours) ---
        elif nb_relances == 2 and temps_ecoule >= timedelta(days=7):
            print(f"📧 [ACTION] Envoi Relance 3 (7 jours) pour {prospect.nom}. Dernière chance !")
            
            # 👇 L'EMAIL PART VRAIMENT ICI 👇
            envoyer_email_relance(prospect.email, prospect.nom, 3)
            
            nouvelle_relance = RelanceAuto(devis_id=devis.devis_id, date_planifiee=maintenant, statut="Envoyée", contenu_message="Relance 3 (7j)")
            db.add(nouvelle_relance)
            db.commit()

        # --- ABANDON & ALERTE COMMERCIAL (Après 8 jours) ---
        elif nb_relances == 3 and temps_ecoule >= timedelta(days=8):
            print(f"🚨 [ALERTE] Aucune réponse de {prospect.nom} ! Transfert au commercial.")
            
            # On change le statut pour que le robot arrête de le surveiller
            devis.status = "Sans Réponse"
            prospect.status = "À rappeler"
            
            # On crée une tâche EXPLICITE pour le commercial !
            nouvelle_tache = TacheCommercial(
                prospect_id=prospect.prospect_id,
                titre=f"📞 Appeler M/Mme {prospect.nom} d'urgence",
                description=f"Le client n'a pas répondu au devis {devis.devis_id} après 3 relances automatiques.\nTéléphone: {prospect.telephone}\nEmail: {prospect.email}",
                date_echeance=maintenant,
                statut="À faire"
            )
            db.add(nouvelle_tache)
            db.commit()
# ---------------------------------------------------------
    # 🕵️‍♂️ PARTIE 2 : DÉTECTION DES CONVERSATIONS ABANDONNÉES
    # ---------------------------------------------------------
    print("🔍 Vérification des prospects incomplets...")
    
    # On cherche les conversations liées à des prospects toujours "Nouveaux"
    conversations_en_cours = db.query(Conversation).join(Prospect).filter(Prospect.status == "Nouveau").all()
    
    for conv in conversations_en_cours:
        prospect = conv.prospect
        
        # Si la conversation a commencé il y a plus d'une heure...
        if conv.date_debut and (maintenant - conv.date_debut) >= timedelta(hours=1):
            print(f"⚠️ [ABANDON] Le prospect {prospect.nom} a quitté avant le devis.")
            
            # 1. On change son statut pour qu'il apparaisse dans le tableau CRM
            prospect.status = "À rappeler"
            
            # 2. On crée une alerte visible pour le commercial
            nouvelle_tache = TacheCommercial(
                prospect_id=prospect.prospect_id,
                titre=f"⚠️ Prospect incomplet : Appeler {prospect.nom}",
                description=f"Le prospect a abandonné la discussion avant la fin.\nTéléphone : {prospect.telephone or 'Non renseigné'}\nEmail : {prospect.email or 'Non renseigné'}\nAction : Reprendre la qualification manuellement.",
                date_echeance=maintenant,
                statut="À faire"
            )
            db.add(nouvelle_tache)
            db.commit()
    # ---------------------------------------------------------

    print("✅ Fin de l'inspection. À plus tard !")
    db.close()

if __name__ == "__main__":
    lancer_robot()