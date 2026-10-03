import difflib
import uuid  # Ajouté pour générer le devis_id
import os
from fastapi import APIRouter, Depends
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse
from datetime import datetime, timedelta
import time
from sqlalchemy.orm.attributes import flag_modified
import re

# On importe depuis votre fichier (qui contient get_db et les modèles)
from app.models.database import (
    Conversation,
    Devis,
    Produit,
    Prospect,
    Location, 
    TacheCommercial,
    SessionLocal,
    get_db,
)
from app.services.pdf_service import generate_devis_pdf
# 📁 Placer au TOUT DÉBUT de votre fichier (main.py ou app.py)
from app.utils.email_sender import envoyer_alerte_commercial, envoyer_devis_client, envoyer_notification_directeur

router = APIRouter(
    prefix="/chat",
    tags=["Chat IA"]
)

class ChatRequest(BaseModel):
    prospect_id: str
    message: str


class preparer_devis(BaseModel):
    """Outil FINAL à utiliser UNIQUEMENT quand TOUTES les étapes de qualification sont terminées."""
    nom: str = Field(..., description="Nom et prénom du client")
    email: str = Field(..., description="Adresse email du client")
    telephone_personnel: str = Field(..., description="Numéro de téléphone personnel")
    entreprise: str = Field(default="Non précisé", description="Nom de l'entreprise (laisser 'Non précisé' si usage personnel)")
    telephone_entreprise: str = Field(default="", description="Numéro de l'entreprise (laisser vide si usage personnel)")
    usage: str = Field(..., description="'Personnel' ou 'Entreprise'")
    adresse_complete: str = Field(..., description="Adresse postale complète")
    ville: str = Field(..., description="Ville pour la livraison")
    produit: str = Field(..., description="Le modèle exact validé (ex: Nacelle Ciseaux)")
    dimensions: str = Field(default="Standard", description="Hauteur ou spécificité technique validée (ex: 12m Électrique)")
    quantite: int = Field(..., description="La quantité souhaitée")
    duree: str = Field(..., description="La durée de location")
    montant: float = Field(default=0.0, description="OBLIGATOIREMENT 0.0")
