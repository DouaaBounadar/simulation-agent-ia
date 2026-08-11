from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import uuid # Ajouté pour générer le devis_id
from app.utils.email_sender import envoyer_alerte_commercial

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage , SystemMessage

# On importe depuis votre fichier (qui contient get_db et les modèles)
from app.models.database import get_db, Conversation, Prospect, Devis, SessionLocal, Produit
from langchain_core.tools import tool
import difflib

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

class transferer_commercial(BaseModel):
    """Outil à utiliser pour transférer la conversation à un humain si le client veut négocier le prix ou a un problème."""
    motif: str = Field(..., description="La raison du transfert (ex: budget de 2200€ trop bas, demande de réduction)")

SYSTEM_PROMPT = """
Tu es un agent commercial d'élite spécialisé dans la location de matériel. 
Ton objectif est de renseigner le client sur les prix réels, négocier, valider une offre, puis générer un devis.

RÈGLES DE COMPORTEMENT STRICTES (À SUIVRE À LA LETTRE) :

1. VÉRIFICATION DU PRIX (PREMIER CONTACT) : Tu dois OBLIGATOIREMENT utiliser l'outil 'consulter_catalogue' pour connaître le vrai prix du produit demandé. Tu ne dois JAMAIS inventer un prix ou deviner un tarif.
2. LA PROPOSITION : Une fois le prix récupéré via le catalogue, calcule le total si besoin et propose ce prix au client en texte clair. Demande son accord (ex: "Le tarif est de X€ au total. Qu'en pensez-vous ?"). 
3. 🚨 LA NÉGOCIATION : Si le client trouve le prix trop cher, NE PROPOSE JAMAIS DE RÉDUCTION. Explique-lui que tu ne peux pas baisser les prix. S'il veut négocier, utilise OBLIGATOIREMENT l'outil 'transferer_commercial' pour alerter l'équipe humaine.
4. LE DÉCLENCHEMENT : Utilise l'outil 'generer_devis' SI ET SEULEMENT SI le client donne un accord explicite sur le dernier prix proposé ("oui", "d'accord", "je valide").
5. 🚨 APRÈS LE DEVIS (TRÈS IMPORTANT) : Une fois que l'outil 'generer_devis' a été utilisé avec succès, NE L'UTILISE PLUS JAMAIS pour ce client. Si le client pose ensuite des questions (ex: "quand vais-je le recevoir ?", "merci"), réponds-lui NATURELLEMENT avec du texte, sans appeler d'outil. (Les devis sont généralement envoyés par email sous 15 minutes).

RÈGLES DE L'OUTIL 'generer_devis' :
- montant : Le prix exact validé par le client.
- description : Résumé du matériel.
- duree : Durée convenue.
"""

@tool
def consulter_catalogue(nom_produit: str) -> str:
    """
    Outil obligatoire pour consulter les tarifs d'un produit.
    Recherche de manière intelligente, même si le client fait des fautes ou oublie des tirets.
    """
    db = SessionLocal()
    try:
        # 1. On récupère tous les produits du catalogue
        tous_les_produits = db.query(Produit).all()
        if not tous_les_produits:
            return "Le catalogue est vide."

        # 2. On crée une liste des noms de produits (en minuscules pour simplifier)
        noms_bdd = {p.nom.lower(): p for p in tous_les_produits}

        # 3. On nettoie la recherche (minuscules)
        recherche = nom_produit.lower()

        # 4. RECHERCHE FLOUE : Python cherche ce qui ressemble le plus (même avec des fautes)
        # cutoff=0.3 signifie qu'on accepte une correspondance à 30% (très tolérant)
        resultats_proches = difflib.get_close_matches(recherche, noms_bdd.keys(), n=1, cutoff=0.3)

        if resultats_proches:
            # On a trouvé un gagnant !
            nom_trouve = resultats_proches[0]
            produit_gagnant = noms_bdd[nom_trouve]
            
            tarifs = produit_gagnant.caracteristiques.get("tarifs", {})
            reponse = f"✅ Produit trouvé en base : {produit_gagnant.nom}\n"
            reponse += "Voici la grille tarifaire exacte :\n"
            for duree, prix in tarifs.items():
                reponse += f"- {duree.replace('_', ' ')} : {prix}€\n"
            
            reponse += "\nUtilise ces tarifs pour formuler ta réponse au client."
            return reponse
        else:
            # Si on cherche "tondeuse" et qu'on ne vend que des nacelles
            return f"❌ Désolé, je n'ai rien trouvé qui ressemble à '{nom_produit}'."

    except Exception as e:
        return f"Erreur de recherche : {str(e)}"
    finally:
        db.close()

