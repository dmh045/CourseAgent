from pathlib import Path

import pytest

from tools.mock_data import default_outline, default_scripts
from tools.ppt_tool import create_ppt


def test_create_ppt(tmp_path: Path) -> None:
    pytest.importorskip("pptx")

    output_path = tmp_path / "generated_presentation.pptx"
    result = create_ppt(default_outline(), default_scripts(default_outline()), None, str(output_path))

    assert Path(result).exists()
    assert Path(result).stat().st_size > 0