# class transferer_commercial(BaseModel):
#     """Outil à utiliser UNIQUEMENT si le client est très en colère, a un problème technique grave, ou s'il refuse catégoriquement de continuer même après tes explications."""
#     motif: str = Field(..., description="La raison du transfert")
SYSTEM_PROMPT = """
Tu es un agent de qualification d'élite spécialisé dans la location de matériel.
Ton objectif est de guider le client à travers un tunnel de qualification strict en 6 étapes. Tu dois RESPECTER ATTENTIVEMENT CES INSTRUCTIONS à la lettre. 

🛑 RÈGLES DE FLUIDITÉ (TRÈS IMPORTANT) :
- Pose les questions **UNE PAR UNE**. Ne pose jamais 3 ou 4 questions dans le même message pour ne pas braquer le client.
- Si le client ne connaît pas une information (ex: "je ne sais pas encore la quantité" ou "je n'ai pas la durée"), dis-lui que ce n'est pas grave, passe à la question suivante, mais GARDE EN MÉMOIRE que tu devras obligatoirement y revenir à la fin.
- Ne répète JAMAIS la même question en boucle.

🛑 RÈGLE ABSOLUE CONCERNANT LE PRIX (NE JAMAIS DÉROGER) :
- Tu ne dois JAMAIS négocier sur le prix.
- Tu ne dois JAMAIS parler du prix ou donner une estimation.
- Si le client pose une question sur le prix EN MILIEU de conversation (c'est-à-dire qu'il te manque encore des informations à collecter), évite de donner un prix et dis-lui EXACTEMENT ceci : "Pour que l'on puisse vous répondre à ce sujet, je dois juste connaître toutes vos informations, et notre responsable vous contactera le plus tôt possible pour vous parler du prix." (Puis enchaîne poliment avec ta question en cours).
- Si le client pose la question sur le prix À LA FIN de la conversation, tu dois lui dire EXACTEMENT ceci : "Notre responsable vous fera connaître très prochainement le prix via vos coordonnées, merci."

**ÉTAPE 1 : Validation du Produit**
Dès que le client mentionne un produit, utilise l'outil 'consulter_catalogue'. 
- Si le produit n'est pas trouvé, l'outil te fournira la liste des catégories. Affiche EXACTEMENT la phrase d'excuse et la liste des catégories proposées pour que le client puisse copier-coller le nom exact.
- Si le produit existe, passe à l'étape 2.

**ÉTAPE 2 : Qualification Technique (Une par une)**
L'outil catalogue te fournira les caractéristiques.
1. Demande d'abord au client de choisir le **Nom du modèle** (qui indique la hauteur).
2. Ensuite, demande-lui de valider les autres **spécifications** (Énergie, Capacité, etc.) étape par étape.
N'invente aucune caractéristique hors de celles fournies par l'outil.

**ÉTAPE 3 : Logistique & Usage (Une par une)**
Une fois le modèle exact identifié, demande une par une :
1. La quantité souhaitée.
2. La ville (pour la livraison) ET l'adresse personnelle complète.
3. La période de location (durée).
4. S'il s'agit d'un usage personnel ou pour une entreprise.

**ÉTAPE 4 : Informations Personnelles (Une par une)**
Une fois la logistique validée, demande une par une :
1. Nom et prénom.
2. Adresse email.
3. Numéro de téléphone personnel.
4. ⚠️ CONDITION STRICTE : SI (et seulement si) le client a indiqué un usage "Entreprise" à l'étape 3, demande AUSSI le numéro de téléphone de l'entreprise et le nom de l'entreprise.


**ÉTAPE 5 : Récapitulatif et Finalisation (OBLIGATOIRE)**
🛑 BLOCAGE STRICT : Avant de faire le récapitulatif final, tu DOIS vérifier ton historique pour t'assurer que tu possèdes ABSOLUMENT TOUTES les informations des étapes 2, 3 et 4 (y compris l'adresse de livraison exacte).
- S'il manque ne serait-ce qu'une seule information : IL EST STRICTEMENT INTERDIT de faire le récapitulatif ou de générer le devis. Tu DOIS exiger la donnée manquante immédiatement. N'accepte JAMAIS de recevoir une information "plus tard".
- Si le dossier est 100% complet, fais un **récapitulatif clair** et demande : "Est-ce que toutes ces informations sont correctes ?"
- 🛑 RÈGLE D'EXÉCUTION ABSOLUE : Si le client confirme (ex: "oui", "c'est bon"), tu as l'INTERDICTION STRICTE de lui répondre simplement avec du texte. Tu DOIS IMPÉRATIVEMENT ET IMMÉDIATEMENT déclencher l'outil 'preparer_devis' avec un montant de 0.0. Ne dis pas "je prépare le devis", appelle l'outil directement. C'est le résultat de l'outil qui te dictera la phrase de fin.
Si tu constates dans l'historique que le devis a DÉJÀ été généré, ton rôle strict de qualification est terminé.
- Ne relance JAMAIS les questions des étapes 1 à 5.
- Discute NORMALEMENT, naturellement et poliment avec le client.
- S'il te relance (ex: "hello", "je n'ai rien reçu", ou des questions sur le matériel), utilise les informations de l'historique pour lui répondre de manière personnalisée et humaine.
"""


