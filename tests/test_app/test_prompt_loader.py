import pytest

from app.errors import PromptError
from app.prompt_loader import PromptLoader


def test_render_substitutes_placeholder(tmp_path):
    (tmp_path / "hello.md").write_text("Hello, $name!", encoding="utf-8")
    loader = PromptLoader(prompts_dir=tmp_path)

    result = loader.render("hello.md", name="World")

    assert result == "Hello, World!"


def test_render_missing_file_raises_prompt_error(tmp_path):
    loader = PromptLoader(prompts_dir=tmp_path)
    with pytest.raises(PromptError):
        loader.render("missing.md")


def test_render_missing_placeholder_raises_prompt_error(tmp_path):
    (tmp_path / "hello.md").write_text("Hello, $name!", encoding="utf-8")
    loader = PromptLoader(prompts_dir=tmp_path)
    with pytest.raises(PromptError):
        loader.render("hello.md")
