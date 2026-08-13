import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.models.database import (
    Devis,
    Location,
    Produit,
    Prospect,
    RelanceAuto,
    SessionLocal,
)
from app.schemas.devis import DevisCreate, DevisResponse
from app.services.pdf_service import generate_devis_pdf
from app.services.pricing import calculate_devis_totals

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
        raise HTTPException(status_code=500, detail=f"Erreur lors de la génération du PDF : {e!s}") from e

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


@router.get("/{devis_id}/accepter", response_class=HTMLResponse)
def accepter_devis_email(devis_id: str, db: Session = Depends(get_db)):
    """Route déclenchée quand le client clique sur 'Accepter' dans l'email."""
    devis = db.query(Devis).filter(Devis.devis_id == devis_id).first()
    
    if not devis:
        return HTMLResponse(content="<h1>❌ Devis introuvable</h1>", status_code=404)
        
    if devis.status == "Accepté":
        return HTMLResponse(content="<h1 style='color: #28a745;'>✅ Ce devis a déjà été accepté !</h1><p>Notre équipe prépare votre livraison.</p>")

    # 1. Mise à jour du Devis
    devis.status = "Accepté"
    devis.date_acceptation = datetime.now(timezone.utc)
    
    # 2. Mise à jour du Prospect (Devient CLIENT)
    prospect = db.query(Prospect).filter(Prospect.prospect_id == devis.prospect_id).first()
    if prospect:
        prospect.status = "CLIENT"
        
    # 3. Création automatique de la Location 
    # (Adapté selon les champs de votre ancien code et de votre modèle)
    date_debut_prevue = datetime.now(timezone.utc) + timedelta(days=1)
    nouvelle_location = Location(
        location_id=f"LOC-{str(uuid.uuid4())[:8].upper()}",  # Nouvel identifiant unique
        devis_id=devis.devis_id,
        prospect_id=devis.prospect_id,
        produit_id=devis.produit_id,
        quantite=devis.quantite,
        # Attention: si vos colonnes s'appellent différemment dans database.py, ajustez ces lignes :
        date_debut_location=date_debut_prevue.date(),
        prix_total_ttc=devis.prix_total_ttc,
        status="Prévue"
    )
    db.add(nouvelle_location)

    # 4. Annuler les relances automatiques en cours
    relances_en_attente = db.query(RelanceAuto).filter(
        RelanceAuto.devis_id == devis_id, 
        RelanceAuto.statut == "Planifiée"
    ).all()
    
    for relance in relances_en_attente:
        relance.statut = "Annulée"

    db.commit()
    
    # 5. Affichage de la page de succès pour le client
    return HTMLResponse(content=f"""
    <html>
        <body style="text-align: center; font-family: Arial; padding: 50px; background-color: #f8f9fa;">
            <div style="background-color: white; padding: 40px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); display: inline-block;">
                <h1 style="color: #28a745;">🎉 Félicitations !</h1>
                <h2>Votre location a bien été confirmée.</h2>
                <p>Le devis <strong>{devis_id}</strong> est officiellement validé.</p>
                <p>Notre équipe va vous contacter très rapidement pour organiser la livraison.</p>
            </div>
        </body>
    </html>
    """)


@router.get("/{devis_id}/refuser", response_class=HTMLResponse)
def refuser_devis_email(devis_id: str, db: Session = Depends(get_db)):
    """Route déclenchée quand le client clique sur 'Refuser' dans l'email."""
    devis = db.query(Devis).filter(Devis.devis_id == devis_id).first()
    
    if not devis:
        return HTMLResponse(content="<h1>❌ Devis introuvable</h1>", status_code=404)
        
    if devis.status == "Rejeté":
        return HTMLResponse(content="<h1 style='color: #dc3545;'>❌ Ce devis est déjà marqué comme refusé.</h1>")

    # 1. Mise à jour du Devis
    devis.status = "Rejeté"
    devis.date_rejet = datetime.now(timezone.utc)
    
    # 2. Mise à jour du Prospect
    prospect = db.query(Prospect).filter(Prospect.prospect_id == devis.prospect_id).first()
    if prospect:
        prospect.status = "Prospect rejeté"
        
    # 3. Annuler les relances automatiques en cours
    relances_en_attente = db.query(RelanceAuto).filter(
        RelanceAuto.devis_id == devis_id, 
        RelanceAuto.statut == "Planifiée"
    ).all()
    
    for relance in relances_en_attente:
        relance.statut = "Annulée"
        
    db.commit()
    
    # 4. Affichage de la page d'annulation
    return HTMLResponse(content=f"""
    <html>
        <body style="text-align: center; font-family: Arial; padding: 50px; background-color: #f8f9fa;">
            <div style="background-color: white; padding: 40px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); display: inline-block;">
                <h1 style="color: #dc3545;">Devis Refusé</h1>
                <p>Le devis <strong>{devis_id}</strong> a été annulé.</p>
                <p>Merci pour votre intérêt. N'hésitez pas à nous recontacter pour un futur besoin.</p>
            </div>
        </body>
    </html>
    """)