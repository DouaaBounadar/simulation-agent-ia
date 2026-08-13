from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


# Schéma pour la création d'un prospect (données envoyées par l'agent IA)
class ProspectCreate(BaseModel):
    nom: str | None = None
    email: EmailStr | None = None
    telephone: str  # Champ requis car unique dans votre BDD
    entreprise: str | None = None
    source: str | None = "Chat"  # Ex: WhatsApp, Email, Form, Chat
    status: str | None = "Nouveau"  # Ex: Nouveau, Qualifié, Client, Perdu

# Schéma pour la réponse HTTP de l'API
class ProspectResponse(ProspectCreate):
    prospect_id: UUID
    date_premiere_contact: datetime | None = None
    date_creation: datetime

    class Config:
        from_attributes = True