import difflib
import uuid  # Ajouté pour générer le devis_id

from fastapi import APIRouter, Depends
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# On importe depuis votre fichier (qui contient get_db et les modèles)
from app.models.database import (
    Conversation,
    Devis,
    Produit,
    Prospect,
    SessionLocal,
    get_db,
)
from app.services.pdf_service import generate_devis_pdf
from app.utils.email_sender import envoyer_alerte_commercial, envoyer_devis_client

router = APIRouter(
    prefix="/chat",
    tags=["Chat IA"]
)

class ChatRequest(BaseModel):
    prospect_id: str
    message: str

class preparer_devis(BaseModel):
    """Prépare les informations du devis une fois que le client a validé le prix, pour déclencher le formulaire."""
    montant: str = Field(..., description="Le prix total en euros (ex: 2400)")
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
4. LE DÉCLENCHEMENT DU DEVIS : Dès que le client accepte le prix proposé (ex: "je valide", "c'est d'accord"), tu DOIS OBLIGATOIREMENT utiliser l'outil 'preparer_devis'. Ne lui demande pas son nom ou son email dans le chat, un formulaire sécurisé va s'ouvrir automatiquement sur son écran.
5. 🚨 APRÈS LE DEVIS (TRÈS IMPORTANT) : Une fois que l'outil 'preparer_devis' a été utilisé, le devis part en validation auprès de notre direction. Si le client pose ensuite des questions (ex: "quand vais-je le recevoir ?"), explique-lui poliment qu'il le recevra par email dès que notre équipe l'aura validé. Ne relance plus d'outil.
6. 🤫 SECRET PROFESSIONNEL : Tu es un humain. Ne mentionne JAMAIS le nom de tes outils internes (comme 'consulter_catalogue', 'transferer_commercial' ou 'generer_devis') au client. Tes actions et tes recherches doivent rester complètement invisibles dans tes réponses.
7. 🏢 PRÉSENTATION GÉNÉRALE : Si le client demande ce que l'entreprise propose ou vend, ne lance AUCUNE recherche dans le catalogue. Réponds naturellement que nous louons du matériel BTP et de manutention (Nacelles, Gerbeurs, Chariots élévateurs, etc.) et demande-lui ce dont il a besoin exactement.

RÈGLES DE L'OUTIL 'preparer_devis' :
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
        return f"Erreur de recherche : {e!s}"
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
    
    outils_disponibles = [consulter_catalogue, transferer_commercial]
    
    # Si le client n'a pas encore fait de devis, on lui donne l'outil
    if prospect.status != "Devis":
        outils_disponibles.append(preparer_devis)
        
    llm_with_tools = llm.bind_tools(outils_disponibles)
    
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

        if nom_outil == "preparer_devis":
            # On récupère les infos validées par l'IA
            montant_ht = args.get("montant", "0")
            nom_produit = args.get("description", "Matériel")
            duree = args.get("duree", "Non précisée")
            
            texte_final = "Parfait ! Pour finaliser votre demande et générer le devis officiel, merci de remplir ce court formulaire : 👇"
            
            # On sauvegarde la réponse dans l'historique
            nouvel_historique = list(historique_actuel)
            nouvel_historique.append({"role": "user", "content": requete.message})
            nouvel_historique.append({"role": "agent", "content": texte_final})
            conversation.messages = nouvel_historique
            db.commit()

            # 🚨 LA MAGIE EST ICI : On renvoie un signal à Streamlit
            return {
                "prospect_id": requete.prospect_id,
                "message_client": requete.message,
                "reponse_agent": texte_final,
                "action": "afficher_formulaire", 
                "donnees_devis": {
                    "montant": float(montant_ht),
                    "produit": nom_produit,
                    "duree": duree
                }
            }

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
class DevisFormulaire(BaseModel):
    prospect_id: str
    nom: str
    email: str
    entreprise: str
    produit: str
    montant: float
    duree: str

