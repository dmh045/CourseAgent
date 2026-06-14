from pathlib import Path

from tools.verifier_tool import verify_outputs


def test_verify_outputs_reports_missing(tmp_path: Path) -> None:
    state = {
        "ppt_path": str(tmp_path / "missing.pptx"),
        "video_path": str(tmp_path / "missing.mp4"),
        "mindmap_image_path": str(tmp_path / "missing.png"),
    }

    result = verify_outputs(state, planned_tools=["create_ppt", "create_video", "generate_mindmap"])

    assert result["ok"] is False
    assert result["missing"]
