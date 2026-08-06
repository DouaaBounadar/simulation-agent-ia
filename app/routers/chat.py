from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import uuid # Ajouté pour générer le devis_id

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

# On importe depuis votre fichier (qui contient get_db et les modèles)
from app.models.database import get_db, Conversation, Prospect, Devis

router = APIRouter(
    prefix="/chat",
    tags=["Chat IA"]
)

class ChatRequest(BaseModel):
    prospect_id: str
    message: str
class generer_devis(BaseModel):
    """Génère un devis officiel une fois que le client a validé ses besoins."""
    montant: float = Field(..., description="Le prix total estimé en euros pour la location")
    description: str = Field(..., description="Le résumé détaillé du matériel loué et la durée")
    duree: str = Field(..., description="La durée de la location (ex: 2 jours, 1 semaine)")

SYSTEM_PROMPT = """
Tu es un agent commercial d'élite spécialisé dans la location de matériel. 
Ton objectif est de négocier avec le client, valider une offre, puis répondre à ses questions.

RÈGLES DE COMPORTEMENT STRICTES (À SUIVRE À LA LETTRE) :

1. AU PREMIER CONTACT : Tu ne dois JAMAIS utiliser l'outil 'generer_devis'. Tu dois OBLIGATOIREMENT proposer un prix en texte et demander l'accord du client (ex: "Je vous propose 200€, qu'en pensez-vous ?").
2. LA NÉGOCIATION : Si le client refuse, demande son budget et propose un prix plus bas.
3. LE DÉCLENCHEMENT : Utilise l'outil 'generer_devis' SI ET SEULEMENT SI le client donne un accord explicite sur le dernier prix proposé ("oui", "d'accord", "je valide").
4. 🚨 APRÈS LE DEVIS (TRÈS IMPORTANT) : Une fois que l'outil 'generer_devis' a été utilisé avec succès, NE L'UTILISE PLUS JAMAIS pour ce client. Si le client pose ensuite des questions (ex: "quand vais-je le recevoir ?", "merci"), réponds-lui NATURELLEMENT avec du texte, sans appeler d'outil. (Les devis sont généralement envoyés par email sous 15 minutes).

RÈGLES DE L'OUTIL 'generer_devis' :
- montant : Le prix exact validé par le client.
- description : Résumé du matériel.
- duree : Durée convenue.
"""
@router.post("/")
async def discuter_avec_ia(requete: ChatRequest, db: Session = Depends(get_db)):
    # 1. Vérification du prospect (utilisation de prospect_id)
    prospect = db.query(Prospect).filter(Prospect.prospect_id == requete.prospect_id).first()
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect introuvable")

    # 2. Récupération ou création de la conversation
    conversation = db.query(Conversation).filter(Conversation.prospect_id == requete.prospect_id).first()
    if not conversation:
        conversation = Conversation(
            prospect_id=requete.prospect_id, 
            messages=[] # On utilise 'messages' comme défini dans votre DB
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    # Si 'messages' est None (nouvelle ligne), on le force en liste vide
    historique_actuel = conversation.messages or []

    # 3. Préparation de la mémoire LangChain
    messages_langchain = []
    for msg in historique_actuel:
        if msg["role"] == "user":
            messages_langchain.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "agent":
            messages_langchain.append(AIMessage(content=msg["content"]))

    llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0.7)
    
    llm_with_tools = llm.bind_tools([generer_devis])
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="historique"),
        ("human", "{user_message}")
    ])
    
    chain = prompt | llm_with_tools
    
    reponse_ia = chain.invoke({
        "historique": messages_langchain,
        "user_message": requete.message
    })

    texte_final = reponse_ia.content

    # 4. Exécution de l'outil si déclenché
    if reponse_ia.tool_calls:
        tool_call = reponse_ia.tool_calls[0]
        args = tool_call["args"]
        
        nouveau_devis = Devis(
            devis_id=f"DEV-{str(uuid.uuid4())[:8].upper()}", # Génération d'un ID unique
            prospect_id=prospect.prospect_id,
            prix_total=args["montant"],
            duree=args["duree"],
            status="Généré"
        )
        db.add(nouveau_devis)
        prospect.status = "Devis" # Mise à jour du statut
        
        texte_final = f"✅ Excellente nouvelle ! Je viens de générer votre devis d'un montant de {args['montant']}€ pour : {args['description']} (Durée: {args['duree']}). Notre équipe va vous l'envoyer par email."

    # 5. Sauvegarde dans JSONB
    nouvel_historique = list(historique_actuel)
    nouvel_historique.append({"role": "user", "content": requete.message})
    nouvel_historique.append({"role": "agent", "content": texte_final})
    
    conversation.messages = nouvel_historique
    db.commit()
    
    return {
        "prospect_id": requete.prospect_id,
        "message_client": requete.message,
        "reponse_agent": texte_final
    }