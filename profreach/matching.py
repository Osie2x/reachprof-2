import json
import anthropic
from .config import ANTHROPIC_API_KEY, MODEL
from .models import ExtractedProfessor, ExperienceBlock, MatchResult
from .prompts import MATCHING_SYSTEM, MATCHING_USER


def match_blocks(
    professor: ExtractedProfessor,
    blocks: list[ExperienceBlock],
) -> MatchResult:
    """Rank experience blocks by relevance to this professor's research."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    library_json = json.dumps(
        [
            {
                "id": b.id,
                "title": b.title,
                "organization": b.organization,
                "dates": b.dates,
                "tags": b.tags,
                "summary": b.summary,
            }
            for b in blocks
        ],
        indent=2,
    )

    user_content = MATCHING_USER.format(
        prof_name=professor.name,
        research_areas=", ".join(professor.research_areas),
        recent_papers=", ".join(professor.recent_papers) or "(none listed)",
        library_blocks_json=library_json,
    )

    message = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY).messages.create(
        model=MODEL,
        max_tokens=512,
        system=MATCHING_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    data = json.loads(raw)

    top_ids: list[str] = data.get("top_block_ids", [])
    match_reasoning: str = data.get("match_reasoning", "")

    # build ordered block list from ids; silently skip unknown ids
    block_map = {b.id: b for b in blocks}
    top_blocks = [block_map[bid] for bid in top_ids if bid in block_map]

    return MatchResult(
        professor=professor,
        top_blocks=top_blocks,
        match_reasoning=match_reasoning,
    )
