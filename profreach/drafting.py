import json
import anthropic
from .config import ANTHROPIC_API_KEY, MODEL
from .models import ExperienceBlock, ExtractedProfessor, EmailDraft
from .prompts import DRAFTING_SYSTEM, DRAFTING_USER


def _count_words(text: str) -> int:
    return len(text.split())


def draft_email(
    professor: ExtractedProfessor,
    top_blocks: list[ExperienceBlock],
    voice_samples_text: str,
    student_name: str,
    student_context: str,
) -> EmailDraft:
    """Generate a 100-word cold email draft for a professor."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    anchor_research = (
        professor.research_areas[0] if professor.research_areas else "your research"
    )
    top_experience = (
        top_blocks[0].summary if top_blocks else "relevant coursework and projects"
    )

    user_content = DRAFTING_USER.format(
        student_name=student_name,
        student_context=student_context,
        prof_name=professor.name,
        prof_title=professor.title or "Professor",
        prof_department=professor.department or "your department",
        anchor_research=anchor_research,
        top_experience=top_experience,
    )

    # Use replace instead of .format() because the prompt contains JSON schema
    # curly braces that would confuse Python's str.format().
    system_with_voice = DRAFTING_SYSTEM.replace("{voice_samples}", voice_samples_text)

    message = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=system_with_voice,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    data = json.loads(raw)
    subject = data.get("subject", "research interest")
    body = data.get("body", "")

    return EmailDraft(
        subject=subject,
        body=body,
        word_count=_count_words(body),
    )
