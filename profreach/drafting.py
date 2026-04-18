import json
import logging
from groq import Groq
from .config import GROQ_API_KEY, MODEL
from .models import ExperienceBlock, ExtractedProfessor, EmailDraft
from .prompts import DRAFTING_SYSTEM, DRAFTING_USER

logger = logging.getLogger(__name__)

WORD_COUNT_MIN = 90
WORD_COUNT_MAX = 110


def _count_words(text: str) -> int:
    return len(text.split())


def _parse_draft(raw: str) -> tuple[str, str]:
    """Strip optional markdown fences and parse JSON. Returns (subject, body)."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    data = json.loads(raw)
    return data.get("subject", "research interest"), data.get("body", "")


def draft_email(
    professor: ExtractedProfessor,
    top_blocks: list[ExperienceBlock],
    voice_samples_text: str,
    student_name: str,
    student_context: str,
) -> EmailDraft:
    """Generate a 100-word cold email draft for a professor.

    Makes one retry if the first draft's word count falls outside 90-110.
    If the retry also misses, accepts it and logs a warning.
    """
    client = Groq(api_key=GROQ_API_KEY)

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

    message = client.chat.completions.create(
        model=MODEL,
        max_tokens=512,
        messages=[
            {"role": "system", "content": system_with_voice},
            {"role": "user", "content": user_content},
        ],
    )

    subject, body = _parse_draft(message.choices[0].message.content)
    wc = _count_words(body)

    if not (WORD_COUNT_MIN <= wc <= WORD_COUNT_MAX):
        logger.warning(
            "First email draft for %s was %d words (target 90-110). Retrying.",
            professor.name,
            wc,
        )
        retry_user = (
            user_content
            + f"\n\nThe previous draft was {wc} words. "
            "Return exactly 90-110 words in the body. Count carefully before responding."
        )
        retry_message = client.chat.completions.create(
            model=MODEL,
            max_tokens=512,
            messages=[
                {"role": "system", "content": system_with_voice},
                {"role": "user", "content": retry_user},
            ],
        )
        subject, body = _parse_draft(retry_message.choices[0].message.content)
        wc = _count_words(body)
        if not (WORD_COUNT_MIN <= wc <= WORD_COUNT_MAX):
            logger.warning(
                "Retry draft for %s still %d words; accepting anyway.",
                professor.name,
                wc,
            )

    return EmailDraft(
        subject=subject,
        body=body,
        word_count=wc,
    )
