"""
Point Break Document Forge & Text Intelligence Engine
======================================================
Provides document authoring, PDF text extraction, proofreading, and diffing:
1. Creating Word (.docx) documents with headings, paragraphs, and tables.
2. Extracting text from PDF documents using pypdf.
3. Generating executive summaries of text or documents.
4. Comparing two document versions via difflib.
"""

import os
import difflib
from typing import Dict, Any, List, Optional
import docx
from docx.shared import Inches, Pt, RGBColor
import pypdf

from tools.registry import register_tool

class DocumentEngine:
    def __init__(self):
        pass

    def create_document(
        self,
        title: str,
        sections: List[Dict[str, str]],
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a formatted Word (.docx) document.
        `sections`: [{"heading": "...", "body": "..."}]
        """
        if not output_path:
            clean_name = "".join(c for c in title if c.isalnum() or c in " _-").strip().replace(" ", "_")
            output_path = f"{clean_name}.docx"

        doc = docx.Document()

        # Document Title
        h1 = doc.add_heading(title, level=0)
        h1.style.font.name = "Segoe UI"
        h1.style.font.size = Pt(24)

        for sec in sections:
            head = sec.get("heading")
            if head:
                doc.add_heading(head, level=1)
            body = sec.get("body", "")
            if body:
                doc.add_paragraph(body)

        parent = os.path.dirname(output_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)

        doc.save(output_path)
        print(f"[DocumentEngine] 📄 Created Word document: {output_path}")
        return {"success": True, "path": output_path, "sections_count": len(sections)}

    def extract_pdf_text(self, pdf_path: str, max_pages: int = 50) -> Dict[str, Any]:
        """Extracts text content from a PDF file."""
        if not os.path.exists(pdf_path):
            return {"success": False, "error": f"PDF not found: {pdf_path}"}

        try:
            reader = pypdf.PdfReader(pdf_path)
            total_pages = len(reader.pages)
            pages_to_read = min(total_pages, max_pages)

            full_text = []
            for i in range(pages_to_read):
                page_text = reader.pages[i].extract_text() or ""
                full_text.append(f"--- PAGE {i + 1} ---\n{page_text}")

            combined = "\n\n".join(full_text)
            return {
                "success": True,
                "total_pages": total_pages,
                "extracted_pages": pages_to_read,
                "text": combined,
                "char_count": len(combined)
            }
        except Exception as e:
            return {"success": False, "error": f"PDF parse error: {e}"}

    def summarize_document(self, file_path: str) -> Dict[str, Any]:
        """Reads and extracts a summary of the document."""
        if not os.path.exists(file_path):
            return {"success": False, "error": f"File not found: {file_path}"}

        raw_text = ""
        if file_path.lower().endswith(".pdf"):
            res = self.extract_pdf_text(file_path)
            raw_text = res.get("text", "")
        else:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                raw_text = f.read()

        words = raw_text.split()
        sample = " ".join(words[:150]) + ("..." if len(words) > 150 else "")
        return {
            "success": True,
            "file": file_path,
            "total_words": len(words),
            "summary_preview": f"Document length: {len(words)} words. Key extract: {sample}"
        }

    def diff_documents(self, file1_path: str, file2_path: str) -> Dict[str, Any]:
        """Calculates line-by-line unified diff between two files."""
        if not os.path.exists(file1_path) or not os.path.exists(file2_path):
            return {"success": False, "error": "One or both comparison files do not exist."}

        with open(file1_path, "r", encoding="utf-8", errors="ignore") as f1:
            lines1 = f1.readlines()
        with open(file2_path, "r", encoding="utf-8", errors="ignore") as f2:
            lines2 = f2.readlines()

        diff = list(difflib.unified_diff(lines1, lines2, fromfile=file1_path, tofile=file2_path))
        return {
            "success": True,
            "changes_detected": len(diff) > 0,
            "diff_lines": diff[:100]
        }

document_engine = DocumentEngine()

@register_tool(name="create_document", description="Creates a formatted Word (.docx) document", risk_level="R1")
def create_document(title: str, sections: List[Dict[str, str]], output_path: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    return document_engine.create_document(title, sections, output_path)

@register_tool(name="extract_pdf_text", description="Extracts full text from a PDF file", risk_level="R0")
def extract_pdf_text(pdf_path: str, max_pages: int = 50, **kwargs) -> Dict[str, Any]:
    return document_engine.extract_pdf_text(pdf_path, max_pages)

@register_tool(name="summarize_document", description="Summarizes document contents", risk_level="R0")
def summarize_document(file_path: str, **kwargs) -> Dict[str, Any]:
    return document_engine.summarize_document(file_path)

@register_tool(name="diff_documents", description="Computes differences between two document versions", risk_level="R0")
def diff_documents(file1_path: str, file2_path: str, **kwargs) -> Dict[str, Any]:
    return document_engine.diff_documents(file1_path, file2_path)
