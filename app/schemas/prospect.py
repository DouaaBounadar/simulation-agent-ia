from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from uuid import UUID

# Schéma pour la création d'un prospect (données envoyées par l'agent IA)
class ProspectCreate(BaseModel):
    nom: Optional[str] = None
    email: Optional[EmailStr] = None
    telephone: str  # Champ requis car unique dans votre BDD
    entreprise: Optional[str] = None
    source: Optional[str] = "Chat"  # Ex: WhatsApp, Email, Form, Chat
    status: Optional[str] = "Nouveau"  # Ex: Nouveau, Qualifié, Client, Perdu

# Schéma pour la réponse HTTP de l'API
class ProspectResponse(ProspectCreate):
    prospect_id: UUID
    date_premiere_contact: Optional[datetime] = None
    date_creation: datetime

    class Config:
        from_attributes = True