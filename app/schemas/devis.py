from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class DevisCreate(BaseModel):
    devis_id: str  
    prospect_id: UUID
    produit_id: int
    caracteristiques_choisies: dict[str, Any] | None = None
    duree: str
    quantite: int = 1
    
    prix_unitaire: float
    prix_total: float
    tva: float = 20.0
    frais_livraison: float | None = 0.0
    montant_caution: float | None = 0.0
    prix_total_ttc: float
    
    status: str | None = "En attente"

class DevisResponse(DevisCreate):
    pdf_path: str | None = None
    date_creation: datetime

    class Config:
        from_attributes = True