from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import uuid # Ajouté pour générer le devis_id
from app.utils.email_sender import envoyer_alerte_commercial
from app.services.pdf_service import generate_devis_pdf

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
    """Génère un devis officiel une fois que le client a validé ses besoins et fourni ses coordonnées."""
    montant: str = Field(..., description="Le prix total en euros (ex: 2400)") # <-- CHANGÉ EN STR
    description: str = Field(..., description="Le résumé détaillé du matériel loué et la durée")
    duree: str = Field(..., description="La durée de la location (ex: 2 jours, 1 semaine)")
    nom_client: str = Field(..., description="Le nom et prénom du client") 
    email_client: str = Field(..., description="L'adresse email du client")
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
4. LE DÉCLENCHEMENT DU DEVIS (PROCÉDURE STRICTE EN 2 ÉTAPES) :
- ÉTAPE 1 (Demande d'infos) : Quand le client accepte le prix (ex: "je valide", "c'est d'accord"), TU NE DOIS PAS utiliser l'outil 'generer_devis'. Tu dois OBLIGATOIREMENT lui répondre avec du texte normal : "Parfait, pour établir votre devis, j'ai besoin de votre nom, prénom et adresse email."
- ÉTAPE 2 (Génération) : Utilise l'outil 'generer_devis' UNIQUEMENT APRÈS que le client t'a donné ses vraies informations dans le chat. N'invente JAMAIS de données de remplissage.
5. 🚨 APRÈS LE DEVIS (TRÈS IMPORTANT) : Une fois que l'outil 'generer_devis' a été utilisé avec succès, NE L'UTILISE PLUS JAMAIS pour ce client. Si le client pose ensuite des questions (ex: "quand vais-je le recevoir ?", "merci"), réponds-lui NATURELLEMENT avec du texte, sans appeler d'outil. (Les devis sont généralement envoyés par email sous 15 minutes).
6. 🤫 SECRET PROFESSIONNEL : Tu es un humain. Ne mentionne JAMAIS le nom de tes outils internes (comme 'consulter_catalogue', 'transferer_commercial' ou 'generer_devis') au client. Tes actions et tes recherches doivent rester complètement invisibles dans tes réponses.
7. 🏢 PRÉSENTATION GÉNÉRALE : Si le client demande ce que l'entreprise propose ou vend, ne lance AUCUNE recherche dans le catalogue. Réponds naturellement que nous louons du matériel BTP et de manutention (Nacelles, Gerbeurs, Chariots élévateurs, etc.) et demande-lui ce dont il a besoin exactement.

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
            # 1. On met à jour la fiche du client dans la base de données avec ses vraies infos !
            nom_client = args.get("nom_client", "Client Inconnu")
            email_client = args.get("email_client", "non_renseigne@email.com")
            
            prospect.nom = nom_client
            prospect.email = email_client
            db.commit() # Sauvegarde des infos client

            # 2. Création de l'ID unique et sauvegarde du devis
            id_du_devis = f"DEV-{str(uuid.uuid4())[:8].upper()}"
            montant_ht = float(args.get("montant", 0))
            nom_produit = args.get("description", "Matériel de location")
            
            nouveau_devis = Devis(
                devis_id=id_du_devis, 
                prospect_id=prospect.prospect_id,
                prix_total=montant_ht,
                duree=args.get("duree", "Non précisée"),
                status="Généré"
            )
            db.add(nouveau_devis)
            prospect.status = "Devis" 
            db.commit() 
            
            # 3. 📄 GÉNÉRATION DU PDF VIA VOTRE SCRIPT
            prospect_data = {
                "nom": nom_client,
                "email": email_client,
                "entreprise": "Non précisée", # On pourra demander l'entreprise plus tard si besoin
                "telephone": "Non précisé"
            }
            
            devis_data = {
                "devis_id": id_du_devis,
                "duree": args.get("duree", "N/A"),
                "quantite": 1,
                "prix_unitaire": montant_ht,
                "prix_total": montant_ht,
                "tva": round(montant_ht * 0.20, 2), # Calcul TVA 20%
                "frais_livraison": 0,
                "montant_caution": 0,
                "prix_total_ttc": round(montant_ht * 1.20, 2)
            }
            
            # Appel de la fonction ReportLab
            chemin_pdf = generate_devis_pdf(devis_data, prospect_data, nom_produit)
            print(f"✅ PDF du devis généré ici : {chemin_pdf}")
            
            # 4. Réponse au client
            texte_final = f"✅ Parfait {nom_client.split()[0]} ! Je viens de générer votre devis d'un montant de {montant_ht}€ HT pour : {nom_produit} (Durée: {args.get('duree')}). Notre équipe va vous l'envoyer à l'adresse {email_client} dans quelques minutes."

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