from app.models.database import (
    SessionLocal, 
    Conversation, 
    Devis, 
    Prospect, 
    Location, 
    RelanceAuto, 
    TacheCommercial
)

def vider_base_de_donnees():
    db = SessionLocal()
    try:
        # 1. Suppression des tables "Enfants" (qui dépendent des Devis ou Prospects)
        print("Suppression des Locations...")
        db.query(Location).delete()
        
        print("Suppression des Relances Automatiques...")
        db.query(RelanceAuto).delete()
        
        print("Suppression des Tâches Commerciales...")
        db.query(TacheCommercial).delete()
        
        print("Suppression des Conversations...")
        db.query(Conversation).delete()

        # 2. Suppression des tables "Parents"
        print("Suppression des Devis...")
        db.query(Devis).delete()
        
        print("Suppression des Prospects...")
        db.query(Prospect).delete()

        # 3. Validation des changements
        db.commit()
        print("✅ Base de données réinitialisée avec succès !")
        print("💡 Note : Votre table 'Produit' (le catalogue) a été conservée intacte.")

    except Exception as e:
        db.rollback()
        print(f"❌ Erreur lors de la réinitialisation : {e}")
    finally:
        db.close()

if __name__ == "__main__":
    vider_base_de_donnees()