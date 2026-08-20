import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# 1. CONFIGURATION DE LA CONNEXION POSTGRESQL
# ⚠️ Remplacez ces valeurs par vos vrais identifiants PostgreSQL
DATABASE_URL = "postgresql://postgres:douaa%401234@localhost:5432/location_db"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. DÉFINITION DES TABLES (MODÈLES)

class Prospect(Base):
    __tablename__ = "prospect"

    prospect_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nom = Column(String(255))
    telephone = Column(String(20), unique=False)
    email = Column(String(255))
    entreprise = Column(String(255))
    source = Column(String(50)) # WhatsApp, Email, Form, Chat
    status = Column(String(50)) # Nouveau, Qualifié, Client, Perdu
    date_premiere_contact = Column(DateTime)
    date_creation = Column(DateTime, default=datetime.now)
    # 👇 LES 2 NOUVELLES LIGNES POUR LE CRM 👇
    montant_en_cours = Column(Numeric(10, 2), default=0)
    date_relance = Column(DateTime)
    # 👆 =================================== 👆

    conversations = relationship("Conversation", back_populates="prospect")
    devis = relationship("Devis", back_populates="prospect")


class Conversation(Base):
    __tablename__ = "conversation"

    conversation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prospect_id = Column(UUID(as_uuid=True), ForeignKey("prospect.prospect_id", ondelete="CASCADE"))
    canal = Column(String(50))
    messages = Column(JSONB) 
    caracteristiques_choisies = Column(JSONB)
    status = Column(String(50)) 
    completude = Column(Numeric(3, 0)) 
    date_debut = Column(DateTime, default=datetime.now)
    date_fin = Column(DateTime)

    prospect = relationship("Prospect", back_populates="conversations")




class Produit(Base):
    __tablename__ = "produit"

    produit_id = Column(Integer, primary_key=True, index=True)
    nom = Column(String(255), unique=True)
    categorie = Column(String(100)) 
    caracteristiques = Column(JSONB) 
    stock_disponible = Column(Integer, default=1)
    date_creation = Column(DateTime, default=datetime.now)


class Devis(Base):
    __tablename__ = "devis"

    devis_id = Column(String(20), primary_key=True)
    prospect_id = Column(UUID(as_uuid=True), ForeignKey("prospect.prospect_id", ondelete="CASCADE"))
    produit_id = Column(Integer, ForeignKey("produit.produit_id"))
    
    caracteristiques_choisies = Column(JSONB)
    duree = Column(String(50))
    quantite = Column(Integer)
    
    prix_unitaire = Column(Numeric(10, 2))
    prix_total = Column(Numeric(10, 2))
    tva = Column(Numeric(10, 2))
    frais_livraison = Column(Numeric(10, 2))
    montant_caution = Column(Numeric(10, 2))
    prix_total_ttc = Column(Numeric(10, 2))
    
    pdf_path = Column(String(255))
    status = Column(String(50))
    
    date_creation = Column(DateTime, default=datetime.now)
    date_envoi = Column(DateTime)
    date_limite_acceptation = Column(DateTime)
    date_acceptation = Column(DateTime)
    date_rejet = Column(DateTime)
    motif_rejet = Column(String)

    prospect = relationship("Prospect", back_populates="devis")


# --- NOUVEAUX MODÈLES 360° ---

class RelanceAuto(Base):
    __tablename__ = "relances_automatiques"
    
    relance_id = Column(Integer, primary_key=True, index=True)
    devis_id = Column(String, ForeignKey("devis.devis_id"))
    date_planifiee = Column(DateTime)
    statut = Column(String, default="Planifiée")  # "Planifiée", "Envoyée", "Annulée"
    contenu_message = Column(Text)


class Location(Base):
    __tablename__ = "locations"
    
    location_id = Column(Integer, primary_key=True, index=True)
    devis_id = Column(String, ForeignKey("devis.devis_id"), unique=True)
    date_debut = Column(DateTime)
    date_fin = Column(DateTime)
    statut = Column(String, default="En cours")  # "En cours", "Terminée", "En retard"
# 👇 LA NOUVELLE TABLE POUR LE ROBOT CRM 👇
class TacheCommercial(Base):
    __tablename__ = "tache_commercial"
    
    tache_id = Column(Integer, primary_key=True, index=True)
    prospect_id = Column(UUID(as_uuid=True), ForeignKey("prospect.prospect_id", ondelete="CASCADE"))
    titre = Column(String(255))
    description = Column(Text)
    date_echeance = Column(DateTime)
    statut = Column(String(50), default="À faire")
    
    date_creation = Column(DateTime, default=datetime.now)
# 👆 ===================================== 👆


# 3. INITIALISATION
def init_db():
    Base.metadata.create_all(bind=engine)
    print("✅ Base de données PostgreSQL initialisée avec succès.")
# --- À AJOUTER À LA FIN DU FICHIER ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

if __name__ == "__main__":
    init_db()

