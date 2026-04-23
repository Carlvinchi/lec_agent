from __future__ import annotations
from pathlib import Path
from string import Template
import yaml

PROMPTS_DIR = Path("prompts")


class PromptTemplate:
    def __init__(self, name: str, version: str, description: str, body: str):
        self.name = name
        self.version = version
        self.description = description
        self._body = body

    def render(self, **kwargs) -> str:
        return Template(self._body).safe_substitute(**kwargs)

    def __str__(self) -> str:
        return self._body


class PromptLoader:
    """
    Loads versioned, composable prompts from the prompts/ directory.

    Layout:
        prompts/
          components/        reusable fragments
          v1/                versioned templates with YAML frontmatter
          v2/                ...

    Each versioned template lists components to assemble via frontmatter:
        ---
        name: plan_then_execute
        version: v1
        components:
          - role
          - prior_context
        ---
        Body with $variable substitution.

    Uses string.Template ($variable) so literal { } in JSON examples never
    need escaping.
    """

    def __init__(self, prompts_dir: Path | str = PROMPTS_DIR):
        self._dir = Path(prompts_dir)

    def load(self, name: str, version: str = "v1") -> PromptTemplate:
        path = self._dir / version / f"{name}.md"
        raw = path.read_text()

        if raw.startswith("---"):
            _, front, body_template = raw.split("---", 2)
            meta = yaml.safe_load(front)
            body_template = body_template.strip()
        else:
            meta = {}
            body_template = raw.strip()

        components_text = ""
        for component in meta.get("components", []):
            comp_path = self._dir / "components" / f"{component}.md"
            components_text += comp_path.read_text().strip() + "\n\n"

        assembled = (components_text + body_template).strip()

        return PromptTemplate(
            name=meta.get("name", name),
            version=meta.get("version", version),
            description=meta.get("description", ""),
            body=assembled,
        )

    def list_versions(self, name: str) -> list[str]:
        """Return all versions that have a template for the given strategy name."""
        return sorted(
            d.name for d in self._dir.iterdir()
            if d.is_dir() and d.name != "components" and (d / f"{name}.md").exists()
        )
