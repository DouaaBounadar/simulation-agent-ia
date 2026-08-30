from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from app.models.database import SessionLocal, Prospect, TacheCommercial

def executer_relances_automatiques():
    db = SessionLocal()
    maintenant = datetime.now()
    
    print(f"🔄 [{maintenant.strftime('%H:%M:%S')}] Vérification des relances automatiques...")
    
    # On cherche les prospects qualifiés ayant une relance dépassée
    prospects_a_relancer = db.query(Prospect).filter(
        Prospect.status == "Prospect qualifié",
        Prospect.date_relance_suivante <= maintenant
    ).all()
    
    for p in prospects_a_relancer:
        # RELANCE 1 : Après 8h
        if p.nb_relances_effectuees == 0:
            print(f"📧 [RELANCE 1] Envoi email à {p.email} (8h après devis)")
            p.nb_relances_effectuees = 1
            p.date_relance_suivante = maintenant + timedelta(days=3) # Programme Relance 2 dans 3 jours
            
        # RELANCE 2 : Après 3 jours
        elif p.nb_relances_effectuees == 1:
            print(f"📧 [RELANCE 2] Envoi email à {p.email} (3 jours sans réponse)")
            p.nb_relances_effectuees = 2
            p.date_relance_suivante = maintenant + timedelta(days=4) # Programme Relance 3 (Total = 7 jours)
            
        # RELANCE 3 : Après 7 jours
        elif p.nb_relances_effectuees == 2:
            print(f"📧 [RELANCE 3] Envoi email de la dernière chance à {p.email}")
            p.nb_relances_effectuees = 3
            p.date_relance_suivante = maintenant + timedelta(hours=1) # Créera la tâche commercial juste après
            
        # ÉCHEC : Toujours pas de réponse après 3 relances ➔ Tâche pour le commercial !
        elif p.nb_relances_effectuees == 3:
            titre_tache = f"Appeler M. {p.nom} aujourd'hui (Pas de réponse aux 3 relances)"
            
            # Vérifie si la tâche n'existe pas déjà
            tache_existante = db.query(TacheCommercial).filter(
                TacheCommercial.prospect_id == p.prospect_id,
                TacheCommercial.est_faite == 0
            ).first()
            
            if not tache_existante:
                nouvelle_tache = TacheCommercial(
                    prospect_id=p.prospect_id,
                    titre=titre_tache,
                    historique_echanges=f"Relances automatiques épuisées sans réponse. Téléphone : {p.telephone}"
                )
                db.add(nouvelle_tache)
                print(f"🚨 [TÂCHE CRÉÉE] {titre_tache}")
            
            p.date_relance_suivante = None # Stop les relances automatiques
            
    db.commit()
    db.close()

# --- INITIALISATION DU PLANIFICATEUR ---
planificateur = BackgroundScheduler()

# Pour le test, on configure l'exécution toutes les 2 minutes
planificateur.add_job(executer_relances_automatiques, 'interval', minutes=2)

if __name__ == "__main__":
    executer_relances_automatiques()