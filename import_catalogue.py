import pandas as pd

from app.models.database import Produit, SessionLocal


def clean_val(val):
    """Convertit les cases vides (NaN) de Pandas en None pour PostgreSQL"""
    if pd.isna(val):
        return None
    return val

def importer_donnees():
    print("📊 Lecture du fichier Excel...")
    
    try:
        df = pd.read_excel('data/Catalogue_location_agent_IA.xlsx')
    except Exception as e:
        print(f"❌ Erreur lors de la lecture du fichier Excel : {e}")
        return

    session = SessionLocal()
    produits_ajoutes = 0
    
    try:
        # 1. Nettoyer la table avant l'importation pour repartir à zéro proprement
        session.query(Produit).delete()
        session.commit()
        print("🧹 Table 'produit' vidée avec succès pour une nouvelle importation.")
        
        for _, row in df.iterrows():
            caracs = {
                "specifications": {
                    "hauteur_travail": clean_val(row['Hauteur travail']),
                    "hauteur_plateforme": clean_val(row['Hauteur plateforme']),
                    "deport": clean_val(row['Déport']),
                    "capacite": clean_val(row['Capacité']),
                    "energie": clean_val(row['Énergie']),
                    "utilisation": clean_val(row['Utilisation'])
                },
                "tarifs": {
                    "1_jour": clean_val(row['1 jour']),
                    "3_jours": clean_val(row['3 jours']),
                    "1_semaine": clean_val(row['1 semaine']),
                    "2_semaines": clean_val(row['2 semaines']),
                    "1_mois": clean_val(row['1 mois']),
                    "6_mois": clean_val(row['6 mois']),
                    "1_an": clean_val(row['1 an'])
                }
            }
            
            # 2. Création d'un nom 100% unique (Catégorie + Modèle)
            categorie_str = str(row['Catégorie']).strip()
            modele_str = str(row['Modèle']).strip()
            nom_unique = f"{categorie_str} - {modele_str}"
            
            nouveau_produit = Produit(
                nom=nom_unique,
                categorie=categorie_str,
                caracteristiques=caracs,
                stock_disponible=3
            )
            session.add(nouveau_produit)
            produits_ajoutes += 1
        
        session.commit()
        print(f"✅ Importation terminée ! {produits_ajoutes} produits ont été ajoutés à la base de données.")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Erreur lors de l'insertion en base de données : {e}")
    finally:
        session.close()

if __name__ == "__main__":
    importer_donnees()