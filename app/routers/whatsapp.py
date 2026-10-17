import asyncio
import logging
import mimetypes
import os
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Form, Request, Response
from openai import OpenAI, OpenAIError
from twilio.twiml.messaging_response import MessagingResponse
from sqlalchemy.orm import Session
from app.models.database import SessionLocal, Prospect

# On importe votre Agent existant
from app.routers.chat import discuter_avec_ia, ChatRequest

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])
logger = logging.getLogger(__name__)

MAX_AUDIO_SIZE_BYTES = 25 * 1024 * 1024
AUDIO_EXTENSIONS = {
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".mp4",
    "audio/webm": ".webm",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/amr": ".amr",
    "audio/3gpp": ".3gp",
}


def _openai_client() -> OpenAI:
    return OpenAI(api_key=os.getenv("OPEN_IA_KEY") or os.getenv("OPENAI_API_KEY"))


async def _download_twilio_audio(
    media_url: str,
    content_type: str,
    destination: Path,
) -> None:
    parsed_url = urlparse(media_url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "api.twilio.com"
        or parsed_url.port not in (None, 443)
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.fragment
    ):
        raise ValueError("L'URL du média Twilio n'est pas valide.")

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        raise RuntimeError("TWILIO_ACCOUNT_SID et TWILIO_AUTH_TOKEN doivent être configurés.")

    expected_path_prefix = f"/2010-04-01/Accounts/{account_sid}/Messages/"
    if not parsed_url.path.startswith(expected_path_prefix):
        raise ValueError("L'URL du média ne correspond pas au compte Twilio configuré.")

    if not content_type.lower().startswith("audio/"):
        raise ValueError("Le média Twilio reçu n'est pas un fichier audio.")

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http_client, http_client.stream(
        "GET",
        media_url,
        auth=(account_sid, auth_token),
    ) as response:
        response.raise_for_status()
        total_size = 0
        with destination.open("wb") as audio_file:
            async for chunk in response.aiter_bytes():
                total_size += len(chunk)
                if total_size > MAX_AUDIO_SIZE_BYTES:
                    raise ValueError("Le message vocal dépasse la taille maximale de 25 Mo.")
                audio_file.write(chunk)


def _transcribe_audio(client: OpenAI, audio_path: Path) -> str:
    with audio_path.open("rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
    return transcription.text.strip()


def _generate_speech(client: OpenAI, text: str, audio_path: Path) -> None:
    speech = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text,
        response_format="mp3",
    )
    speech.write_to_file(audio_path)


@router.post("/webhook")
async def whatsapp_webhook(
    request: Request,
    From: str = Form(...),
    Body: str = Form(""),
    NumMedia: int = Form(0),
    MediaUrl0: str | None = Form(None),
    MediaContentType0: str | None = Form(None),
):
    """Réceptionne les messages WhatsApp et les envoie au vrai cerveau (chat.py)."""
    telephone = From.replace("whatsapp:", "").strip()
    message_client = Body.strip()
    is_voice_message = (
        NumMedia > 0
        and MediaContentType0 is not None
        and "audio" in MediaContentType0.lower()
    )
    downloaded_audio_path: Path | None = None

    db: Session = SessionLocal()
    try:
        openai_client: OpenAI | None = None
        if is_voice_message:
            if not MediaUrl0:
                raise ValueError("Le message vocal Twilio ne contient pas d'URL de média.")

            content_type = MediaContentType0 or ""
            suffix = AUDIO_EXTENSIONS.get(
                content_type.split(";", maxsplit=1)[0].lower(),
                mimetypes.guess_extension(content_type.split(";", maxsplit=1)[0]) or ".audio",
            )
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary_file:
                downloaded_audio_path = Path(temporary_file.name)

            await _download_twilio_audio(MediaUrl0, content_type, downloaded_audio_path)
            openai_client = _openai_client()
            message_client = await asyncio.to_thread(
                _transcribe_audio,
                openai_client,
                downloaded_audio_path,
            )
            if not message_client:
                raise ValueError("La transcription du message vocal est vide.")

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
        import time
        start_time = time.time()
        print(f"⏳ Envoi du message '{message_client}' à l'IA...")
        
        requete = ChatRequest(
            prospect_id=str(prospect.prospect_id), 
            message=message_client
        )
        
        reponse_ia = await discuter_avec_ia(requete=requete, db=db)
        
        # 🛠️ Extraction sécurisée
        contenu_brut = reponse_ia.get("reponse_agent", "")
        if isinstance(contenu_brut, list):
            texte_reponse = "\n".join([
                item.get("text", str(item)) if isinstance(item, dict) else str(item) 
                for item in contenu_brut
            ])
        else:
            texte_reponse = str(contenu_brut)

        # Sécurité Anti-Vide
        if not texte_reponse or texte_reponse.strip() == "":
            texte_reponse = "Désolé, je suis là ! Que vouliez-vous me demander ?"
            print("⚠️ L'IA a renvoyé un texte vide, remplacement par la phrase de sécurité.")

        # 3. On renvoie la réponse propre à WhatsApp
        twiml = MessagingResponse()
        message_twilio = twiml.message()
        message_twilio.body(texte_reponse)
        if is_voice_message:
            audio_filename = f"{uuid.uuid4()}.mp3"
            audio_path = Path(__file__).resolve().parents[1] / "static" / audio_filename
            try:
                if openai_client is None:
                    openai_client = _openai_client()
                await asyncio.to_thread(
                    _generate_speech,
                    openai_client,
                    texte_reponse,
                    audio_path,
                )
                message_twilio.media(str(request.url_for("static", path=audio_filename)))
            except (OpenAIError, OSError):
                logger.exception("Impossible de générer la réponse vocale WhatsApp.")
        
        temps_ecoule = round(time.time() - start_time, 2)
        print(f"⏱️ Temps de réponse de l'IA : {temps_ecoule} secondes")
        print(f"📤 XML envoyé à Twilio : \n{twiml}")

        return Response(content=str(twiml), media_type="application/xml")

    except Exception:
        logger.exception("Erreur lors du traitement du webhook WhatsApp.")
        twiml = MessagingResponse()
        twiml.message().body(
            "Désolé, je rencontre une petite surcharge technique. Je reviens vite !"
        )
        return Response(content=str(twiml), media_type="application/xml")

    finally:
        if downloaded_audio_path is not None:
            try:
                downloaded_audio_path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Impossible de supprimer le fichier audio Twilio temporaire.")
        db.close()