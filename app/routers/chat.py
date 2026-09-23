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

# On importe depuis votre fichier (qui contient get_db et les modèles)
from app.models.database import (
    Conversation,
    Devis,
    Produit,
    Prospect,
    Location,
    RelanceAuto, 
    TacheCommercial,
    SessionLocal,
    get_db,
)
from app.services.pdf_service import generate_devis_pdf
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
class transferer_commercial(BaseModel):
    """Outil à utiliser UNIQUEMENT si le client est très en colère, a un problème technique grave, ou s'il refuse catégoriquement de continuer même après tes explications."""
    motif: str = Field(..., description="La raison du transfert")
SYSTEM_PROMPT = """
Tu es un agent de qualification d'élite spécialisé dans la location de matériel.
Ton objectif est de guider le client à travers un tunnel de qualification strict en 6 étapes. Tu dois RESPECTER ATTENTIVEMENT CES INSTRUCTIONS à la lettre. Pose les questions étape par étape (1 ou 2 à la fois maximum) pour ne pas braquer le client.

🛑 RÈGLE ABSOLUE CONCERNANT LE PRIX (NE JAMAIS DÉROGER) :
- Tu ne dois JAMAIS négocier sur le prix.
- Tu ne dois JAMAIS parler du prix ou donner une estimation.
- Si le client pose une question sur le prix EN MILIEU de conversation (c'est-à-dire qu'il te manque encore des informations à collecter), évite de donner un prix et dis-lui EXACTEMENT ceci : "Pour que l'on puisse vous répondre à ce sujet, je dois juste connaître toutes vos informations, et notre responsable vous contactera le plus tôt possible pour vous parler du prix." (Puis enchaîne poliment avec ta question en cours).
- Si le client pose la question sur le prix À LA FIN de la conversation (une fois que toutes les informations du formulaire ont été collectées et validées), tu dois lui dire EXACTEMENT ceci : "Notre responsable vous fera connaître très prochainement le prix via vos coordonnées, merci."

**ÉTAPE 1 : Validation du Produit**
Dès que le client mentionne un produit, utilise l'outil 'consulter_catalogue'. 
- Si l'outil indique que le produit n'existe pas, réponds EXACTEMENT : "Je suis désolé, ce produit ne correspond à aucun produit dans notre catalogue, merci de vérifier le nom du produit."
- Si le produit existe (ex: Nacelle Ciseaux), passe à l'étape 2.

**ÉTAPE 2 : Qualification Technique (Strictement basée sur la BDD)**
L'outil catalogue te fournira les caractéristiques disponibles pour la catégorie demandée (Hauteur, Énergie, Capacité, Utilisation, etc.).
Pose des questions pour affiner chaque critère manquant jusqu'à identifier le modèle EXACT. N'invente aucune caractéristique hors de celles fournies par l'outil.

**ÉTAPE 3 : Logistique & Usage**
Une fois le modèle exact identifié, demande :
1. La quantité souhaitée.
2. La ville (pour la livraison) ET l'adresse personnelle complète.
3. La période de location (durée).
4. S'il s'agit d'un usage personnel ou pour une entreprise.
⚠️ RÈGLE DE RÉPONSE INCOMPLÈTE : Si le client répond à certaines questions mais en oublie d'autres (ex: il donne la quantité mais oublie la ville), TU DOIS le relancer spécifiquement sur l'information manquante avant de passer à l'étape 4.

**ÉTAPE 4 : Informations Personnelles (Conditionnelles)**
Une fois la logistique validée, demande :
1. Nom et prénom.
2. Adresse email.
3. Numéro de téléphone personnel.
4. ⚠️ CONDITION STRICTE : SI (et seulement si) le client a indiqué un usage "Entreprise" à l'étape 3, demande AUSSI le numéro de téléphone de l'entreprise et le nom de l'entreprise. Si c'est un usage personnel, ne demande pas ce numéro.

**ÉTAPE 5 : Finalisation**
Dès que TOUTES ces informations sont récoltées sans exception (ne rate aucune information), déclenche l'outil 'preparer_devis' avec un montant OBLIGATOIRE de 0.0.

**ÉTAPE 6 : Relation Client (Post-Devis)**
Si tu constates dans l'historique que le devis a DÉJÀ été généré (les informations ont été collectées), ton rôle strict de qualification est terminé.
- Ne relance JAMAIS les questions des étapes 1 à 5.
- Discute NORMALEMENT, naturellement et poliment avec le client.
- S'il te relance (ex: "hello", "je n'ai rien reçu", ou des questions sur le matériel), utilise les informations de l'historique pour lui répondre de manière personnalisée et humaine, comme le ferait un conseiller commercial qui connaît déjà son dossier.
"""


