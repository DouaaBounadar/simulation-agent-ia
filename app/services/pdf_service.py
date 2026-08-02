import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

PDF_DIR = "generated_pdfs"
os.makedirs(PDF_DIR, exist_ok=True)

def generate_devis_pdf(devis_data: dict, prospect_data: dict, produit_nom: str) -> str:
    filename = f"devis_{devis_data['devis_id']}.pdf"
    filepath = os.path.join(PDF_DIR, filename)
    
    doc = SimpleDocTemplate(filepath, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'TitleStyle', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor('#1A365D'), spaceAfter=20
    )
    story.append(Paragraph(f"DEVIS DE LOCATION : {devis_data['devis_id']}", title_style))
    story.append(Spacer(1, 12))

    prospect_info = f"""
    <b>Informations Client :</b><br/>
    <b>Entreprise :</b> {prospect_data.get('entreprise', 'N/A')}<br/>
    <b>Contact :</b> {prospect_data.get('nom', 'N/A')}<br/>
    <b>Email :</b> {prospect_data.get('email', 'N/A')}<br/>
    <b>Téléphone :</b> {prospect_data.get('telephone', 'N/A')}<br/>
    """
    story.append(Paragraph(prospect_info, styles['Normal']))
    story.append(Spacer(1, 20))

    data = [
        ["Désignation", "Durée", "Qté", "Prix Unitaire", "Total HT"],
        [
            f"{produit_nom}\n({', '.join([f'{k}: {v}' for k, v in (devis_data.get('caracteristiques_choisies') or {}).items()])})",
            str(devis_data['duree']),
            str(devis_data['quantite']),
            f"{devis_data['prix_unitaire']} €",
            f"{devis_data['prix_total']} €"
        ]
    ]

    t = Table(data, colWidths=[200, 70, 40, 80, 80])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2B6CB0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    story.append(t)
    story.append(Spacer(1, 20))

    totals = f"""
    <b>Sous-total HT :</b> {devis_data['prix_total']} €<br/>
    <b>TVA :</b> {devis_data['tva']} €<br/>
    <b>Frais de livraison :</b> {devis_data['frais_livraison']} €<br/>
    <b>Montant Caution :</b> {devis_data['montant_caution']} €<br/>
    <hr/>
    <b>TOTAL TTC : {devis_data['prix_total_ttc']} €</b>
    """
    story.append(Paragraph(totals, styles['Normal']))

    doc.build(story)
    return filepath