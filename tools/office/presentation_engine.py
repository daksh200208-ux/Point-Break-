"""
Point Break Presentation Engine (PowerPoint / 16:9 Decks)
==========================================================
Generates high-impact 16:9 widescreen presentation slide decks:
1. Title and overview slides.
2. Section headers and agenda blocks.
3. Multi-point content slides with structured formatting.
4. Auto-generated speaker notes for each slide.
"""

import os
from typing import Dict, Any, List, Optional
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

from tools.registry import register_tool

class PresentationEngine:
    def __init__(self):
        pass

    def create_presentation(
        self,
        title: str,
        subtitle: str = "Prepared by Point Break AI",
        slides_data: Optional[List[Dict[str, Any]]] = None,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a 16:9 PowerPoint deck.
        `slides_data`: [
            {"title": "...", "points": ["...", "..."], "speaker_notes": "..."}
        ]
        """
        if not output_path:
            clean_name = "".join(c for c in title if c.isalnum() or c in " _-").strip().replace(" ", "_")
            output_path = f"{clean_name}.pptx"

        prs = Presentation()
        # Set 16:9 widescreen dimensions
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        # 1. Title Slide
        title_layout = prs.slide_layouts[0]
        slide = prs.slides.add_slide(title_layout)
        slide.shapes.title.text = title
        if len(slide.placeholders) > 1:
            slide.placeholders[1].text = subtitle

        # 2. Content Slides
        bullet_layout = prs.slide_layouts[1]
        slides = slides_data or [
            {
                "title": "Executive Summary",
                "points": ["Operational objectives defined", "Autonomous execution active", "Verified outcomes delivered"],
                "speaker_notes": "Walk the audience through the high-level objectives and timeline."
            },
            {
                "title": "Key Milestones",
                "points": ["Phase 1: Architecture stabilization", "Phase 2: Data forge deployment", "Phase 3: Multi-agent autonomy"],
                "speaker_notes": "Highlight each delivery milestone and completion confidence."
            }
        ]

        for s_info in slides:
            c_slide = prs.slides.add_slide(bullet_layout)
            c_slide.shapes.title.text = s_info.get("title", "Slide")

            body_shape = c_slide.shapes.placeholders[1]
            tf = body_shape.text_frame
            tf.word_wrap = True

            points = s_info.get("points", [])
            for idx, pt in enumerate(points):
                p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
                p.text = pt
                p.font.size = Pt(20)

            # Speaker Notes
            notes = s_info.get("speaker_notes")
            if notes:
                notes_slide = c_slide.notes_slide
                notes_slide.notes_text_frame.text = notes

        parent = os.path.dirname(output_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)

        prs.save(output_path)
        print(f"[PresentationEngine] 📽️ Presentation saved at: {output_path} ({len(slides) + 1} slides)")
        return {
            "success": True,
            "path": output_path,
            "total_slides": len(slides) + 1
        }

presentation_engine = PresentationEngine()

@register_tool(name="create_presentation", description="Creates a 16:9 PowerPoint presentation deck", risk_level="R1")
def create_presentation(title: str, subtitle: str = "Point Break Report", slides_data: Optional[List[Dict[str, Any]]] = None, output_path: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    return presentation_engine.create_presentation(title, subtitle, slides_data, output_path)
