from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID

class DevisCreate(BaseModel):
    devis_id: str  # Ex: "DEV-2026-001"
    prospect_id: UUID
    produit_id: int
    caracteristiques_choisies: Optional[Dict[str, Any]] = None
    duree: str  # Ex: "7 jours", "1 mois"
    quantite: int = 1
    
    prix_unitaire: float
    prix_total: float
    tva: float = 20.0
    frais_livraison: Optional[float] = 0.0
    montant_caution: Optional[float] = 0.0
    prix_total_ttc: float
    
    status: Optional[str] = "En attente"

class DevisResponse(DevisCreate):
    pdf_path: Optional[str] = None
    date_creation: datetime

    class Config:
        from_attributes = True