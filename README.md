# Messages vocaux WhatsApp

Le webhook `POST /whatsapp/webhook` accepte les messages vocaux Twilio WhatsApp.
Il télécharge le média auprès de `api.twilio.com`, le transcrit avec Whisper
(`whisper-1`), puis transmet la transcription à l'agent. Pour un message vocal,
la réponse finale est également générée en MP3 avec `tts-1` et envoyée comme
média WhatsApp en plus du texte.

Configurer les variables d'environnement suivantes :

- `OPEN_IA_KEY` (ou `OPENAI_API_KEY`) : clé API OpenAI.
- `TWILIO_ACCOUNT_SID` et `TWILIO_AUTH_TOKEN` : identifiants utilisés pour
  télécharger les médias entrants protégés de Twilio.

L'application sert les réponses audio générées sous `/static/`. L'URL publique
du webhook doit être accessible par Twilio afin qu'il puisse télécharger le MP3.
Les fichiers vocaux entrants temporaires sont supprimés à la fin de chaque
requête ; les MP3 générés restent dans `app/static/`.