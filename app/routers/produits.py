
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.database import Produit, SessionLocal

router = APIRouter(
    prefix="/produits",
    tags=["Produits"]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("", response_model=list[dict])
def lister_produits(db: Session = Depends(get_db)):
    produits = db.query(Produit).all()
    return [
        {
            "produit_id": p.produit_id,
            "nom": p.nom,
            "categorie": p.categorie,
            "caracteristiques": p.caracteristiques,
            "stock_disponible": p.stock_disponible
        }
        for p in produits
    ]