from app.models.database import engine, Base

print("🔄 Suppression des anciennes tables...")
Base.metadata.drop_all(bind=engine)

print("✨ Création des nouvelles tables avec les colonnes CRM...")
Base.metadata.create_all(bind=engine)

print("✅ Base de données mise à jour avec succès !")