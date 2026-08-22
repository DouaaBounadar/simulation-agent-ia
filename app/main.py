from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from app.models.database import init_db
from app.routers import chat, devis, produits, prospects, whatsapp


# ... après la création de app = FastAPI()



load_dotenv() 

# 1. On crée la fonction lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("⏳ Initialisation de la base de données...")
    init_db()  # Crée les tables manquantes automatiquement au démarrage
    print("✅ Base de données prête !")
    yield
    print("🛑 Arrêt du serveur.")

# 2. On l'attache à l'application FastAPI
app = FastAPI(
    title="API - Agent IA Commercial 360°",
    description="API de gestion du catalogue de location et suivi prospect/devis.",
    version="1.0.0",
    lifespan=lifespan  # <-- C'est la ligne magique !
)

# Inclusion des routeurs
app.include_router(produits.router)
app.include_router(prospects.router)
app.include_router(devis.router)
app.include_router(chat.router)
app.include_router(whatsapp.router)

@app.get("/")
def accueil():
    return {"message": "✅ L'API de l'Agent IA est en ligne et opérationnelle !"}
