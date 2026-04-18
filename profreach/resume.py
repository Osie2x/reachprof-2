from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import pdfkit
from .config import TEMPLATES_DIR
from .models import ExperienceBlock, StudentInfo


def render_resume(
    student: StudentInfo,
    ordered_blocks: list[ExperienceBlock],
    output_path: str | Path,
) -> Path:
    """Render a one-page PDF resume and write it to output_path."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("resume.html")

    html_content = template.render(
        student=student,
        ordered_blocks=ordered_blocks,
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pdfkit.from_string(html_content, str(output_path))

    return output_path
