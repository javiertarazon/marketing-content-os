import ast
import json
from pathlib import Path


NOTEBOOKS = Path(__file__).parents[1] / "notebooks"


def test_notebooks_are_valid_json_with_python_cells() -> None:
    notebooks = sorted(NOTEBOOKS.glob("*.ipynb"))
    assert len(notebooks) == 2

    for path in notebooks:
        notebook = json.loads(path.read_text(encoding="utf-8"))
        assert notebook["nbformat"] == 4

        for cell in notebook["cells"]:
            if cell["cell_type"] != "code":
                continue
            source = "".join(cell["source"])
            python_lines = [
                line
                for line in source.splitlines()
                if not line.lstrip().startswith(("!", "%"))
            ]
            if python_lines:
                ast.parse("\n".join(python_lines), filename=str(path))
