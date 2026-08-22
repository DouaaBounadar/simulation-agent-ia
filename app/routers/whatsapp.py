import os
import uuid
from fastapi import APIRouter, Form, Response
from twilio.twiml.messaging_response import MessagingResponse
from sqlalchemy.orm import Session
from app.models.database import SessionLocal, Prospect

# On importe votre Agent existant
from app.routers.chat import discuter_avec_ia, ChatRequest

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

@router.post("/webhook")
async def whatsapp_webhook(From: str = Form(...), Body: str = Form(...)):
    """Réceptionne les messages WhatsApp et les envoie au vrai cerveau (chat.py)."""
    telephone = From.replace("whatsapp:", "").strip()
    message_client = Body.strip()

    db: Session = SessionLocal()
    try:
        # 1. On cherche le client
        prospect = db.query(Prospect).filter(Prospect.telephone == telephone).first()
        
        if not prospect:
            prospect_id_genere = str(uuid.uuid4())
            prospect = Prospect(
                prospect_id=prospect_id_genere,
                nom="Client WhatsApp",
                telephone=telephone,
                email="non_renseigne@email.com",
                status="Nouveau"
            )
            db.add(prospect)
            db.commit()
            db.refresh(prospect)

        # 2. 🧠 ON BRANCHE VOTRE AGENT IA
        requete = ChatRequest(
            prospect_id=str(prospect.prospect_id), 
            message=message_client
        )
        
        reponse_ia = await discuter_avec_ia(requete=requete, db=db)
        
        # 🛠️ LA CORRECTION EST ICI : On force le format Texte pour Twilio
        contenu_brut = reponse_ia["reponse_agent"]
        if isinstance(contenu_brut, list):
            texte_reponse = "\n".join([
                item.get("text", str(item)) if isinstance(item, dict) else str(item) 
                for item in contenu_brut
            ])
        else:
            texte_reponse = str(contenu_brut)

        # 3. On renvoie la réponse propre à WhatsApp
        twiml = MessagingResponse()
        twiml.message(texte_reponse)

        return Response(content=str(twiml), media_type="application/xml")

    except Exception as e:
        print(f"❌ Erreur Webhook WhatsApp : {e}")
        twiml = MessagingResponse()
        twiml.message("Désolé, je rencontre une petite surcharge technique. Je reviens vite !")
        return Response(content=str(twiml), media_type="application/xml")

    finally:
        db.close()