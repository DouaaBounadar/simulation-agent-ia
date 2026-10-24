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
# 🏗️ Location Pro IA — Assistant Commercial & Gestion de Devis

Système complet d'automatisation des ventes pour la location de matériel lourd (nacelles, chariots, gerbeurs). L'application s'appuie sur un agent conversationnel IA (GPT-4o) qualifiant les demandes sur le Web ou WhatsApp, calcule les tarifs dynamiquement depuis une base de données, puis confie la validation finale à un commercial via un tableau de bord Streamlit avant l'envoi du devis PDF au client.

---

## 🛠️ Stack Technologique

| Composant | Technologies |
|---|---|
| **Backend & API** | Python, FastAPI, Uvicorn, Pydantic, Python-dotenv |
| **Base de données & ORM** | PostgreSQL (UUID, JSONB), SQLAlchemy 2 |
| **Intelligence Artificielle** | OpenAI (GPT-4o), LangChain Core / LangChain OpenAI |
| **WhatsApp & Vocal** | Twilio WhatsApp Webhook, OpenAI Whisper (`whisper-1`), OpenAI TTS (`tts-1`) |
| **Frontend & Dashboard** | Streamlit, Pandas |
| **Génération & Services** | ReportLab (PDF), Gmail SMTP (`smtplib`), APScheduler |

---

## 🚀 Fonctionnalités Principales

1. **Qualification Multicanale par l'IA :** Chat Web Streamlit et Webhook WhatsApp (Texte et Note vocale).
2. **Calcul Automatique des Tarifs :** Extraction des grilles tarifaires dégressives stockées en `JSONB` dans la base PostgreSQL selon la durée demandée.
3. **Confidentialité des Prix :** L'agent IA ne divulgue pas le montant au client durant la conversation ; le devis est créé au statut `Brouillon`.
4. **Validation Express Commerciale (Streamlit) :**
   - Révision des devis en attente.
   - Modification en direct du montant TTC.
   - Génération à la volée du PDF avec ReportLab.
   - Expédition automatique par email avec pièce jointe.
5. **Acceptation Client & Commande :** Liens d'action dans l'email permettant au client de valider le devis, ce qui génère automatiquement la réservation (`Location`).

---

## 📱 Messages Vocaux WhatsApp

Le webhook `POST /whatsapp/webhook` accepte les messages vocaux Twilio WhatsApp.
Il télécharge le média auprès de `api.twilio.com`, le transcrit avec Whisper
(`whisper-1`), puis transmet la transcription à l'agent. Pour un message vocal,
la réponse finale est également générée en MP3 avec `tts-1` et envoyée comme
média WhatsApp en plus du texte.

### Variables d'environnement requises :

- `OPEN_IA_KEY` (ou `OPENAI_API_KEY`) : Clé API OpenAI.
- `TWILIO_ACCOUNT_SID` et `TWILIO_AUTH_TOKEN` : Identifiants utilisés pour télécharger les médias entrants protégés de Twilio.
- `DATABASE_URL` : URL de connexion PostgreSQL.
- `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` : Configuration SMTP pour l'envoi des e-mails.

L'application sert les réponses audio générées sous `/static/`. L'URL publique
du webhook doit être accessible par Twilio afin qu'il puisse télécharger le MP3.
Les fichiers vocaux entrants temporaires sont supprimés à la fin de chaque
requête ; les MP3 générés restent dans `app/static/`.

---

## 📂 Structure du Projet

```text
├── app/
│   ├── main.py                # Point d'entrée de l'API FastAPI
│   ├── models/
│   │   └── database.py        # Modèles SQLAlchemy (Prospect, Devis, Produit, Location)
│   ├── routers/
│   │   ├── chat.py            # Agent IA conversationnel & outil preparer_devis
│   │   ├── whatsapp.py        # Webhook WhatsApp Twilio (Texte + Vocaux Whisper/TTS)
│   │   ├── devis.py           # Routes de validation/acceptation devis
│   │   ├── prospects.py       # API de gestion des prospects
│   │   └── produits.py        # API de consultation du catalogue
│   ├── services/
│   │   └── pdf_service.py     # Génération des devis PDF (ReportLab)
│   ├── static/                # Fichiers audio générés pour WhatsApp (.mp3)
│   └── utils/
│       └── email_sender.py    # Service d'envoi d'emails SMTP
├── frontend/
│   ├── interface.py           # Application Streamlit (Chat Client)
│   └── pages/
│       ├── 1_📊_Dashboard_Admin.py  # Dashboard Directeur & Validation Express
│       └── 2_🤝_CRM_Commercial.py  # Suivi CRM et relances
├── generated_pdfs/            # Dossier de stockage des devis PDF générés
├── import_catalogue.py        # Script d'importation du catalogue Excel vers PostgreSQL
├── robot_relances.py          # Planificateur de relances automatiques
├── requirements.txt           # Dépendances Python
└── README.md
Installation et Lancement
1. Installation des dépendances
Bash
pip install -r requirements.txt
2. Démarrage de l'API Backend (FastAPI)
Bash
uvicorn app.main:app --reload
3. Démarrage du Dashboard Commercial & Chat (Streamlit)
Bash
streamlit run frontend/interface.py