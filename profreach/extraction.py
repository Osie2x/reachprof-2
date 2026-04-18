import json
import anthropic
from .config import ANTHROPIC_API_KEY, MODEL
from .models import ExtractedProfessor
from .prompts import EXTRACTION_SYSTEM, EXTRACTION_USER


def extract_professor(page_text: str, page_url: str, user_note: str = "") -> ExtractedProfessor:
    """Call the LLM to extract structured professor metadata from page text."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_content = EXTRACTION_USER.format(
        page_url=page_url,
        user_note=user_note or "(none)",
        page_text=page_text[:8000],  # guard against very long pages
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = message.content[0].text.strip()

    # strip any accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    data = json.loads(raw)

    # enforce recent_papers max 3
    data["recent_papers"] = data.get("recent_papers", [])[:3]

    return ExtractedProfessor(
        name=data["name"],
        title=data.get("title"),
        university=data.get("university"),
        department=data.get("department"),
        research_areas=data.get("research_areas", []),
        recent_papers=data["recent_papers"],
        contact_email=data.get("contact_email"),
        page_url=page_url,
        extraction_confidence=data.get("extraction_confidence", "medium"),
        extraction_notes=data.get("extraction_notes", ""),
    )
