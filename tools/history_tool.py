from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from config import RUNS_DIR


MANIFEST_NAME = "manifest.json"


def create_run_dir(kind: str, source_path: str | Path | None = None) -> Path:
    """Create an isolated folder for one generated run."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    source_name = Path(source_path).stem if source_path else "untitled"
    slug = _slug(source_name)[:36] or "untitled"
    run_dir = RUNS_DIR / f"{timestamp}_{kind}_{slug}"
    suffix = 1
    while run_dir.exists():
        suffix += 1
        run_dir = RUNS_DIR / f"{timestamp}_{kind}_{slug}_{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_manifest(run_dir: str | Path, manifest: Dict[str, Any]) -> str:
    path = Path(run_dir) / MANIFEST_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": Path(run_dir).name,
        "run_dir": str(Path(run_dir)),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        **manifest,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def load_manifest(path_or_dir: str | Path) -> Dict[str, Any]:
    path = Path(path_or_dir)
    if path.is_dir():
        path = path / MANIFEST_NAME
    return json.loads(path.read_text(encoding="utf-8"))


def list_manifests() -> List[Dict[str, Any]]:
    manifests: List[Dict[str, Any]] = []
    if not RUNS_DIR.exists():
        return manifests
    for path in RUNS_DIR.glob(f"*/{MANIFEST_NAME}"):
        try:
            item = load_manifest(path)
            item["manifest_path"] = str(path)
            item["size_bytes"] = directory_size(Path(item.get("run_dir", path.parent)))
            manifests.append(item)
        except Exception:
            continue
    return sorted(manifests, key=lambda item: str(item.get("created_at", "")), reverse=True)


def collect_artifacts(run_dir: str | Path, names: Iterable[str]) -> Dict[str, str]:
    base = Path(run_dir)
    artifacts: Dict[str, str] = {}
    for name in names:
        path = base / name
        if path.exists() and path.is_file():
            artifacts[name] = str(path)
    return artifacts


def directory_size(path: str | Path) -> int:
    base = Path(path)
    if not base.exists():
        return 0
    return sum(item.stat().st_size for item in base.rglob("*") if item.is_file())


def delete_run(run_id: str) -> bool:
    target = (RUNS_DIR / run_id).resolve()
    root = RUNS_DIR.resolve()
    if root not in target.parents:
        return False
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
        return True
    return False


def set_pinned(run_id: str) -> None:
    for manifest in list_manifests():
        run_dir = Path(manifest.get("run_dir", ""))
        if not run_dir.exists():
            continue
        manifest["pinned"] = manifest.get("run_id") == run_id
        manifest.pop("manifest_path", None)
        manifest.pop("size_bytes", None)
        (run_dir / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", value, flags=re.U).strip("._")
    return cleaned or "untitled"
