from app.models.database import SessionLocal, Produit

# On ouvre la connexion
db = SessionLocal()

# On compte le nombre de produits dans la table
nombre_produits = db.query(Produit).count()

print("========================================")
if nombre_produits == 0:
    print("🚨 La table Produit est complètement VIDE !")
else:
    print(f"✅ La table contient {nombre_produits} produits.")
print("========================================")

# On ferme la connexion
db.close()