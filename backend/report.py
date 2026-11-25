"""
PDF Risk Report Generator
Generates branded, downloadable PDF risk analysis reports using reportlab.
"""
import io
from datetime import datetime
from xml.sax.saxutils import escape as _esc

import config


def _e(v) -> str:
    return _esc(str(v if v is not None else ''))


def build_pdf_report(risk_data: dict) -> bytes:
    """
    Builds a professional PDF risk report from classifier output.
    Returns raw PDF bytes suitable for HTTP response.
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            HRFlowable, KeepTogether
        )
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    except ImportError:
        raise ImportError("reportlab is required for PDF generation. Install with: pip install reportlab")
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter,
        rightMargin=60, 
        leftMargin=60, 
        topMargin=50, 
        bottomMargin=50
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Title'],
        fontSize=22,
        spaceAfter=6,
        textColor=colors.HexColor('#1e1b4b'),
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=20,
        textColor=colors.HexColor('#6b7280'),
        fontName='Helvetica'
    )
    
    section_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=16,
        spaceAfter=8,
        textColor=colors.HexColor('#312e81'),
        fontName='Helvetica-Bold'
    )
    
    body_style = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontSize=9,
        leading=13,
        spaceAfter=6,
        textColor=colors.HexColor('#374151'),
        fontName='Helvetica'
    )
    
    small_style = ParagraphStyle(
        'SmallText',
        parent=styles['Normal'],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#6b7280'),
        fontName='Helvetica'
    )

    concern_style = ParagraphStyle(
        'ConcernText',
        parent=styles['Normal'],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#92400e'),
        fontName='Helvetica-Oblique',
        leftIndent=12
    )

    rewrite_style = ParagraphStyle(
        'RewriteText',
        parent=styles['Normal'],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#065f46'),
        fontName='Helvetica-Oblique',
        leftIndent=12
    )

    tip_style = ParagraphStyle(
        'TipText',
        parent=styles['Normal'],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#1e40af'),
        fontName='Helvetica-Oblique',
        leftIndent=12
    )
    
    elements = []
    summary = risk_data.get('summary', {})
    flags = risk_data.get('flags', [])
    doc_id = risk_data.get('doc_id', 'Unknown')
    
    # ---- HEADER ----
    elements.append(Paragraph("Legal Risk Analysis Report", title_style))
    elements.append(Paragraph(
        f"File: {_e(risk_data.get('filename') or 'unknown')}  |  Generated: {datetime.now().strftime('%B %d, %Y %I:%M %p')}  |  "
        f"Document ID: {_e(doc_id[:12])}  |  Analysis: {_e(risk_data.get('engine', 'rules'))}",
        subtitle_style
    ))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e5e7eb')))
    elements.append(Spacer(1, 16))
    
    # ---- RISK SUMMARY TABLE ----
    elements.append(Paragraph("Risk Summary", section_style))
    
    overall = summary.get('overall_score', 0)
    risk_label = summary.get('overall_label') or ('LOW' if overall < 25 else 'MODERATE' if overall < 50 else 'HIGH' if overall < 75 else 'CRITICAL')
    
    summary_data = [
        ['Category', 'Count', 'Overall Risk Score'],
        ['High Risk', str(summary.get('high', 0)), f'{overall}/100 ({risk_label})'],
        ['Medium Risk', str(summary.get('medium', 0)), ''],
        ['Low Risk', str(summary.get('low', 0)), ''],
    ]
    
    summary_table = Table(summary_data, colWidths=[2.5*inch, 1.5*inch, 2.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#312e81')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f9fafb')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f9fafb'), colors.white]),
        ('SPAN', (2, 1), (2, 3)),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))
    
    # ---- FLAGGED CLAUSES ----
    if flags:
        elements.append(Paragraph("Flagged Clauses & Analysis", section_style))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e5e7eb')))
        elements.append(Spacer(1, 8))
        
        risk_colors = {
            'high': colors.HexColor('#dc2626'),
            'medium': colors.HexColor('#d97706'),
            'low': colors.HexColor('#16a34a')
        }
        
        for idx, flag in enumerate(flags, 1):
            risk_level = flag.get('risk_level', 'medium')
            severity = flag.get('severity_score', 5)
            color = risk_colors.get(risk_level, colors.gray)
            
            clause_elements = []
            
            # Clause header
            header_text = f"<b>{idx}. {_e(flag.get('clause_type', 'Unknown'))}</b>  —  " \
                         f"<font color='{color.hexval()}'>{_e(risk_level.upper())} RISK</font>  " \
                         f"(Severity: {severity}/10)"
            clause_elements.append(Paragraph(header_text, body_style))
            
            # Plain English
            clause_elements.append(Paragraph(
                f"<b>Plain English:</b> {_e(flag.get('plain_english', 'N/A'))}", body_style
            ))
            
            # Concerns
            concerns = flag.get('concerns', [])
            if concerns:
                clause_elements.append(Paragraph("<b>Concerns:</b>", small_style))
                for concern in concerns:
                    clause_elements.append(Paragraph(f"- {_e(concern)}", concern_style))
            
            # Suggested Rewrite
            rewrite = flag.get('suggested_rewrite')
            if rewrite:
                clause_elements.append(Paragraph("<b>Suggested Rewrite:</b>", small_style))
                clause_elements.append(Paragraph(f'"{_e(rewrite)}"', rewrite_style))
            
            # Negotiation Tip
            tip = flag.get('negotiation_tip')
            if tip:
                clause_elements.append(Paragraph("<b>Negotiation Tip:</b>", small_style))
                clause_elements.append(Paragraph(f'"{_e(tip)}"', tip_style))
            
            # Raw text snippet
            raw = (flag.get('evidence') or flag.get('raw_text', ''))[:300]
            if raw:
                clause_elements.append(Spacer(1, 4))
                clause_elements.append(Paragraph(
                    f"<font color='#9ca3af'><i>Original text: \"{_e(raw)}\"</i></font>", small_style
                ))
            
            clause_elements.append(Spacer(1, 6))
            clause_elements.append(HRFlowable(width="100%", thickness=0.3, color=colors.HexColor('#f3f4f6')))
            clause_elements.append(Spacer(1, 8))
            
            elements.append(KeepTogether(clause_elements))
    else:
        elements.append(Paragraph("No risky clauses were detected by the rules in this agreement. This does not mean the contract is safe.", body_style))
    
    # ---- FOOTER ----
    elements.append(Spacer(1, 30))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e5e7eb')))
    elements.append(Spacer(1, 8))
    
    footer_style = ParagraphStyle(
        'Footer', parent=styles['Normal'],
        fontSize=7, textColor=colors.HexColor('#9ca3af'),
        alignment=TA_CENTER
    )
    elements.append(Paragraph(_e(config.DISCLAIMER), footer_style))
    
    doc.build(elements)
    return buffer.getvalue()
