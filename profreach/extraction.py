import json
import logging
from groq import Groq
from .config import GROQ_API_KEY, MODEL
from .models import ExtractedProfessor
from .prompts import EXTRACTION_SYSTEM, EXTRACTION_USER

logger = logging.getLogger(__name__)

PAGE_TEXT_LIMIT = 20000


def extract_professor(page_text: str, page_url: str, user_note: str = "") -> ExtractedProfessor:
    """Call the LLM to extract structured professor metadata from page text."""
    client = Groq(api_key=GROQ_API_KEY)

    if len(page_text) > PAGE_TEXT_LIMIT:
        logger.warning(
            "Page text for %s is %d chars; truncating to %d. "
            "Research Interests section may be cut. Consider reviewing the output.",
            page_url,
            len(page_text),
            PAGE_TEXT_LIMIT,
        )

    user_content = EXTRACTION_USER.format(
        page_url=page_url,
        user_note=user_note or "(none)",
        page_text=page_text[:PAGE_TEXT_LIMIT],
    )

    message = client.chat.completions.create(
        model=MODEL,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM},
            {"role": "user", "content": user_content},
        ],
    )

    raw = message.choices[0].message.content.strip()

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
