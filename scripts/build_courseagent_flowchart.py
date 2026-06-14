from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "deliverables"
FLOW_PATH = OUT_DIR / "courseagent_data_flow_horizontal.png"


def font(size: int, bold: bool = False):
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf" if bold else "C:/Windows/Fonts/simsun.ttc"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def build_flowchart() -> Path:
    OUT_DIR.mkdir(exist_ok=True)
    img = Image.new("RGB", (1900, 780), "#F7FAFC")
    draw = ImageDraw.Draw(img)

    title_font = font(42, True)
    subtitle_font = font(22)
    node_font = font(20, True)
    small_font = font(17)

    def wrap(value: str, fnt, width: int) -> list[str]:
        lines: list[str] = []
        line = ""
        for ch in value:
            test = line + ch
            if draw.textlength(test, font=fnt) <= width:
                line = test
            else:
                if line:
                    lines.append(line)
                line = ch
        if line:
            lines.append(line)
        return lines

    def center_text(box: tuple[int, int, int, int], value: str, fnt, fill="#0F172A") -> None:
        x1, y1, x2, y2 = box
        lines: list[str] = []
        for chunk in value.split("\n"):
            lines.extend(wrap(chunk, fnt, x2 - x1 - 26))
        total_h = len(lines) * fnt.size + max(0, len(lines) - 1) * 6
        y = y1 + ((y2 - y1) - total_h) / 2 - 2
        for line in lines:
            w = draw.textlength(line, font=fnt)
            draw.text((x1 + ((x2 - x1) - w) / 2, y), line, font=fnt, fill=fill)
            y += fnt.size + 6

    def node(
        x: int,
        y: int,
        w: int,
        h: int,
        label: str,
        fill: str,
        border: str,
        text_fill: str = "#0F172A",
    ) -> tuple[int, int, int, int]:
        box = (x, y, x + w, y + h)
        draw.rounded_rectangle((x + 4, y + 6, x + w + 4, y + h + 6), radius=18, fill="#E2E8F0")
        draw.rounded_rectangle(box, radius=18, fill=fill, outline=border, width=2)
        center_text(box, label, node_font, text_fill)
        return box

    def small_node(
        x: int,
        y: int,
        w: int,
        h: int,
        label: str,
        fill: str,
        border: str,
    ) -> tuple[int, int, int, int]:
        box = (x, y, x + w, y + h)
        draw.rounded_rectangle(box, radius=15, fill=fill, outline=border, width=2)
        center_text(box, label, small_font, "#334155")
        return box

    def arrow(start: tuple[int, int], end: tuple[int, int], color="#64748B", width: int = 3) -> None:
        draw.line((start, end), fill=color, width=width)
        ex, ey = end
        sx, sy = start
        if abs(ex - sx) >= abs(ey - sy):
            if ex >= sx:
                pts = [(ex, ey), (ex - 13, ey - 8), (ex - 13, ey + 8)]
            else:
                pts = [(ex, ey), (ex + 13, ey - 8), (ex + 13, ey + 8)]
        else:
            if ey >= sy:
                pts = [(ex, ey), (ex - 8, ey - 13), (ex + 8, ey - 13)]
            else:
                pts = [(ex, ey), (ex - 8, ey + 13), (ex + 8, ey + 13)]
        draw.polygon(pts, fill=color)

    def orthogonal(points: list[tuple[int, int]], color="#64748B", width: int = 3) -> None:
        draw.line(points, fill=color, width=width, joint="curve")
        arrow(points[-2], points[-1], color, width)

    def right_mid(box: tuple[int, int, int, int]) -> tuple[int, int]:
        return box[2], (box[1] + box[3]) // 2

    def left_mid(box: tuple[int, int, int, int]) -> tuple[int, int]:
        return box[0], (box[1] + box[3]) // 2

    def top_mid(box: tuple[int, int, int, int]) -> tuple[int, int]:
        return (box[0] + box[2]) // 2, box[1]

    def bottom_mid(box: tuple[int, int, int, int]) -> tuple[int, int]:
        return (box[0] + box[2]) // 2, box[3]

    draw.text((70, 48), "CourseAgent 数据处理流程图", font=title_font, fill="#0B2545")
    draw.text(
        (72, 106),
        "横向展示从用户上传资料到历史记录下载的完整链路，并把解析与产物生成两个并行阶段单独展开。",
        font=subtitle_font,
        fill="#475569",
    )

    y_main = 350
    main_h = 74
    upload = node(70, y_main, 190, main_h, "用户上传资料", "#EAF3FF", "#93C5FD")
    validate = node(315, y_main, 210, main_h, "输入校验\n任务创建", "#ECFDF5", "#86EFAC")
    storage = node(580, y_main, 230, main_h, "原始文件写入\n对象 / 临时存储", "#FFF7ED", "#FDBA74")
    llm = node(1040, y_main, 220, main_h, "LLM 生成\n结构化 JSON", "#F0FDFA", "#67E8F9")
    verifier = node(1510, y_main, 180, main_h, "Verifier\n产物校验", "#F8FAFC", "#CBD5E1")
    history = node(1740, y_main, 130, main_h, "UI 查询\n下载", "#F0FDF4", "#86EFAC")

    arrow(right_mid(upload), left_mid(validate), "#3B82F6")
    arrow(right_mid(validate), left_mid(storage), "#22C55E")

    # Parallel parse stage.
    parse_nodes = [
        small_node(875, 215, 130, 54, "文本解析", "#EFF6FF", "#BFDBFE"),
        small_node(875, 350, 130, 54, "字幕切分", "#F5F3FF", "#DDD6FE"),
        small_node(875, 485, 130, 54, "视频元数据", "#FFF7ED", "#FED7AA"),
    ]
    parse_bus_x = 842
    arrow(right_mid(storage), (parse_bus_x, y_main + main_h // 2), "#F59E0B")
    draw.line((parse_bus_x, 242, parse_bus_x, 512), fill="#94A3B8", width=3)
    for p in parse_nodes:
        arrow((parse_bus_x, (p[1] + p[3]) // 2), left_mid(p), "#94A3B8")
        orthogonal([right_mid(p), (1020, (p[1] + p[3]) // 2), (1020, y_main + main_h // 2), left_mid(llm)], "#94A3B8")

    # Parallel tool output stage.
    tool_nodes = [
        small_node(1325, 145, 140, 52, "PPTX", "#EEF2FF", "#C7D2FE"),
        small_node(1325, 235, 140, 52, "MP4", "#FFF1F2", "#FECDD3"),
        small_node(1325, 325, 140, 52, "SRT", "#F0FDFA", "#99F6E4"),
        small_node(1325, 415, 140, 52, "导图", "#F5F3FF", "#DDD6FE"),
        small_node(1325, 505, 140, 52, "报告", "#FFFBEB", "#FDE68A"),
    ]
    tool_bus_x = 1290
    arrow(right_mid(llm), (tool_bus_x, y_main + main_h // 2), "#06B6D4")
    draw.line((tool_bus_x, 171, tool_bus_x, 531), fill="#94A3B8", width=3)
    for t in tool_nodes:
        arrow((tool_bus_x, (t[1] + t[3]) // 2), left_mid(t), "#94A3B8")
        orthogonal([right_mid(t), (1482, (t[1] + t[3]) // 2), (1482, y_main + main_h // 2), left_mid(verifier)], "#94A3B8")

    manifest = node(1510, 535, 180, 70, "manifest / 数据库\n记录状态与索引", "#EEF2FF", "#C7D2FE")
    arrow(right_mid(verifier), left_mid(history), "#64748B")
    orthogonal([bottom_mid(verifier), (1600, 500), top_mid(manifest)], "#6366F1")
    orthogonal([right_mid(manifest), (1810, (manifest[1] + manifest[3]) // 2), (1810, y_main + main_h), bottom_mid(history)], "#6366F1")

    # Stage labels.
    labels = [
        (70, 240, "输入"),
        (580, 240, "存储"),
        (875, 155, "并行解析"),
        (1325, 85, "并行产物生成"),
        (1510, 240, "校验与记录"),
    ]
    for x, y, label in labels:
        draw.rounded_rectangle((x, y, x + 120, y + 36), radius=18, fill="#FFFFFF", outline="#CBD5E1", width=1)
        center_text((x, y, x + 120, y + 36), label, small_font, "#475569")

    draw.rounded_rectangle((70, 660, 1830, 720), radius=18, fill="#FFFFFF", outline="#CBD5E1", width=2)
    draw.text((100, 678), "设计重点", font=font(21, True), fill="#0B2545")
    draw.text(
        (215, 680),
        "主流程保持横向阅读；解析阶段按文本、字幕、视频元数据并行；工具阶段按 PPTX、MP4、SRT、导图、报告并行，最后统一校验并写入历史。",
        font=small_font,
        fill="#334155",
    )

    img.save(FLOW_PATH)
    return FLOW_PATH


if __name__ == "__main__":
    print(build_flowchart())
