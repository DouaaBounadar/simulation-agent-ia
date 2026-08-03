from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uuid

from app.models.database import SessionLocal, Produit, Prospect, Devis
from app.schemas.devis import DevisCreate, DevisResponse
from app.services.pdf_service import generate_devis_pdf
from app.services.pricing import calculate_devis_totals  # 👈 Nouvel import !

router = APIRouter(
    prefix="/devis",
    tags=["Devis"]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("", response_model=DevisResponse, status_code=status.HTTP_201_CREATED)
def creer_devis(devis: DevisCreate, db: Session = Depends(get_db)):
    # 1. Vérifier si le prospect existe
    prospect = db.query(Prospect).filter(Prospect.prospect_id == devis.prospect_id).first()
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect introuvable.")
        
    # 2. Vérifier si le produit existe
    produit = db.query(Produit).filter(Produit.produit_id == devis.produit_id).first()
    if not produit:
        raise HTTPException(status_code=404, detail="Produit introuvable.")

    # 3. Calcul dynamique des tarifs (Logique Métier)
    # Pour l'exemple, supposons un tarif journalier de base de 150€ et une durée de 7 jours
    # (Tu pourras adapter selon tes vrais champs de durée et prix produit)
    calculs = calculate_devis_totals(
        prix_journalier_de_base=150.0, 
        duree_jours=7, 
        quantite=devis.quantite
    )

    # 4. Préparation des données pour le PDF avec les prix calculés
    devis_dict = devis.model_dump()
    devis_dict.update(calculs)  # On réinjecte les calculs automatiques

    prospect_dict = {
        "nom": prospect.nom,
        "email": prospect.email,
        "telephone": prospect.telephone,
        "entreprise": prospect.entreprise
    }

    try:
        pdf_path = generate_devis_pdf(
            devis_data=devis_dict, 
            prospect_data=prospect_dict, 
            produit_nom=produit.nom
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la génération du PDF : {str(e)}")

    # 5. Enregistrement en base avec les montants calculés automatiquement
    nouveau_devis = Devis(
        devis_id=devis.devis_id,
        prospect_id=devis.prospect_id,
        produit_id=devis.produit_id,
        caracteristiques_choisies=devis.caracteristiques_choisies,
        duree=devis.duree,
        quantite=devis.quantite,
        prix_unitaire=calculs["prix_unitaire"],
        prix_total=calculs["prix_total"],
        tva=calculs["tva"],
        frais_livraison=calculs["frais_livraison"],
        montant_caution=calculs["montant_caution"],
        prix_total_ttc=calculs["prix_total_ttc"],
        status=devis.status,
        pdf_path=pdf_path
    )

    db.add(nouveau_devis)
    db.commit()
    db.refresh(nouveau_devis)

    return nouveau_devis