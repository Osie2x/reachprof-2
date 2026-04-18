from .models import ExtractedProfessor


def validate_extraction(extracted: ExtractedProfessor) -> list[str]:
    """Return a list of warning strings. Empty list = fully valid."""
    warnings = []

    if not extracted.research_areas:
        warnings.append(
            "No research areas extracted -- faculty page may have been parsed poorly."
        )

    if extracted.contact_email and "@" not in extracted.contact_email:
        warnings.append(
            f"Extracted email {extracted.contact_email!r} does not look like an email."
        )

    if extracted.extraction_confidence == "low":
        warnings.append(
            f"Low extraction confidence: {extracted.extraction_notes}"
        )

    if not extracted.name or extracted.name.strip() == "":
        warnings.append("Professor name could not be extracted.")

    return warnings
