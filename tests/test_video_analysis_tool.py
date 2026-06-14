from __future__ import annotations

from pathlib import Path

from tools.video_analysis_tool import analyze_course_video


def test_analyze_course_video_from_srt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOCK_MODE", "true")
    video = tmp_path / "lecture.mp4"
    video.write_bytes(b"fake video placeholder")
    srt = tmp_path / "lecture.srt"
    srt.write_text(
        "\n".join(
            [
                "1",
                "00:00:00,000 --> 00:00:08,000",
                "今天我们介绍 KLM 效率模型，它用于预测用户完成界面操作的时间。",
                "",
                "2",
                "00:00:08,000 --> 00:00:18,000",
                "K 表示按键，P 表示指向，H 表示手在设备之间移动，M 表示心理准备。",
                "",
                "3",
                "00:00:18,000 --> 00:00:32,000",
                "计算规则的重点是如何插入或删除 M，并通过 Temperature Converter 案例完成演算。",
                "",
            ]
        ),
        encoding="utf-8",
    )

    report = analyze_course_video(str(video), subtitle_path=str(srt), output_dir=tmp_path, transcribe_if_missing=False)

    assert report["subtitle_source"] == "uploaded_srt"
    assert Path(report["analysis_markdown"]).exists()
    assert Path(report["markers_path"]).exists()
    assert Path(report["mindmap_visual"]).exists()
    assert report["markers"]
    assert report["highlights"]
    assert "KLM" in Path(report["transcript_path"]).read_text(encoding="utf-8")
