import ast
from pathlib import Path


APP = Path(__file__).parents[1] / "apps" / "script-generator-space" / "app.py"


def test_script_generator_space_uses_qwen_on_zerogpu() -> None:
    source = APP.read_text(encoding="utf-8")
    ast.parse(source, filename=str(APP))

    assert 'MODEL_ID = "Qwen/Qwen3-4B"' in source
    assert "@spaces.GPU(duration=120)" in source
    assert 'api_name="generate"' in source
