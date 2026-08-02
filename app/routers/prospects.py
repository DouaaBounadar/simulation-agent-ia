from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from app.models.database import SessionLocal, Prospect
from app.schemas.prospect import ProspectCreate, ProspectResponse

router = APIRouter(
    prefix="/prospects",
    tags=["Prospects"]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("", response_model=ProspectResponse, status_code=status.HTTP_201_CREATED)
def creer_prospect(prospect: ProspectCreate, db: Session = Depends(get_db)):
    prospect_existant = db.query(Prospect).filter(Prospect.telephone == prospect.telephone).first()
    if prospect_existant:
        raise HTTPException(
            status_code=400, 
            detail="Un prospect avec ce numéro de téléphone existe déjà."
        )
    
    nouveau_prospect = Prospect(
        nom=prospect.nom,
        email=prospect.email,
        telephone=prospect.telephone,
        entreprise=prospect.entreprise,
        source=prospect.source,
        status=prospect.status,
        date_premiere_contact=datetime.now()
    )
    
    db.add(nouveau_prospect)
    db.commit()
    db.refresh(nouveau_prospect)
    
    return nouveau_prospect

@router.get("", response_model=List[ProspectResponse])
def lister_prospects(db: Session = Depends(get_db)):
    return db.query(Prospect).all()