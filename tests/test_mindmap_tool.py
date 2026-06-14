from pathlib import Path

from tools.mindmap_tool import create_mindmap_image
from tools.mock_data import default_mindmap


def test_create_mindmap_file(tmp_path: Path) -> None:
    result = create_mindmap_image(default_mindmap(), str(tmp_path / "mindmap.png"))
    result_path = Path(result)

    assert result_path.exists()
    assert result_path.suffix in {".png", ".mmd"}