@router.post("/finaliser_devis")
def finaliser_devis_endpoint(data: DevisFormulaire, db: Session = Depends(get_db)):
    # 1. Mettre à jour les vraies informations du client
    prospect = db.query(Prospect).filter(Prospect.prospect_id == data.prospect_id).first()
    if prospect:
        prospect.nom = data.nom
        prospect.email = data.email
        prospect.entreprise = data.entreprise
        prospect.status = "Devis"

    # --- 🚀 NOUVEAUTÉ : RÉCUPÉRATION DU PRIX DANS LE JSON ---
    produit_db = db.query(Produit).filter(Produit.nom == data.produit).first()
    
    vrai_montant = 150.0 # Prix par défaut
    
    if produit_db and produit_db.caracteristiques:
        # On ouvre la boîte JSON qui contient toutes les infos de l'Excel
        carac = produit_db.caracteristiques
        
        # On fait correspondre le choix du client avec la colonne de l'Excel
        if data.duree == "1 jour":
            vrai_montant = float(carac.get("1 jour", 150))
        elif data.duree == "3 jours":
            vrai_montant = float(carac.get("3 jours", 450))
        elif data.duree == "1 semaine":
            vrai_montant = float(carac.get("1 semaine", 1000))
        elif data.duree == "2 semaines":
            # On gère l'absence du "s" dans votre fichier Excel
            vrai_montant = float(carac.get("2 semaine", carac.get("2 semaines", 2000)))
        elif data.duree == "1 mois":
            vrai_montant = float(carac.get("1 mois", 4000))
        elif data.duree == "6 mois":
            vrai_montant = float(carac.get("6 mois", 20000))
        elif data.duree == "1 an":
            vrai_montant = float(carac.get("1 an", 40000))
    # --------------------------------------------------------

    # 2. Créer l'historique du devis (AVEC LE VRAI MONTANT)
    id_du_devis = f"DEV-{str(uuid.uuid4())[:8].upper()}"
    nouveau_devis = Devis(
        devis_id=id_du_devis,
        prospect_id=data.prospect_id,
        prix_total=vrai_montant,  
        prix_total_ttc=round(vrai_montant * 1.20, 2), # 👈 AJOUTEZ CETTE LIGNE
        duree=data.duree,
        status="Brouillon"
    )
    db.add(nouveau_devis)
    
    # 🚨 CORRECTION DU BUG DE MÉMOIRE ICI (role: "agent")
    conversation = db.query(Conversation).filter(Conversation.prospect_id == data.prospect_id).first()
    if conversation:
        historique = list(conversation.messages)
        historique.append({
            "role": "agent", 
            "content": f"[NOTE SYSTÈME INTERNE] : Opération réussie. Le client a rempli le formulaire. Le devis a été généré en BROUILLON et soumis au directeur pour validation. L'étape de devis est DÉFINITIVEMENT TERMINÉE. Si le client dit merci, dis-lui 'Je vous en prie, vous recevrez le devis par email après validation'."
        })
        conversation.messages = historique
        
    db.commit()

    # 3. 📄 Générer le PDF physique !
    prospect_data = {
        "nom": data.nom,
        "email": data.email,
        "entreprise": data.entreprise,
        "telephone": "Non précisé"
    }
    
    # Mise à jour des données du PDF
    devis_data = {
        "devis_id": id_du_devis,
        "duree": data.duree,
        "quantite": 1,
        "prix_unitaire": vrai_montant,
        "prix_total": vrai_montant,
        "tva": round(vrai_montant * 0.20, 2),
        "frais_livraison": 0,
        "montant_caution": 0,
        "prix_total_ttc": round(vrai_montant * 1.20, 2)
    }
    
    chemin_pdf = generate_devis_pdf(devis_data, prospect_data, data.produit)
    print(f"🎉 SUCCESS: Le PDF a été généré via le formulaire ici : {chemin_pdf}")
    
    return {"status": "success", "pdf_path": chemin_pdf}