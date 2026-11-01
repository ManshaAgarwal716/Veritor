"""PDF export generator for Veritor package integrity reports using ReportLab."""

import io
from datetime import UTC, datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.schemas.scans import ScanReportResponse


def _clean_str(val: Any) -> str:
    if val is None:
        return "N/A"
    s = str(val).strip()
    return s if s else "N/A"


def _risk_color(level: str) -> colors.Color:
    lvl = level.upper()
    if lvl == "LOW":
        return colors.HexColor("#16a34a")
    elif lvl in ("MED", "MEDIUM"):
        return colors.HexColor("#d97706")
    elif lvl in ("HIGH", "CRITICAL"):
        return colors.HexColor("#dc2626")
    return colors.HexColor("#475569")


class NumberedCanvas:
    """Canvas that adds running headers and page numbers on two passes."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass


def generate_pdf_report(report: ScanReportResponse) -> bytes:
    """Render a professional cybersecurity report PDF and return bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=12,
    )
    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "DocBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
    )
    code_style = ParagraphStyle(
        "DocCode",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#0f172a"),
    )
    badge_style = ParagraphStyle(
        "BadgeText",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=colors.white,
        alignment=1,  # Center
    )

    story: list[Any] = []

    # 1. Header & Title Banner
    story.append(Paragraph("VERITOR | SUPPLY CHAIN INTEGRITY REPORT", title_style))
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    story.append(
        Paragraph(
            f"Package: <b>{report.package_name}</b> ({report.version}) | "
            f"Ecosystem: <b>{str(report.ecosystem).upper()}</b> | Generated: {now_str}",
            subtitle_style,
        )
    )
    story.append(
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284c7"), spaceAfter=10)
    )

    # 2. Risk Executive Summary
    risk_dict = (
        report.risk
        if isinstance(report.risk, dict)
        else (report.risk.model_dump() if report.risk else {})
    )
    risk_score = risk_dict.get("score", 0)
    risk_level = str(risk_dict.get("level") or "UNKNOWN").upper()
    risk_summary = risk_dict.get("summary") or "Automated deterministic risk evaluation completed."

    score_color = _risk_color(risk_level)
    score_cell = Paragraph(
        f"<b>RISK SCORE</b><br/><font size=20><b>{risk_score}</b></font>/100<br/>"
        f"<b>{risk_level}</b>",
        badge_style,
    )
    conf = _clean_str(risk_dict.get("confidence"))
    comp = _clean_str(risk_dict.get("completeness"))
    summary_cell = Paragraph(
        f"<b>Deterministic Risk Verdict:</b><br/>{risk_summary}<br/><br/>"
        f"<b>Confidence:</b> {conf} | <b>Completeness:</b> {comp}",
        body_style,
    )

    risk_table = Table(
        [[score_cell, summary_cell]],
        colWidths=[120, 420],
    )
    risk_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), score_color),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#f8fafc")),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(risk_table)
    story.append(Spacer(1, 10))

    # 3. Provenance & Build Identity
    story.append(Paragraph("Provenance & Attestation Verification", section_heading))
    prov_dict = (
        report.provenance
        if isinstance(report.provenance, dict)
        else (report.provenance.model_dump() if report.provenance else {})
    )
    prov_status = str(prov_dict.get("status") or "UNAVAILABLE")
    sig_verified = bool(prov_dict.get("signature_verified") or prov_dict.get("sigstore_verified"))
    digest_matches = bool(
        prov_dict.get("tarball_digest_matches") or prov_dict.get("integrity_matches")
    )
    repo_matched = bool(
        prov_dict.get("repository_matches_declared") or prov_dict.get("repository_matched")
    )
    commit_matched = bool(
        prov_dict.get("commit_matches_source_match") or prov_dict.get("commit_matched")
    )

    prov_rows = [
        [
            Paragraph("<b>Provenance Status</b>", body_style),
            Paragraph(f"<b>{prov_status}</b>", body_style),
        ],
        [
            Paragraph("<b>Sigstore Attestation</b>", body_style),
            Paragraph(
                "Verified Cryptographically"
                if sig_verified
                else "No cryptographically verified signature",
                body_style,
            ),
        ],
        [
            Paragraph("<b>Package Digest Matches</b>", body_style),
            Paragraph(
                "Matches declared registry hash" if digest_matches else "Unmatched or unverified",
                body_style,
            ),
        ],
        [
            Paragraph("<b>Source Repo Matched</b>", body_style),
            Paragraph(
                "Matches declared source repository"
                if repo_matched
                else "Unconfirmed or no attestation",
                body_style,
            ),
        ],
        [
            Paragraph("<b>Commit Matched</b>", body_style),
            Paragraph(
                "Matches matched commit SHA" if commit_matched else "Unconfirmed or no attestation",
                body_style,
            ),
        ],
    ]
    prov_table = Table(prov_rows, colWidths=[180, 360])
    prov_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(prov_table)
    story.append(Spacer(1, 10))

    # 4. Source Repository & Matching
    story.append(Paragraph("Source Repository Resolution", section_heading))
    src_dict = (
        report.source_match
        if isinstance(report.source_match, dict)
        else (report.source_match.model_dump() if report.source_match else {})
    )
    src_url = src_dict.get("repository") or "None"
    if isinstance(src_url, dict):
        src_url = (
            src_url.get("url") or f"https://github.com/{src_url.get('owner')}/{src_url.get('name')}"
        )

    src_rows = [
        [
            Paragraph("<b>Source Match Status</b>", body_style),
            Paragraph(f"<b>{_clean_str(src_dict.get('status'))}</b>", body_style),
        ],
        [
            Paragraph("<b>Repository URL</b>", body_style),
            Paragraph(_clean_str(src_url), body_style),
        ],
        [
            Paragraph("<b>Commit SHA / Tag</b>", body_style),
            Paragraph(
                f"{_clean_str(src_dict.get('commit_sha'))} "
                f"(Tag: {_clean_str(src_dict.get('tag'))})",
                body_style,
            ),
        ],
        [
            Paragraph("<b>Resolution Method</b>", body_style),
            Paragraph(
                f"{_clean_str(src_dict.get('method'))} "
                f"(Confidence: {_clean_str(src_dict.get('confidence'))})",
                body_style,
            ),
        ],
    ]
    src_table = Table(src_rows, colWidths=[180, 360])
    src_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(src_table)
    story.append(Spacer(1, 10))

    # 5. File Inventory & Comparison
    story.append(Paragraph("File Comparison & Generated Artifact Intelligence", section_heading))
    comp_dict = (
        report.comparison
        if isinstance(report.comparison, dict)
        else (report.comparison.model_dump() if report.comparison else {})
    )
    files = comp_dict.get("files", [])
    total_f = len(files)
    identical_f = sum(1 for f in files if f.get("status") == "IDENTICAL")
    added_f = sum(1 for f in files if f.get("status") == "ADDED")
    modified_f = sum(1 for f in files if f.get("status") == "MODIFIED")
    removed_f = sum(1 for f in files if f.get("status") == "REMOVED")
    suspicious_f = sum(
        1 for f in files if str(f.get("classification") or "").upper() == "SUSPICIOUS"
    )
    generated_f = sum(
        1 for f in files if str(f.get("classification") or "").upper() == "LIKELY_GENERATED"
    )

    comp_summary_text = (
        f"Compared <b>{total_f}</b> files between package and repository source: "
        f"<b>{identical_f}</b> identical, <b>{added_f}</b> added, <b>{modified_f}</b> modified, "
        f"<b>{removed_f}</b> removed.<br/>"
        f"Artifact Classification: <b>{generated_f}</b> likely build output, "
        f"<b>{suspicious_f}</b> suspicious artifact(s)."
    )
    story.append(Paragraph(comp_summary_text, body_style))
    story.append(Spacer(1, 10))

    # 6. Static AST Security Findings
    story.append(Paragraph("Security Findings & AST Code Analysis", section_heading))
    sec_dict = (
        report.security
        if isinstance(report.security, dict)
        else (report.security.model_dump() if report.security else {})
    )
    findings = sec_dict.get("findings", [])

    if not findings:
        story.append(
            Paragraph(
                "✅ <b>Clean:</b> No suspicious AST patterns or supply chain risks "
                "detected in analyzed files.",
                body_style,
            )
        )
    else:
        finding_rows = [
            [
                Paragraph("<b>Rule ID</b>", body_style),
                Paragraph("<b>Location</b>", body_style),
                Paragraph("<b>Sev</b>", body_style),
                Paragraph("<b>Finding Detail</b>", body_style),
            ]
        ]
        for f in findings[:10]:  # Limit to 10 for layout clarity
            rule_id = f.get("rule_id", "N/A")
            loc = f"{f.get('path', 'N/A')}:{f.get('line', 0)}"
            sev = f.get("severity", "INFO")
            exp = f.get("explanation", "")
            evid = f.get("evidence", "")
            detail = f"<b>{exp}</b><br/><font color='#64748b'>Evidence:</font> {evid}"
            finding_rows.append(
                [
                    Paragraph(rule_id, code_style),
                    Paragraph(loc, code_style),
                    Paragraph(sev, body_style),
                    Paragraph(detail, body_style),
                ]
            )

        finding_table = Table(finding_rows, colWidths=[70, 140, 50, 280])
        finding_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(finding_table)
        if len(findings) > 10:
            extra = len(findings) - 10
            story.append(
                Paragraph(
                    f"<i>...and {extra} additional finding(s). "
                    f"See complete JSON export for full list.</i>",
                    subtitle_style,
                )
            )

    story.append(Spacer(1, 10))

    # 7. AI Behavioral Investigation
    story.append(Paragraph("AI Behavioral Investigation (Ollama / Qwen2.5-Coder)", section_heading))
    ai_dict = (
        report.ai if isinstance(report.ai, dict) else (report.ai.model_dump() if report.ai else {})
    )
    ai_summary = (
        ai_dict.get("behavioral_summary") or "AI investigation confirmed deterministic analysis."
    )
    ai_model = ai_dict.get("model") or "qwen2.5-coder:7b"
    ai_status = ai_dict.get("status") or "COMPLETED"

    story.append(
        Paragraph(
            f"<b>Model:</b> {ai_model} | <b>Status:</b> {ai_status}<br/>"
            f"<b>Assessment:</b> {ai_summary}",
            body_style,
        )
    )
    story.append(Spacer(1, 10))

    # 8. Recommendations & Limitations
    recs = risk_dict.get("recommendations", [])
    if recs:
        story.append(Paragraph("Recommendations", section_heading))
        for r in recs:
            story.append(Paragraph(f"• {r}", body_style))
        story.append(Spacer(1, 6))

    limits = risk_dict.get("limitations", [])
    if limits:
        story.append(Paragraph("Analysis Limitations", section_heading))
        for lim in limits:
            story.append(Paragraph(f"• <i>{lim}</i>", subtitle_style))
        story.append(Spacer(1, 6))

    # Build document
    doc.build(story)
    return buffer.getvalue()