import time

@tool
def consulter_catalogue(nom_produit: str) -> str:
    """Consulte la base de données pour vérifier l'existence d'un produit et lister ses caractéristiques variables."""
    debut_outil = time.time()
    db = SessionLocal()
    try:
        tous_les_produits = db.query(Produit).all()
        recherche = nom_produit.lower()

        # Filtrer les produits qui contiennent le mot clé
        produits_correspondants = [p for p in tous_les_produits if recherche in p.nom.lower() or recherche in p.categorie.lower()]

        if not produits_correspondants:
            return "❌ INTROUVABLE. Dis au client : 'Je suis désolé, ce produit ne correspond à aucun produit dans notre catalogue, merci de vérifier le nom du produit.'"

        # Regrouper les caractéristiques pour que l'IA sache quoi demander
        hauteurs, energies, utilisations, capacites, deports = set(), set(), set(), set(), set()
        
        for p in produits_correspondants:
            specs = p.caracteristiques.get("specifications", {})
            if specs.get("hauteur_travail") and specs.get("hauteur_travail") != "-": hauteurs.add(specs["hauteur_travail"])
            if specs.get("energie") and specs.get("energie") != "-": energies.add(specs["energie"])
            if specs.get("utilisation") and specs.get("utilisation") != "-": utilisations.add(specs["utilisation"])
            if specs.get("capacite") and specs.get("capacite") != "-": capacites.add(specs["capacite"])
            if specs.get("deport") and specs.get("deport") != "-": deports.add(specs["deport"])

        reponse = f"✅ Catégorie trouvée. Pour trouver le modèle exact, tu dois demander au client de choisir parmi ces critères (s'ils ne l'ont pas déjà précisé) :\n"
        if hauteurs: reponse += f"- Hauteurs : {', '.join(sorted(list(hauteurs)))}\n"
        if energies: reponse += f"- Énergie : {', '.join(list(energies))}\n"
        if utilisations: reponse += f"- Usage : {', '.join(list(utilisations))}\n"
        if capacites: reponse += f"- Capacité de levage : {', '.join(list(capacites))}\n"
        if deports: reponse += f"- Déport : {', '.join(list(deports))}\n"
        
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
    outils_disponibles = [consulter_catalogue, transferer_commercial]
    
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
            # 1. L'IA a récolté TOUTES les informations de l'enquête !
            nom = args.get("nom", "Non précisé")
            entreprise = args.get("entreprise", "Non précisé") # 👈 Correspond maintenant au modèle !
            email = args.get("email", "Non précisé")
            telephone = args.get("telephone_personnel", "Non précisé") # 👈 Précision du champ
            produit = args.get("produit", "Matériel") # 👈 Correspond au modèle !
            quantite = int(args.get("quantite", 1))
            dimensions = args.get("dimensions", "Standard")
            duree = args.get("duree", "Non précisée")
            montant_ht = float(args.get("montant", 0.0))
            # 2. On met à jour la "carte d'identité" du client dans la Base de Données
            prospect.nom = nom
            prospect.entreprise = entreprise
            prospect.email = email
            prospect.telephone = telephone
            
            # 👇 --- 🌟 INTÉGRATION CRM INVISIBLE POUR L'IA 🌟 --- 👇
            prospect.status = "Qualifié" 
            prospect.montant_en_cours = montant_ht
            prospect.date_relance = datetime.now() + timedelta(days=2) # Relance prévue dans 2 jours
            # 👆 ---------------------------------------------------- 👆
            
            db.commit()

            # 3. Création du devis automatique (Bypass du formulaire !)
            # 3. Création du devis automatique (Bypass du formulaire !)
            import uuid
            id_du_devis = f"DEV-{str(uuid.uuid4())[:8].upper()}"
            
            # 👇 NOUVEAU : On cherche le produit dans la base pour récupérer son ID
            produit_db = db.query(Produit).filter(Produit.nom.ilike(f"%{produit}%")).first()
            produit_id_trouve = produit_db.produit_id if produit_db else None

            nouveau_devis = Devis(
                devis_id=id_du_devis,
                prospect_id=prospect.prospect_id,
                produit_id=produit_id_trouve,  # 👈 AJOUTÉ
                quantite=quantite,             # 👈 AJOUTÉ
                prix_total=montant_ht,
                prix_total_ttc=round(montant_ht * 1.20, 2),
                duree=duree,
                status="Brouillon"
            )
            db.add(nouveau_devis)
            db.commit()
            nouvelle_relance = RelanceAuto(
                devis_id=id_du_devis,
                date_planifiee=prospect.date_relance, # Déjà calculée à J+2
                statut="Planifiée",
                contenu_message=f"Bonjour {nom}, avez-vous pu consulter notre devis {id_du_devis} ?"
            )
            db.add(nouvelle_relance)
            db.commit()

            # 4. Génération du PDF physique
            prospect_data = {
                "nom": nom, "email": email, "entreprise": entreprise, "telephone": telephone
            }
            devis_data = {
                "devis_id": id_du_devis,
                "duree": duree,
                "quantite": quantite,
                "prix_unitaire": montant_ht / quantite if quantite > 0 else montant_ht,
                "prix_total": montant_ht,
                "tva": round(montant_ht * 0.20, 2),
                "frais_livraison": 0,
                "montant_caution": 0,
                "prix_total_ttc": round(montant_ht * 1.20, 2)
            }
            
            # (On combine le produit et la dimension pour le PDF)
            description_pdf = f"{produit} - {dimensions}"
            chemin_pdf = generate_devis_pdf(devis_data, prospect_data, description_pdf)

            # 5. Notification au Directeur
            from app.utils.email_sender import envoyer_notification_directeur
            envoyer_notification_directeur(id_du_devis, nom, devis_data["prix_total_ttc"], email, telephone)

            # 6. La réponse finale que l'IA dira au client
            texte_final = f"C'est parfait {nom} ! J'ai bien enregistré votre demande pour {quantite} {produit} ({dimensions}). Votre devis officiel a été généré avec succès et transmis à notre direction. Vous le recevrez d'ici peu sur votre adresse ({email}). Merci pour votre confiance !"
            
            nouvel_historique = list(historique_actuel)
            nouvel_historique.append({"role": "user", "content": requete.message})
            nouvel_historique.append({"role": "agent", "content": texte_final})
            conversation.messages = nouvel_historique
            db.commit()

            # FIN DE L'ACTION : Plus d'action 'afficher_formulaire' !
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

        elif nom_outil == "transferer_commercial":
            # 1. On met à jour le statut du prospect dans la BDD
            prospect.status = "À rappeler (Négociation)"
            nouvelle_tache = TacheCommercial(
                prospect_id=prospect.prospect_id,
                titre="Appel Client : Négociation de prix",
                description=args.get('motif', 'Aucun motif précisé'),
                date_echeance=datetime.now() + timedelta(hours=2), # À rappeler dans les 2h
                statut="À faire"
            )
            db.add(nouvelle_tache)
            # -----------------------------------------------------------
            
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
            vrai_montant = float(carac.get("2 semaine", carac.get("2 semaines", 2000)))
        elif data.duree == "1 mois":
            vrai_montant = float(carac.get("1 mois", 4000))
        elif data.duree == "6 mois":
            vrai_montant = float(carac.get("6 mois", 20000))
        elif data.duree == "1 an":
            vrai_montant = float(carac.get("1 an", 40000))
    # --------------------------------------------------------
    prix_unitaire = vrai_montant
    vrai_montant = prix_unitaire * data.quantite

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
    return {"status": "success", "pdf_path": chemin_pdf}
    

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