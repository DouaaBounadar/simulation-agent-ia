import difflib
import uuid  # Ajouté pour générer le devis_id
import os
from decimal import Decimal
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


class ProduitCommande(BaseModel):
    nom: str = Field(..., description="Nom exact du modèle tel qu'affiché dans le catalogue")
    quantite: int = Field(..., ge=1, description="Nombre d'unités de ce modèle")
    prix_unitaire: float = Field(..., gt=0, description="Prix catalogue pour un jour et une unité")
    dimensions: str = Field(default="Standard", description="Hauteur ou spécificité validée")


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
    produits: list[ProduitCommande] = Field(..., min_length=1, description="Toutes les lignes du panier")
    duree: str = Field(..., description="Durée de location, par exemple '3 jours' ou '1 semaine'")
    montant: float = Field(..., ge=0, description="Montant global calculé pour toutes les lignes")


def convertir_duree_en_jours(duree: str) -> int:
    """Convertit une durée de location textuelle en nombre de jours facturables."""
    correspondance = re.search(r"(\d+)\s*(jour|semaine|mois|an)", duree.lower())
    if not correspondance:
        raise ValueError(f"Durée non reconnue : {duree}")

    valeur = int(correspondance.group(1))
    unite = correspondance.group(2)
    multiplicateur = {"jour": 1, "semaine": 7, "mois": 30, "an": 365}[unite]
    return valeur * multiplicateur


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
- 🛑 RÈGLE D'EXÉCUTION ABSOLUE : Si le client confirme (ex: "oui", "c'est bon"), tu as l'INTERDICTION STRICTE de lui répondre simplement avec du texte. Tu DOIS IMPÉRATIVEMENT ET IMMÉDIATEMENT déclencher l'outil 'preparer_devis' avec toutes les lignes du panier et le montant global calculé. Ne dis pas "je prépare le devis", appelle l'outil directement. C'est le résultat de l'outil qui te dictera la phrase de fin.
Avant d'utiliser l'outil preparer_devis, tu DOIS impérativement extraire le prix unitaire de chaque produit depuis le catalogue, faire le calcul (Prix unitaire x Quantité x Durée) pour chaque équipement, et fournir le montant global.
Pour preparer_devis, transmets chaque équipement dans le tableau 'produits' avec son nom exact, sa quantité, son prix unitaire journalier catalogue et ses dimensions. Le backend recalcule le montant à partir des tarifs catalogue; ne remplace jamais un tarif introuvable par 0.
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
            caracteristiques = p.caracteristiques or {}
            specs = caracteristiques.get("specifications", {})
            tarifs = caracteristiques.get("tarifs", {})
            hauteur = specs.get("hauteur_travail", "-")
            capacite = specs.get("capacite", "-")
            energie = specs.get("energie", "-")
            prix_journalier = tarifs.get("1_jour")
            tarif_catalogue = (
                f"Prix journalier catalogue: {prix_journalier} €"
                if prix_journalier is not None
                else "Prix journalier indisponible dans le catalogue"
            )
            liste_modeles.append(
                f"- Modèle : {p.nom} (Hauteur: {hauteur}, Capacité: {capacite}, "
                f"Énergie: {energie}; {tarif_catalogue})"
            )

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

    messages_complets = [SystemMessage(content=SYSTEM_PROMPT)]
    messages_complets.extend(messages_langchain)
    messages_complets.append(HumanMessage(content=requete.message))
    
    reponse_ia = await chain.ainvoke({
        "historique": messages_langchain,
        "user_message": requete.message
    })

    # 4. Traiter tous les tours d'outils jusqu'à obtenir une réponse texte.
    nombre_tours_outils = 0
    tentatives_reponse_vide = 0
    while reponse_ia.tool_calls or not reponse_ia.content:
        if not reponse_ia.tool_calls:
            tentatives_reponse_vide += 1
            if tentatives_reponse_vide >= 3:
                break
            reponse_ia = await llm_with_tools.ainvoke(messages_complets)
            continue

        nombre_tours_outils += 1
        if nombre_tours_outils > 8:
            raise RuntimeError("L'IA a dépassé la limite de 8 tours d'appels d'outils.")

        messages_complets.append(reponse_ia)

        for tool_call in reponse_ia.tool_calls:
            nom_outil = tool_call["name"]
            args = tool_call["args"]
            resultat_outil = ""

            if nom_outil == "preparer_devis":
                import random

                nom = args.get("nom", "Non précisé")
                entreprise = args.get("entreprise", "Non précisé")
                email = args.get("email", "Non précisé")
                telephone = args.get("telephone_personnel", "Non précisé")
                duree = str(args.get("duree", "1 jour")).lower().strip()
                panier = args.get("produits", [])

                try:
                    duree_jours = convertir_duree_en_jours(duree)
                    if not panier:
                        raise ValueError("Le panier ne contient aucun produit.")

                    lignes_panier = []
                    montant_ht_decimal = Decimal("0")
                    for ligne in panier:
                        nom_produit = ligne["nom"]
                        quantite_ligne = int(ligne["quantite"])
                        produit_db = db.query(Produit).filter(Produit.nom == nom_produit).first()
                        if not produit_db:
                            raise ValueError(f"Produit absent du catalogue : {nom_produit}")

                        caracteristiques = produit_db.caracteristiques or {}
                        tarif_journalier = (caracteristiques.get("tarifs") or {}).get("1_jour")
                        if tarif_journalier is None or Decimal(str(tarif_journalier)) <= 0:
                            raise ValueError(f"Tarif journalier indisponible pour : {nom_produit}")

                        prix_unitaire_journalier = Decimal(str(tarif_journalier))
                        sous_total = (
                            prix_unitaire_journalier
                            * quantite_ligne
                            * duree_jours
                        )
                        montant_ht_decimal += sous_total
                        lignes_panier.append({
                            "produit_id": produit_db.produit_id,
                            "nom": produit_db.nom,
                            "quantite": quantite_ligne,
                            "prix_unitaire_journalier": float(prix_unitaire_journalier),
                            "duree_jours": duree_jours,
                            "dimensions": ligne.get("dimensions", "Standard"),
                            "sous_total_ht": float(sous_total)
                        })

                    montant_ht = float(montant_ht_decimal.quantize(Decimal("0.01")))
                    total_quantite = sum(ligne["quantite"] for ligne in lignes_panier)
                    prix_unitaire_moyen = montant_ht_decimal / (total_quantite * duree_jours)
                    montant_ttc = float((montant_ht_decimal * Decimal("1.20")).quantize(Decimal("0.01")))
                    premier_produit_id = lignes_panier[0]["produit_id"] if len(lignes_panier) == 1 else None

                    prospect.nom = nom
                    prospect.entreprise = entreprise
                    prospect.email = email
                    prospect.telephone = telephone
                    prospect.status = "Qualifié"
                    prospect.montant_en_cours = montant_ht

                    numero_devis = f"DEV-{datetime.now().strftime('%y%m%d')}-{random.randint(1000, 9999)}"
                    nouveau_devis = Devis(
                        devis_id=numero_devis,
                        prospect_id=prospect.prospect_id,
                        produit_id=premier_produit_id,
                        quantite=total_quantite,
                        caracteristiques_choisies={"produits": lignes_panier},
                        duree=duree,
                        prix_unitaire=float(prix_unitaire_moyen.quantize(Decimal("0.01"))),
                        prix_total=montant_ht,
                        prix_total_ttc=montant_ttc,
                        status="Brouillon"
                    )
                    db.add(nouveau_devis)
                    db.commit()
                    envoyer_notification_directeur(
                        devis_id=numero_devis,
                        nom_client=prospect.nom,
                        montant=montant_ht,
                        email_client=prospect.email,
                        telephone_client=prospect.telephone
                    )
                    resultat_outil = (
                        f"Devis {numero_devis} préparé en brouillon avec un total HT de {montant_ht:.2f} €. "
                        "Ne mentionne aucun prix au client. Dis EXACTEMENT et UNIQUEMENT que son dossier a "
                        "été transmis à l'équipe commerciale pour validation et qu'il recevra son devis par email."
                    )
                    print(f"📦 Résultat de l'outil Devis : {resultat_outil}")
                except (KeyError, TypeError, ValueError, ArithmeticError) as e:
                    db.rollback()
                    resultat_outil = (
                        f"Devis non créé : {e}. Demande les informations manquantes ou utilise les noms "
                        "exacts et les tarifs journaliers fournis par consulter_catalogue."
                    )

            elif nom_outil == "consulter_catalogue":
                print(f"👉 L'IA utilise le catalogue avec : {args}")
                resultat_outil = consulter_catalogue.invoke(args)
                print(f"📦 Résultat de la recherche catalogue : {resultat_outil}")

            else:
                resultat_outil = f"Erreur : outil inconnu '{nom_outil}'."

            # Chaque appel doit recevoir exactement une réponse associée à son ID.
            messages_complets.append(ToolMessage(
                content=str(resultat_outil),
                tool_call_id=tool_call["id"]
            ))

        print("🧠 Tous les outils de ce tour sont traités; nouvel appel au modèle...")
        reponse_ia = await llm_with_tools.ainvoke(messages_complets)

    texte_final = reponse_ia.content
    if not texte_final or (isinstance(texte_final, str) and texte_final.strip() == "[]"):
        texte_final = "Pardon, je rencontre un problème technique, je reviens tout de suite."
        print("⚠️ Alerte : aucune réponse texte valide après le traitement des outils.")

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