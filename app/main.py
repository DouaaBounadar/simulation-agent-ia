from fastapi import FastAPI
from app.routers import produits, prospects, devis

app = FastAPI(
    title="API - Agent IA Commercial 360°",
    description="API de gestion du catalogue de location et suivi prospect/devis.",
    version="1.0.0"
)

# Inclusion des routeurs
app.include_router(produits.router)
app.include_router(prospects.router)
app.include_router(devis.router)

@app.get("/")
def accueil():
    return {"message": "✅ L'API de l'Agent IA est en ligne et opérationnelle !"}