import time
@tool
def consulter_catalogue(nom_produit: str) -> str:
    """Consulte la base de données pour vérifier l'existence d'un produit."""
    debut_outil = time.time()
    db = SessionLocal()
    try:
        tous_les_produits = db.query(Produit).all()
        recherche = nom_produit.lower()

        # 1. On cherche par catégorie (votre logique)
        produits_correspondants = [p for p in tous_les_produits if recherche in p.nom.lower() or recherche in p.categorie.lower()]

        # 2. SI INTROUVABLE : On récupère la liste des catégories pour l'afficher au client !
        if not produits_correspondants:
            # On extrait toutes les catégories uniques de la BDD
            categories_uniques = list(set([p.categorie for p in tous_les_produits if p.categorie]))
            liste_cats = "\n- ".join(categories_uniques)
            
            return f"❌ INTROUVABLE. Dis EXACTEMENT ceci au client : 'Je suis désolé, ce produit ne correspond à aucun produit dans notre catalogue, merci de vérifier le nom du produit. Voici les catégories que nous proposons :\n- {liste_cats}\nLequel souhaitez-vous ?'"

        # 3. SI TROUVÉ : On liste les noms exacts et leurs spécifications
        liste_modeles = []
        for p in produits_correspondants:
            specs = p.caracteristiques.get("specifications", {})
            hauteur = specs.get("hauteur_travail", "-")
            capacite = specs.get("capacite", "-")
            energie = specs.get("energie", "-")
            liste_modeles.append(f"- Modèle : {p.nom} (Hauteur: {hauteur}, Capacité: {capacite}, Énergie: {energie})")

        reponse = (
            "✅ Catégorie trouvée. Voici la liste des modèles exacts :\n" + "\n".join(liste_modeles) +
            "\n\nINSTRUCTION : Demande au client de choisir le modèle exact (qui indique la hauteur) en premier."
        )
        return reponse

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

    llm = ChatOpenAI(
    model="gpt-4o", # Le modèle le plus intelligent et performant d'OpenAI
    api_key=os.getenv("OPEN_IA_KEY"),
    temperature=0.7,
    max_retries=3
)
    outils_disponibles = [consulter_catalogue]
    
    # Si le client n'a pas encore fait de devis, on lui donne l'outil
    if prospect.status not in ["Devis", "Qualifié"]:
        outils_disponibles.append(preparer_devis)
        
    llm_with_tools = llm.bind_tools(outils_disponibles)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="historique"),
        ("human", "{user_message}")
    ])
    
    chain = prompt | llm_with_tools
    
    reponse_ia = await chain.ainvoke({
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
            import json
            import re
            from datetime import datetime
            import random
            
            # 1. Récupération des informations de l'IA (On ignore le montant donné par l'IA)
            nom = args.get("nom", "Non précisé")
            entreprise = args.get("entreprise", "Non précisé") 
            email = args.get("email", "Non précisé")
            telephone = args.get("telephone_personnel", "Non précisé") 
            produit = args.get("produit", "Matériel")
            quantite = int(args.get("quantite", 1))
            dimensions = args.get("dimensions", "Standard")
            duree = str(args.get("duree", "1 jour")).lower().strip()

            # 2. Mise à jour du prospect
            prospect.nom = nom
            prospect.entreprise = entreprise
            prospect.email = email
            prospect.telephone = telephone
            prospect.status = "Qualifié" 
            
            # --- 🔍 RECHERCHE DU PRODUIT EN BDD ---
            produit_db = db.query(Produit).filter(Produit.nom.ilike(f"%{produit}%")).first()
            produit_id = produit_db.produit_id if produit_db else None
            
            # --- 💰 CALCUL AUTOMATIQUE DU PRIX DEPUIS LE JSON ---
           # --- 💰 CALCUL AUTOMATIQUE DU PRIX DEPUIS LE JSON ---
            montant_ht = 0.0
            if produit_db and produit_db.caracteristiques: # 👈 C'est ici !
                try:
                    # SQLAlchemy transforme déjà le JSONB en dictionnaire
                    data_json = produit_db.caracteristiques
                    tarifs = data_json.get("tarifs", {})
                    
                    # Analyse de la durée (ex: trouver "3" dans "3 jours")
                    nombres = re.findall(r'\d+', duree)
                    nb = int(nombres[0]) if nombres else 1
                    
                    # Création de la clé exacte pour chercher dans le dictionnaire
                    cle_tarif = "1_jour"
                    if "jour" in duree:
                        cle_tarif = f"{nb}_jour" if nb == 1 else f"{nb}_jours"
                    elif "semain" in duree:
                        cle_tarif = f"{nb}_semaine" if nb == 1 else f"{nb}_semaines"
                    elif "mois" in duree:
                        cle_tarif = f"{nb}_mois"
                    elif "an" in duree:
                        cle_tarif = f"{nb}_an" if nb == 1 else f"{nb}_ans"
                        
                    # On cherche le prix unitaire dans la base
                    prix_unitaire = float(tarifs.get(cle_tarif, 0.0))
                    
                    # Si la durée n'existe pas dans la base (ex: 4 jours), on calcule (1 jour * 4)
                    if prix_unitaire == 0.0 and "1_jour" in tarifs:
                        if "jour" in duree:
                            prix_unitaire = float(tarifs.get("1_jour")) * nb
                        else:
                            prix_unitaire = float(tarifs.get("1_jour"))
                            
                    # On multiplie par la quantité demandée
                    montant_ht = prix_unitaire * quantite

                except Exception as e:
                    print(f"⚠️ Erreur de calcul du prix : {e}")
                    montant_ht = 0.0
            
            prospect.montant_en_cours = montant_ht
            
            # --- 🛠️ GÉNÉRATION DU NUMÉRO DE DEVIS ---
            numero_devis = f"DEV-{datetime.now().strftime('%y%m%d')}-{random.randint(1000, 9999)}"

            # --- 3. CRÉATION DU DEVIS EN BROUILLON ---
            nouveau_devis = Devis(
                devis_id=numero_devis,
                prospect_id=prospect.prospect_id,
                produit_id=produit_id,
                quantite=quantite,
                caracteristiques_choisies={"dimensions": dimensions},
                duree=duree,
                prix_total=montant_ht,
                prix_total_ttc=round(montant_ht * 1.20, 2),
                status="Brouillon"
            )
            db.add(nouveau_devis)
            db.commit()

            # --- 4. ALERTE UNIQUEMENT AU COMMERCIAL (PAS DE CLIENT) ---
            envoyer_notification_directeur(
                devis_id=numero_devis, 
                nom_client=prospect.nom, 
                montant=montant_ht, 
                email_client=prospect.email, 
                telephone_client=prospect.telephone
            )

            resultat_devis = f"Devis {numero_devis} préparé en brouillon avec succès. Ne mentionne AUCUN PRIX. Dis EXACTEMENT et UNIQUEMENT au client que son dossier a été transmis à l'équipe commerciale pour validation et qu'il recevra son devis par email."
            print(f"📦 [ETAPE 2] Résultat de l'outil Devis : {resultat_devis}")
            print("🧠 [ETAPE 3] Deuxième appel à l'IA en cours (génération de la réponse)...")

            messages_langchain.append(reponse_ia)
            messages_langchain.append(ToolMessage(content=resultat_devis, tool_call_id=tool_call["id"]))

            reponse_finale = await llm_with_tools.ainvoke(messages_langchain)
            texte_final = reponse_finale.content
            
            # --- DÉBUT DE LA CORRECTION ---
            nouvel_historique = list(historique_actuel)
            nouvel_historique.append({"role": "user", "content": requete.message})
            nouvel_historique.append({"role": "agent", "content": texte_final})
            conversation.messages = nouvel_historique
            
            # 🚨 OBLIGATOIRE POUR QUE LA BDD SAUVEGARDE LE JSON :
            flag_modified(conversation, "messages")
            
            # UN SEUL COMMIT À LA TOUTE FIN POUR TOUT SAUVEGARDER D'UN COUP
            db.commit()
            # --- FIN DE LA CORRECTION ---

            # FIN DE L'ACTION
            return {
                "prospect_id": requete.prospect_id,
                "message_client": requete.message,
                "reponse_agent": texte_final
            }

        elif nom_outil == "consulter_catalogue":
            print(f"👉 [ETAPE 1] L'IA utilise le catalogue avec : {args}")
            
            # 1. On interroge la base de données via notre outil
            resultat_catalogue = consulter_catalogue.invoke(args)
            print(f"📦 [ETAPE 2] Résultat de la BDD : {resultat_catalogue}")
            
            # 2. On reconstruit l'ordre exact de la conversation
            messages_complets = [SystemMessage(content=SYSTEM_PROMPT)]
            messages_complets.extend(messages_langchain)
            messages_complets.append(HumanMessage(content=requete.message))
            messages_complets.append(reponse_ia)
            messages_complets.append(ToolMessage(
                content=resultat_catalogue, 
                tool_call_id=tool_call["id"]
            ))
            
            print("🧠 [ETAPE 3] Deuxième appel à l'IA en cours (génération de la réponse)...")
            reponse_finale = await llm_with_tools.ainvoke(messages_complets)
            texte_final = reponse_finale.content
            
            print(f"💬 [ETAPE 4] Texte généré par l'IA : '{texte_final}'")
            
            # 🚨 SÉCURITÉ : Si l'IA renvoie un texte vide, on force une réponse manuelle
            if not texte_final or texte_final.strip() == "[]":
               texte_final = "Pardon, je rencontre un problème technique, je reviens tout de suite."
               print("⚠️ Alerte : Le texte final était vide. Activation de la phrase de secours.")

        # elif nom_outil == "transferer_commercial":
        #     # 1. On met à jour le statut du prospect dans la BDD
        #     prospect.status = "À rappeler (Négociation)"
        #     nouvelle_tache = TacheCommercial(
        #         prospect_id=prospect.prospect_id,
        #         titre="Appel Client : Négociation de prix",
        #         description=args.get('motif', 'Aucun motif précisé'),
        #         date_echeance=datetime.now() + timedelta(hours=2), # À rappeler dans les 2h
        #         statut="À faire"
        #     )
        #     db.add(nouvelle_tache)
        #     # -----------------------------------------------------------
            
        #     prospect.status = "À rappeler (Négociation)"
        #     db.commit()
            
        #     # 2. ✉️ ON DÉCLENCHE L'ALERTE EMAIL !
        #     nom_client = prospect.nom if prospect.nom else "Client Web"
        #     envoyer_alerte_commercial(nom_client, str(prospect.prospect_id), args.get('motif', 'Aucun motif précisé'))
            
        #     # 3. La réponse à afficher au client
        #     texte_final = f"✅ C'est bien noté. J'ai alerté notre équipe commerciale (Motif : {args.get('motif')}). Un expert va vous recontacter très rapidement !"

    else:
        # Si l'IA n'appelle aucun outil (elle dit juste bonjour ou négocie)
        texte_final = reponse_ia.content

    # 5. Sauvegarde dans JSONB
    nouvel_historique = list(historique_actuel)
    nouvel_historique.append({"role": "user", "content": requete.message})
    nouvel_historique.append({"role": "agent", "content": texte_final})
    
    conversation.messages = nouvel_historique
    # Ajoutez cette ligne ici aussi !
    flag_modified(conversation, "messages")
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
    telephone: str
    produit: str
    montant: float
    duree: str
    quantite: int

@router.post("/finaliser_devis")
def finaliser_devis_endpoint(data: DevisFormulaire, db: Session = Depends(get_db)):
    # ==========================================
    # 1. RECONNAISSANCE INTELLIGENTE DU CLIENT
    # ==========================================
    
    # On vérifie si ce numéro de téléphone existe déjà dans la base
    prospect_existant = db.query(Prospect).filter(Prospect.telephone == data.telephone).first()

    if prospect_existant:
        # 🟢 LE CLIENT EXISTE DÉJÀ (C'est un habitué !)
        prospect_existant.nom = data.nom
        prospect_existant.email = data.email
        prospect_existant.entreprise = data.entreprise
        prospect_existant.status = "Devis"
        
        # On force l'utilisation de SON véritable ID historique
        client_id_final = prospect_existant.prospect_id
        
        # On raccroche la conversation en cours à son vrai profil
        conversation = db.query(Conversation).filter(Conversation.prospect_id == data.prospect_id).first()
        if conversation:
            conversation.prospect_id = client_id_final
    else:
        # 🔵 C'EST UN NOUVEAU CLIENT (On garde l'ID généré par Streamlit)
        prospect_actuel = db.query(Prospect).filter(Prospect.prospect_id == data.prospect_id).first()
        if prospect_actuel:
            prospect_actuel.nom = data.nom
            prospect_actuel.email = data.email
            prospect_actuel.telephone = data.telephone
            prospect_actuel.entreprise = data.entreprise
            prospect_actuel.status = "Devis"
            
        client_id_final = data.prospect_id

    # On enregistre les modifications du client dans la base
    db.commit()

    # --- 🚀 NOUVEAUTÉ : RÉCUPÉRATION DU PRIX DANS LE JSON ---
    produit_db = db.query(Produit).filter(Produit.nom == data.produit).first()
    
    vrai_montant = 0.0 
    
    if produit_db and produit_db.caracteristiques:
        carac = produit_db.caracteristiques
        
        # On extrait spécifiquement le bloc des prix
        tarifs = carac.get("tarifs", {})
        
        # On formate la durée de l'IA pour correspondre à votre BDD (ex: "1 semaine" devient "1_semaine")
        duree_recherche = data.duree.replace(" ", "_").lower()
        
        # 1. Si le tarif exact existe dans la BDD (ex: "1_mois", "2_semaines")
        if duree_recherche in tarifs:
            vrai_montant = float(tarifs[duree_recherche])
            
        # 2. Si la durée n'existe pas (ex: "4_semaines", "12_jours")
        elif "1_jour" in tarifs:
            # On récupère LE VRAI PRIX JOURNALIER de cette machine spécifique
            prix_unitaire_jour = float(tarifs["1_jour"])
            
            # On extrait le chiffre du texte (ex: récupère "4" dans "4 semaines")
            nombres = re.findall(r'\d+', data.duree)
            
            if nombres:
                valeur_temps = int(nombres[0])
                
                # Conversion en jours
                if "semaine" in data.duree.lower():
                    jours_totaux = valeur_temps * 7
                elif "mois" in data.duree.lower():
                    jours_totaux = valeur_temps * 30
                elif "an" in data.duree.lower():
                    jours_totaux = valeur_temps * 365
                else:
                    jours_totaux = valeur_temps
                
                # Calcul basé sur votre prix journalier réel
                vrai_montant = prix_unitaire_jour * jours_totaux

    # On applique la quantité demandée
    prix_unitaire = vrai_montant
    vrai_montant = prix_unitaire * data.quantite
    
    # Sécurité pour les logs
    if vrai_montant == 0.0:
        print(f"⚠️ ERREUR PRIX : Impossible de calculer le prix pour '{data.produit}' avec la durée '{data.duree}'.")

    # 2. Créer l'historique du devis (AVEC LE VRAI MONTANT ET LE VRAI CLIENT)
    id_du_devis = f"DEV-{str(uuid.uuid4())[:8].upper()}"
    nouveau_devis = Devis(
        devis_id=id_du_devis,
        prospect_id=client_id_final,  
        produit_id=produit_db.produit_id if produit_db else None,  # 👈 AJOUTÉ
        quantite=data.quantite,                                    # 👈 AJOUTÉ
        prix_total=vrai_montant,  
        prix_total_ttc=round(vrai_montant * 1.20, 2), 
        duree=data.duree,
        status="Brouillon"
    )
    db.add(nouveau_devis)
    
    # 🚨 CORRECTION DU BUG DE MÉMOIRE ICI
    conversation = db.query(Conversation).filter(Conversation.prospect_id == client_id_final).first()
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
        "telephone": data.telephone # 👈 Modifié pour s'afficher sur le PDF !
    }
    
    # Mise à jour des données du PDF
    devis_data = {
        "devis_id": id_du_devis,
        "duree": data.duree,
        "quantite": data.quantite,    
        "prix_unitaire": prix_unitaire, 
        "prix_total": vrai_montant,     
        "tva": round(vrai_montant * 0.20, 2),
        "frais_livraison": 0,
        "montant_caution": 0,
        "prix_total_ttc": round(vrai_montant * 1.20, 2)
    }
    
    chemin_pdf = generate_devis_pdf(devis_data, prospect_data, data.produit)
    print(f"🎉 SUCCESS: Le PDF a été généré via le formulaire ici : {chemin_pdf}")
    # ...

    # 🚨 Appels corrigés avec les bons noms de paramètres positionnels / nommés
    envoyer_notification_directeur(
        id_du_devis, 
        data.nom, 
        devis_data["prix_total_ttc"], 
        data.email, 
        data.telephone
    )
    return {"status": "success", "message": "Devis généré en brouillon et en attente de validation."}
# N'oubliez pas de vérifier que envoyer_devis_client est bien importé en haut du fichier !
# from app.utils.email_sender import envoyer_devis_client

from pydantic import BaseModel

# Modèle pour recevoir le nouveau prix depuis l'interface
class UpdatePrixDevis(BaseModel):
    nouveau_prix_ttc: float = None

@router.post("/commercial/valider_devis/{devis_id}")
def validation_commercial_et_envoi_client(
    devis_id: str, 
    payload: UpdatePrixDevis = None, 
    db: Session = Depends(get_db)
):
    """
    Validation par le commercial avec possibilité de modifier le prix.
    """
    # 1. Chercher le devis
    devis = db.query(Devis).filter(Devis.devis_id == devis_id).first()
    if not devis:
        return {"error": "Devis introuvable"}
    
    # 2. Mise à jour du prix si le commercial l'a modifié
    if payload and payload.nouveau_prix_ttc is not None:
        devis.prix_total_ttc = payload.nouveau_prix_ttc
        devis.prix_total = payload.nouveau_prix_ttc / 1.20 # Mise à jour du HT (TVA 20%)

    # 3. Sauvegarde du statut
    devis.status = "Envoyé"
    db.commit()

    # 4. Envoi de l'email au client
    prospect = db.query(Prospect).filter(Prospect.prospect_id == devis.prospect_id).first()
    
    if prospect and prospect.email:
        try:
            # 🚨 ATTENTION : C'est ici que votre PDF doit être généré avant d'envoyer l'email
            # generer_pdf(devis_id) 

            envoyer_devis_client(
                devis_id=devis.devis_id,
                nom_client=prospect.nom,
                email_client=prospect.email,
                montant_ttc=devis.prix_total_ttc
            )
            return {"message": f"Succès ! Le devis {devis_id} a été envoyé au client."}
        
        except Exception as e:
            # Si le fichier manque, le devis est quand même validé en base, on retourne juste l'erreur d'email
            print(f"Erreur d'envoi d'email : {e}")
            return {"error": f"Devis validé en base, mais erreur d'envoi du mail (Fichier manquant). Détail: {str(e)}"}
            
    return {"error": "Impossible d'envoyer l'email : prospect introuvable."}

    # 3. Récupérer les infos du prospect pour lui envoyer l'email
    prospect = db.query(Prospect).filter(Prospect.prospect_id == devis.prospect_id).first()

    if prospect and prospect.email:
        # 4. 🚀 On envoie le devis PDF au client !
        # Le mail devra contenir le lien vers la route que vous avez trouvée tout à l'heure :
        # "Cliquez ici pour accepter : https://votre-site.com/valider_devis/DEV-12345"
        
        envoyer_devis_client(
            devis_id=devis.devis_id,
            nom_client=prospect.nom,
            email_client=prospect.email,
            montant_ttc=devis.prix_total_ttc
        )
        return {"message": f"Succès ! Le devis {devis_id} a été validé et envoyé au client."}
    else:
        return {"error": "Impossible d'envoyer l'email : prospect introuvable ou email manquant."}
    

@router.get("/valider_devis/{devis_id}", response_class=HTMLResponse)
def valider_devis_par_email(devis_id: str, db: Session = Depends(get_db)):
    # 1. Chercher le devis
    devis = db.query(Devis).filter(Devis.devis_id == devis_id).first()
    if not devis:
        return HTMLResponse(content="<h1>❌ Devis introuvable</h1>", status_code=404)
    
    # 2. Mettre à jour le statut du devis
    devis.status = "Accepté"
    
    # 3. Créer automatiquement la Location correspondant au devis
    # (Sécurité si prix_total_ttc est vide, on prend prix_total)
    montant_final = devis.prix_total_ttc if devis.prix_total_ttc else devis.prix_total
    
    # 👇 NOUVEAU : Conversion de la durée textuelle en vraies dates
    date_start = datetime.now()
    date_end = date_start
    duree_texte = devis.duree.lower() if devis.duree else ""
    
    if "jour" in duree_texte:
        jours = int(''.join(filter(str.isdigit, duree_texte)) or 1)
        date_end = date_start + timedelta(days=jours)
    elif "semaine" in duree_texte:
        semaines = int(''.join(filter(str.isdigit, duree_texte)) or 1)
        date_end = date_start + timedelta(weeks=semaines)
    elif "mois" in duree_texte:
        mois = int(''.join(filter(str.isdigit, duree_texte)) or 1)
        date_end = date_start + timedelta(days=30 * mois) # Approximation
    elif "an" in duree_texte:
        ans = int(''.join(filter(str.isdigit, duree_texte)) or 1)
        date_end = date_start + timedelta(days=365 * ans)

    nouvelle_location = Location(
        devis_id=devis.devis_id,
        date_debut=date_start,  # 👈 AJOUTÉ
        date_fin=date_end,      # 👈 AJOUTÉ
        statut="En cours"
    )
    db.add(nouvelle_location)
    
    # 4. Mettre à jour le prospect
    prospect = db.query(Prospect).filter(Prospect.prospect_id == devis.prospect_id).first()
    if prospect:
        prospect.status = "Client"
        
    db.commit()
    
    # 5. Page HTML de succès élégante pour le client
    html_content = f"""
    <html>
        <head>
            <title>Location Confirmée</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; background-color: #f4f6f9; }}
                .card {{ background: white; padding: 40px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); display: inline-block; }}
                h1 {{ color: #2e7d32; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🎉 Félicitations !</h1>
                <p>Votre location pour le devis <b>{devis_id}</b> a été validée avec succès.</p>
                <p>Nos équipes logistiques vont vous contacter très rapidement pour la livraison.</p>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)