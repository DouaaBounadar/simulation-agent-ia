from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.database import SessionLocal, Produit, Prospect, Devis
from app.schemas.devis import DevisCreate, DevisResponse
from app.services.pdf_service import generate_devis_pdf

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

    # 3. Préparation et génération du PDF
    devis_dict = devis.model_dump()
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

    # 4. Créer le devis en base
    nouveau_devis = Devis(
        devis_id=devis.devis_id,
        prospect_id=devis.prospect_id,
        produit_id=devis.produit_id,
        caracteristiques_choisies=devis.caracteristiques_choisies,
        duree=devis.duree,
        quantite=devis.quantite,
        prix_unitaire=devis.prix_unitaire,
        prix_total=devis.prix_total,
        tva=devis.tva,
        frais_livraison=devis.frais_livraison,
        montant_caution=devis.montant_caution,
        prix_total_ttc=devis.prix_total_ttc,
        status=devis.status,
        pdf_path=pdf_path
    )

    db.add(nouveau_devis)
    db.commit()
    db.refresh(nouveau_devis)

    return nouveau_devis