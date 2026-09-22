"""Prompt Builder / loader.

Per docs/architecture.md section 6: prompts live in versioned .md files under
prompts/, named "NN_prompt_name_XXX.md". This module only loads and substitutes
placeholders — it must never contain business logic.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

from app.errors import PromptError


class PromptLoader:
    def __init__(self, prompts_dir: Path):
        self._prompts_dir = prompts_dir

    def render(self, filename: str, **variables: str) -> str:
        path = self._prompts_dir / filename
        if not path.exists():
            raise PromptError(f"Prompt template not found: {path}")

        template_text = path.read_text(encoding="utf-8")
        try:
            return Template(template_text).substitute(**variables)
        except KeyError as exc:
            raise PromptError(
                f"Missing placeholder {exc} while rendering prompt {filename}"
            ) from exc
