from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from .config import TEMPLATES_DIR
from .models import ExperienceBlock


class StudentInfo:
    """Simple container for student contact data."""

    def __init__(
        self,
        name: str,
        email: str,
        phone: str,
        location: str,
        github: str = "",
        linkedin: str = "",
    ):
        self.name = name
        self.email = email
        self.phone = phone
        self.location = location
        self.github = github
        self.linkedin = linkedin


def render_resume(
    student: StudentInfo,
    ordered_blocks: list[ExperienceBlock],
    output_path: str | Path,
) -> Path:
    """Render a one-page PDF resume and write it to output_path.

    ordered_blocks should already be sorted with matched blocks first.
    Returns the output path.
    """
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("resume.html")

    html_content = template.render(
        student=student,
        ordered_blocks=ordered_blocks,
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    HTML(string=html_content).write_pdf(str(output_path))

    return output_path
