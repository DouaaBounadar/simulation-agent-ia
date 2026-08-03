def calculate_devis_totals(prix_journalier_de_base: float, duree_jours: int, quantite: int, taux_tva: float = 0.20):
    """
    Calcule automatiquement la tarification complète d'un devis.
    """
    # 1. Calcul du prix unitaire et total HT
    prix_unitaire = prix_journalier_de_base * duree_jours
    prix_total_ht = prix_unitaire * quantite
    
    # 2. Calcul de la TVA et de la livraison
    tva = round(prix_total_ht * taux_tva, 2)
    frais_livraison = 100.0 if prix_total_ht < 1000.0 else 0.0  # Offert dès 1000€ HT
    
    # 3. Caution (fixée à 30% du total HT)
    montant_caution = round(prix_total_ht * 0.30, 2)
    
    # 4. Total TTC
    prix_total_ttc = round(prix_total_ht + tva + frais_livraison, 2)
    
    return {
        "prix_unitaire": prix_unitaire,
        "prix_total": prix_total_ht,
        "tva": tva,
        "frais_livraison": frais_livraison,
        "montant_caution": montant_caution,
        "prix_total_ttc": prix_total_ttc
    }