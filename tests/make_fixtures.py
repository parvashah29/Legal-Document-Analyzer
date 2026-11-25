"""Builds fictional sample contracts (TXT, DOCX, PDF text, PDF scanned-like) into a directory."""
import io
import sys
from pathlib import Path

RISKY = [
    "SERVICES AGREEMENT between Acme Widgets LLC (the Client) and Jane Doe (the Contractor). All parties are fictional.",
    "1. Term and Renewal. This Agreement shall automatically renew for successive one-year terms unless the Contractor gives written notice of non-renewal at least ninety (90) days before the end of the then-current term.",
    "2. Termination. The Client may terminate this Agreement at any time, for any reason or no reason, in its sole discretion, without liability. The Contractor may not terminate before the end of the term.",
    "3. Liability. The Contractor's liability under this Agreement shall be unlimited, including for indirect and consequential damages.",
    "4. Indemnification. The Contractor shall indemnify and hold harmless the Client from any and all claims, damages and expenses, even if caused in part by the negligence of the Client.",
    "5. Non-Compete. During the term and for five (5) years afterward, the Contractor shall not, anywhere worldwide, engage in any business that competes with the Client.",
    "6. Intellectual Property. The Contractor hereby assigns to the Client all right, title and interest in all work product, inventions and intellectual property created during the term, including pre-existing tools.",
    "7. Payment. Invoices are payable in 60 days. Late payments accrue a fee of 1.5% per month.",
    "8. Governing Law. This Agreement is governed by the laws of the State of Delaware. Disputes will be resolved by binding arbitration under AAA rules and the Contractor bears all costs.",
    "9. Confidentiality. The Contractor shall keep all information confidential in perpetuity, under no circumstances disclosing it.",
]
CLEAN = [
    "MUTUAL NON-DISCLOSURE AGREEMENT between Alpha Corp and Beta Inc. (fictional).",
    "1. Each party may disclose confidential information to the other for evaluating a possible business relationship. Confidential information excludes information that is public, independently developed, or lawfully received from a third party.",
    "2. Each party shall protect the other's confidential information for three (3) years. Either party may terminate this Agreement on thirty (30) days' written notice.",
    "3. This Agreement is governed by the laws of the State of New York.",
]


def build(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    (out / "risky.txt").write_text("\n\n".join(RISKY))
    (out / "clean_nda.txt").write_text("\n\n".join(CLEAN))
    from docx import Document
    d = Document()
    for p in RISKY:
        d.add_paragraph(p)
    d.save(out / "risky.docx")
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import Paragraph, SimpleDocTemplate
    from reportlab.lib.styles import getSampleStyleSheet
    st = getSampleStyleSheet()["Normal"]
    SimpleDocTemplate(str(out / "risky.pdf"), pagesize=letter).build([Paragraph(p.replace("&", "&amp;"), st) for p in RISKY])
    # image-only PDF (no text layer) to emulate a scan
    from reportlab.pdfgen import canvas
    from PIL import Image
    img = Image.new("RGB", (200, 100), "white")
    c = canvas.Canvas(str(out / "scanned.pdf"), pagesize=letter)
    c.drawInlineImage(img, 50, 500)
    c.save()
    (out / "not_a_pdf.pdf").write_bytes(b"hello this is not a pdf")


if __name__ == "__main__":
    build(Path(sys.argv[1]))
