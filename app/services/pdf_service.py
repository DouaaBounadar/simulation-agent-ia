import os
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# 🚀 NOUVEAUTÉ : Un chemin absolu robuste
DOSSIER_RACINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
# (Si votre fichier est directement dans 'app', remplacez "../.." par "..")
PDF_DIR = os.path.join(DOSSIER_RACINE, "generated_pdfs")
os.makedirs(PDF_DIR, exist_ok=True)

def generate_devis_pdf(devis_data: dict, prospect_data: dict, produit_nom: str) -> str:
    filename = f"{devis_data['devis_id']}.pdf"
    filepath = os.path.join(PDF_DIR, filename)

    doc = SimpleDocTemplate(
        filepath,
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54
    )
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DevisTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=25,
        textColor=colors.HexColor("#17324D"),
        spaceAfter=8
    )
    body_style = ParagraphStyle(
        "DevisBody",
        parent=styles["BodyText"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#263746")
    )
    product_style = ParagraphStyle(
        "ProductDescription",
        parent=body_style,
        fontSize=9,
        leading=12
    )
    header_style = ParagraphStyle(
        "TableHeader",
        parent=body_style,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        leading=11
    )
    total_label_style = ParagraphStyle(
        "TotalLabel",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=colors.HexColor("#17324D"),
        alignment=2
    )
    total_value_style = ParagraphStyle(
        "TotalValue",
        parent=total_label_style,
        fontSize=12,
        textColor=colors.HexColor("#126B52")
    )

    story.append(Paragraph(f"DEVIS DE LOCATION : {escape(str(devis_data['devis_id']))}", title_style))
    story.append(Paragraph("Récapitulatif de votre demande de location", body_style))
    story.append(Spacer(1, 18))

    prospect_info = f"""
    <b>Informations client</b><br/>
    Entreprise : {escape(str(prospect_data.get('entreprise') or 'N/A'))}<br/>
    Contact : {escape(str(prospect_data.get('nom') or 'N/A'))}<br/>
    Email : {escape(str(prospect_data.get('email') or 'N/A'))}<br/>
    Téléphone : {escape(str(prospect_data.get('telephone') or 'N/A'))}
    """
    story.append(Paragraph(prospect_info, body_style))
    story.append(Spacer(1, 22))

    caracteristiques = devis_data.get("caracteristiques_choisies") or {}
    produits = caracteristiques.get("produits", []) if isinstance(caracteristiques, dict) else []
    lignes_tableau = [[
        Paragraph("Description du Produit", header_style),
        Paragraph("Quantité", header_style),
        Paragraph("Prix Unitaire (Jour)", header_style),
        Paragraph("Sous-total", header_style)
    ]]

    if produits:
        for produit in produits:
            description = escape(str(produit.get("nom") or produit_nom))
            dimensions = produit.get("dimensions")
            if dimensions and dimensions != "Standard":
                description += f"<br/><font color='#64748B' size='8'>{escape(str(dimensions))}</font>"

            quantite = int(produit.get("quantite") or 0)
            prix_journalier = float(produit.get("prix_unitaire_journalier") or 0.0)
            sous_total = float(produit.get("sous_total_ht") or 0.0)
            lignes_tableau.append([
                Paragraph(description, product_style),
                str(quantite),
                f"{prix_journalier:,.2f} €",
                f"{sous_total:,.2f} €"
            ])
    else:
        quantite = int(devis_data.get("quantite") or 0)
        prix_unitaire = float(devis_data.get("prix_unitaire") or 0.0)
        sous_total = float(devis_data.get("prix_total") or 0.0)
        description = escape(str(produit_nom))
        lignes_tableau.append([
            Paragraph(description, product_style),
            str(quantite),
            f"{prix_unitaire:,.2f} €",
            f"{sous_total:,.2f} €"
        ])

    total_ttc = float(devis_data.get("prix_total_ttc") or 0.0)
    lignes_tableau.append([
        "",
        "",
        Paragraph("Montant Total TTC", total_label_style),
        Paragraph(f"{total_ttc:,.2f} €", total_value_style)
    ])

    largeur_tableau = letter[0] - doc.leftMargin - doc.rightMargin
    tableau = Table(
        lignes_tableau,
        colWidths=[largeur_tableau * 0.43, largeur_tableau * 0.14, largeur_tableau * 0.22, largeur_tableau * 0.21],
        repeatRows=1,
        hAlign="LEFT"
    )
    styles_tableau = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#244B68")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 1), (1, -2), "CENTER"),
        ("ALIGN", (2, 1), (-1, -2), "RIGHT"),
        ("ALIGN", (2, -1), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#244B68")),
        ("LINEBELOW", (0, 1), (-1, -3), 0.45, colors.HexColor("#D6DEE5")),
        ("BOX", (0, 0), (-1, -2), 0.6, colors.HexColor("#CAD4DD")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EAF4F0")),
        ("LINEABOVE", (0, -1), (-1, -1), 1.2, colors.HexColor("#3D8069")),
        ("SPAN", (0, -1), (1, -1)),
        ("BOX", (0, -1), (-1, -1), 0.6, colors.HexColor("#A9CBBE")),
    ]
    for row_index in range(1, len(lignes_tableau) - 1):
        if row_index % 2 == 0:
            styles_tableau.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F6F8FA")))
    tableau.setStyle(TableStyle(styles_tableau))
    story.append(tableau)

    story.append(Spacer(1, 12))
    details_totaux = [
        ["Sous-total HT", f"{float(devis_data.get('prix_total') or 0.0):,.2f} €"],
        ["TVA", f"{float(devis_data.get('tva') or 0.0):,.2f} €"],
        ["Frais de livraison", f"{float(devis_data.get('frais_livraison') or 0.0):,.2f} €"],
        ["Montant de la caution", f"{float(devis_data.get('montant_caution') or 0.0):,.2f} €"]
    ]
    resume_totaux = Table(details_totaux, colWidths=[largeur_tableau * 0.72, largeur_tableau * 0.28], hAlign="RIGHT")
    resume_totaux.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#405466")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(resume_totaux)

    doc.build(story)
    return filepath