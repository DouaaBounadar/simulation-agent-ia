from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from app.models.database import SessionLocal, Produit, Prospect, Devis
from app.schemas.prospect import ProspectCreate, ProspectResponse
from app.schemas.devis import DevisCreate, DevisResponse

# 👇 NOUVEAU : Import de notre service PDF
from app.services.pdf_service import generate_devis_pdf

app = FastAPI(
    title="API - Agent IA Commercial 360°",
    description="API de gestion du catalogue de location et suivi prospect/devis.",
    version="1.0.0"
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def accueil():
    return {"message": "✅ L'API de l'Agent IA est en ligne et opérationnelle !"}

# --- ROUTES PRODUITS ---

@app.get("/produits", response_model=List[dict])
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

# --- ROUTES PROSPECTS ---

@app.post("/prospects", response_model=ProspectResponse, status_code=status.HTTP_201_CREATED)
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

@app.get("/prospects", response_model=List[ProspectResponse])
def lister_prospects(db: Session = Depends(get_db)):
    return db.query(Prospect).all()

# --- ROUTES DEVIS ---

@app.post("/devis", response_model=DevisResponse, status_code=status.HTTP_201_CREATED)
def creer_devis(devis: DevisCreate, db: Session = Depends(get_db)):
    # 1. Vérifier si le prospect existe
    prospect = db.query(Prospect).filter(Prospect.prospect_id == devis.prospect_id).first()
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect introuvable.")
        
    # 2. Vérifier si le produit existe
    produit = db.query(Produit).filter(Produit.produit_id == devis.produit_id).first()
    if not produit:
        raise HTTPException(status_code=404, detail="Produit introuvable.")

    # 👇 NOUVEAU : Préparation et génération du PDF
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

    # 3. Créer le devis en base (avec le chemin du PDF ajouté à la fin)
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
        pdf_path=pdf_path  # 👈 ON SAUVEGARDE LE CHEMIN ICI
    )

    db.add(nouveau_devis)
    db.commit()
    db.refresh(nouveau_devis)

    return nouveau_devis