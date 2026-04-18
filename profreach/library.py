from __future__ import annotations
import re
from .models import ExperienceBlock


def parse_library(md_text: str) -> list[ExperienceBlock]:
    """Parse experience_library.md into a list of ExperienceBlock objects.

    Each block starts with a ## heading. Lines with "key: value" are metadata;
    lines starting with "- " are resume bullets.
    """
    blocks: list[ExperienceBlock] = []
    chunks = re.split(r"^## ", md_text, flags=re.MULTILINE)

    for chunk in chunks[1:]:  # skip preamble before first ##
        lines = chunk.splitlines()
        if not lines:
            continue
        block_id = lines[0].strip()
        meta: dict[str, str] = {}
        bullets: list[str] = []

        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith("- "):
                bullets.append(stripped[2:].strip())
            elif ":" in stripped:
                key, _, value = stripped.partition(":")
                meta[key.strip()] = value.strip()

        if not block_id:
            continue

        blocks.append(
            ExperienceBlock(
                id=block_id,
                title=meta.get("title", block_id),
                organization=meta.get("organization") or None,
                dates=meta.get("dates") or None,
                bullets=bullets,
                tags=[
                    t.strip()
                    for t in meta.get("tags", "[]").strip("[]").split(",")
                    if t.strip()
                ],
                summary=meta.get("summary", ""),
            )
        )

    return blocks


def load_voice_samples(md_text: str) -> str:
    """Return the raw voice samples markdown text for injection into the prompt."""
    return md_text.strip()
