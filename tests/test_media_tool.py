from pathlib import Path

from moviepy import ColorClip

from tools.media_tool import compose_videos, filter_video_by_subtitles, parse_srt
from tools.media_tool import create_explanation_video
from tools.mock_data import default_outline, default_scripts


def test_create_explanation_video(tmp_path: Path) -> None:
    output_path = tmp_path / "final_video.mp4"
    outline = default_outline()
    result = create_explanation_video(outline, default_scripts(outline), str(output_path), seconds_per_slide=1, voice_enabled=False)

    assert Path(result).exists()
    assert Path(result).stat().st_size > 0
    assert (tmp_path / "subtitles.srt").exists()
    assert (tmp_path / "video_markers.json").exists()
    assert (tmp_path / "video_chapters.md").exists()
    assert (tmp_path / "voice_report.json").exists()


def test_parse_srt() -> None:
    items = parse_srt("1\n00:00:00,000 --> 00:00:01,500\n第一句讲解\n\n")

    assert len(items) == 1
    assert items[0].start == 0
    assert items[0].end == 1.5
    assert items[0].text == "第一句讲解"


def test_filter_video_by_subtitles(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    ColorClip((320, 180), color=(20, 80, 160), duration=4).write_videofile(
        str(source), fps=4, codec="libx264", audio=False, logger=None, pixel_format="yuv420p"
    )
    srt = tmp_path / "source.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n保留讲解\n\n"
        "2\n00:00:02,000 --> 00:00:03,000\n删除敏感内容\n\n",
        encoding="utf-8",
    )

    report = filter_video_by_subtitles(
        str(source),
        str(srt),
        str(tmp_path / "filtered.mp4"),
        sensitive_words=["敏感"],
        remove_non_speech=True,
        padding=0,
    )

    assert Path(report["output_video"]).exists()
    assert Path(report["output_subtitles"]).exists()
    assert len(report["keep_intervals"]) == 1
    assert report["removed"]


def test_compose_videos(tmp_path: Path) -> None:
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    ColorClip((320, 180), color=(200, 40, 40), duration=1).write_videofile(
        str(first), fps=4, codec="libx264", audio=False, logger=None, pixel_format="yuv420p"
    )
    ColorClip((320, 180), color=(40, 160, 80), duration=1).write_videofile(
        str(second), fps=4, codec="libx264", audio=False, logger=None, pixel_format="yuv420p"
    )

    report = compose_videos([str(first), str(second)], str(tmp_path / "composed.mp4"), title="测试合成")

    assert Path(report["output_video"]).exists()
    assert Path(report["output_video"]).stat().st_size > 0