@router.post("/")
async def discuter_avec_ia(requete: ChatRequest, db: Session = Depends(get_db)):
    # 1. Vérification du prospect : s'il n'existe pas, on le crée automatiquement
    prospect = db.query(Prospect).filter(Prospect.prospect_id == requete.prospect_id).first()
    if not prospect:
        prospect = Prospect(
            prospect_id=requete.prospect_id,
            nom="Client Web Anonyme",
            email="non_renseigne@email.com", # Optionnel, selon vos champs obligatoires
            status="Nouveau"
        )
        db.add(prospect)
        db.commit()
        db.refresh(prospect)

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
    
    llm_with_tools = llm.bind_tools([generer_devis, consulter_catalogue, transferer_commercial])
    
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
        nom_outil = tool_call["name"]  # On regarde quel outil l'IA veut utiliser
        args = tool_call["args"]

        if nom_outil == "generer_devis":
            # --- VOTRE CODE ACTUEL POUR LE DEVIS ---
            nouveau_devis = Devis(
                devis_id=f"DEV-{str(uuid.uuid4())[:8].upper()}", 
                prospect_id=prospect.prospect_id,
                prix_total=args.get("montant", 0), # 🛡️ Le .get() évite les plantages
                duree=args.get("duree", "Non précisée"),
                status="Généré"
            )
            db.add(nouveau_devis)
            prospect.status = "Devis" 
            
            texte_final = f"✅ Excellente nouvelle ! Je viens de générer votre devis d'un montant de {args.get('montant')}€ pour : {args.get('description')} (Durée: {args.get('duree')}). Notre équipe va vous l'envoyer par email."

        elif nom_outil == "consulter_catalogue":
            # --- NOUVEAU CODE POUR LE CATALOGUE ---
            # 1. On interroge la base de données via notre outil
            resultat_catalogue = consulter_catalogue.invoke(args)
            
            # 2. On reconstruit l'ordre exact de la conversation pour le 2ème passage
            messages_complets = [SystemMessage(content=SYSTEM_PROMPT)]
            messages_complets.extend(messages_langchain) # L'historique passé
            messages_complets.append(HumanMessage(content=requete.message)) # La demande actuelle
            messages_complets.append(reponse_ia) # L'intention d'appeler l'outil
            messages_complets.append(ToolMessage(
                content=resultat_catalogue, 
                tool_call_id=tool_call["id"]
            )) # Le retour de la base de données
            
            # 3. On rappelle l'IA (elle va lire le prix et répondre naturellement)
            reponse_finale = llm_with_tools.invoke(messages_complets)
            texte_final = reponse_finale.content

        elif nom_outil == "transferer_commercial":
            # 1. On met à jour le statut du prospect dans la BDD
            prospect.status = "À rappeler (Négociation)"
            db.commit()
            
            # 2. ✉️ ON DÉCLENCHE L'ALERTE EMAIL !
            nom_client = prospect.nom if prospect.nom else "Client Web"
            envoyer_alerte_commercial(nom_client, str(prospect.prospect_id), args.get('motif', 'Aucun motif précisé'))
            
            # 3. La réponse à afficher au client
            texte_final = f"✅ C'est bien noté. J'ai alerté notre équipe commerciale (Motif : {args.get('motif')}). Un expert va vous recontacter très rapidement !"

    else:
        # Si l'IA n'appelle aucun outil (elle dit juste bonjour ou négocie)
        texte_final = reponse_ia.content

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