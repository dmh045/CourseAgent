from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict

from config import is_mock_mode
from tools.content_guard import contains_unrelated_project_terms, is_sparse_mindmap
from tools.local_content import _looks_like_klm, local_mindmap
from tools.llm_client import call_llm
from tools.mock_data import default_mindmap
from tools.prompt_loader import load_prompt


def generate_mindmap_structure(text: str) -> Dict[str, Any]:
    """Generate a hierarchical mindmap JSON structure."""
    if is_mock_mode():
        return local_mindmap(text)
    prompt = load_prompt("mindmap_prompt.txt", text=text[:26000])
    result = call_llm(prompt, expect_json=True, schema_name="mindmap", fallback=local_mindmap(text))
    if isinstance(result, dict) and "children" in result:
        if contains_unrelated_project_terms(result, text) or is_sparse_mindmap(result) or _domain_mismatch(result, text):
            return local_mindmap(text)
        return result
    return local_mindmap(text) or default_mindmap()


def _domain_mismatch(mindmap: Dict[str, Any], source_text: str) -> bool:
    if not _looks_like_klm(source_text):
        return False
    content = json.dumps(mindmap, ensure_ascii=False).lower()
    signals = ["klm", "keystroke", "interface timings", "calculation rules", "rule 0", "temperature converter"]
    return sum(signal in content for signal in signals) < 2 or "交互设计过程" in content


def create_mindmap_image(mindmap_data: Dict[str, Any], output_path: str) -> str:
    """
    Render the mindmap to PNG with Graphviz.

    If Graphviz is unavailable, write a Mermaid mindmap file and return its path.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    _ensure_graphviz_path()
    try:
        from graphviz import Digraph

        graph = Digraph("mindmap", format="png")
        graph.attr(rankdir="LR", bgcolor="white", margin="0.05", nodesep="0.28", ranksep="0.5")
        graph.attr("node", shape="box", style="rounded,filled", fontname="Microsoft YaHei", color="#3b82f6", fillcolor="#eff6ff")
        graph.attr("edge", color="#64748b")

        counter = {"value": 0}

        def add_node(label: str, parent: str | None = None) -> str:
            counter["value"] += 1
            node_id = f"n{counter['value']}"
            graph.node(node_id, label[:30])
            if parent:
                graph.edge(parent, node_id)
            return node_id

        def add_branch(node: Dict[str, Any], parent_id: str) -> None:
            label = str(node.get("name", "知识点")).strip() or "知识点"
            node_id = add_node(label, parent_id)
            for child_node in node.get("children", []) or []:
                if isinstance(child_node, dict):
                    add_branch(child_node, node_id)

        root_id = add_node(mindmap_data.get("title", "课程资料主题"))
        for child in mindmap_data.get("children", []):
            if isinstance(child, dict):
                add_branch(child, root_id)

        source_path = output.with_name(f"{output.stem}_source_{uuid.uuid4().hex}")
        rendered = graph.render(filename=str(source_path), cleanup=True)
        rendered_path = Path(rendered)
        if rendered_path != output:
            if output.exists():
                try:
                    output.unlink()
                except PermissionError:
                    pass
            shutil.copyfile(rendered_path, output)
            try:
                rendered_path.unlink()
            except PermissionError:
                pass
        if source_path.exists():
            try:
                source_path.unlink()
            except PermissionError:
                pass
        _trim_image_whitespace(output)
        return str(output)
    except Exception:
        mermaid_path = output.with_suffix(".mmd")
        mermaid_path.write_text(to_mermaid(mindmap_data), encoding="utf-8")
        return str(mermaid_path)


def to_mermaid(mindmap_data: Dict[str, Any]) -> str:
    """Convert mindmap JSON to Mermaid mindmap syntax."""
    lines = ["mindmap", f"  root(({mindmap_data.get('title', '课程资料主题')}))"]

    def add_lines(node: Dict[str, Any], depth: int) -> None:
        indent = "  " * depth
        lines.append(f"{indent}{node.get('name', '知识点')}")
        for child_node in node.get("children", []) or []:
            if isinstance(child_node, dict):
                add_lines(child_node, depth + 1)

    for child in mindmap_data.get("children", []):
        if isinstance(child, dict):
            add_lines(child, 2)
    return "\n".join(lines) + "\n"


def _ensure_graphviz_path() -> None:
    """Add common Windows Graphviz install folders to PATH for this process."""
    if shutil.which("dot"):
        return

    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Graphviz" / "bin",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Graphviz" / "bin",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Graphviz" / "bin",
    ]
    existing = [str(path) for path in candidates if (path / "dot.exe").exists()]
    if existing:
        os.environ["PATH"] = os.pathsep.join(existing + [os.environ.get("PATH", "")])


def _trim_image_whitespace(path: Path) -> None:
    try:
        from PIL import Image, ImageChops

        image = Image.open(path).convert("RGB")
        background = Image.new("RGB", image.size, "white")
        diff = ImageChops.difference(image, background)
        bbox = diff.getbbox()
        if not bbox:
            return
        pad = 28
        left = max(bbox[0] - pad, 0)
        top = max(bbox[1] - pad, 0)
        right = min(bbox[2] + pad, image.width)
        bottom = min(bbox[3] + pad, image.height)
        image.crop((left, top, right, bottom)).save(path)
    except Exception:
        return
