"""パイプライン全体のオーケストレーション (出力フォルダ構成管理)。"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from pathlib import Path

from .analysis import analyze_source, analyze_stems
from .aaf_builder import build_aaf
from .separation import DEFAULT_MODEL, separate_stems


# ファイル名1要素の上限 (APFS/ext4 の 255 バイト制限に対し、".aaf" 拡張子や
# demucs が付けるサフィックスの余地を残した値)
_MAX_NAME_BYTES = 200


def _truncate_utf8(name: str, limit: int = _MAX_NAME_BYTES) -> str:
    """UTF-8 バイト数で切り詰める (文字の途中で切らない)。"""
    raw = name.encode("utf-8")
    if len(raw) <= limit:
        return name
    return raw[:limit].decode("utf-8", errors="ignore")


def sanitize_title(name: str, fallback: str = "song") -> str:
    """ファイル名・トラック名に使えるタイトルへ正規化する。"""
    name = unicodedata.normalize("NFC", name).strip()
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"_+", "_", name).strip("._")
    name = _truncate_utf8(name)
    return name or fallback


def collect_stems(stems_dir: str | Path) -> dict[str, Path]:
    """既存フォルダから *.wav をステムとして収集する (build-aaf 用)。"""
    d = Path(stems_dir)
    wavs = sorted(p for p in d.glob("*.wav") if not p.name.startswith("."))
    if not wavs:
        # demucs 出力 (<stems>/<model>/<track>/) の一段深い構成も許容する
        for sub in sorted(d.glob("*/*/")):
            wavs = sorted(sub.glob("*.wav"))
            if wavs:
                break
    if not wavs:
        raise FileNotFoundError(f"WAV が見つかりません: {d}")
    return {p.stem: p for p in wavs}


def run_pipeline(audio_path: str | Path,
                 out_root: str | Path,
                 title: str | None = None,
                 model: str = DEFAULT_MODEL,
                 device: str = "cpu",
                 segment: float | None = None,
                 stems_dir: str | Path | None = None,
                 overwrite: bool = False,
                 subtype: str = "PCM_24") -> dict:
    """分離 → 解析 → AAF 生成 → レポートまでを実行する。

    stems_dir を指定すると分離をスキップし、そのWAV群をステムとして使う。
    出力先に既にプロジェクトがある場合、overwrite=False なら FileExistsError。

    戻り値: 生成物のパスと解析結果をまとめた dict。
    """
    src = Path(audio_path)
    if not stems_dir and not src.is_file():
        raise FileNotFoundError(f"音声ファイルがありません: {src}")

    name = sanitize_title(title or src.stem)
    project_dir = Path(out_root) / name
    if project_dir.exists() and any(project_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"出力先に既にプロジェクトがあります: {project_dir}\n"
            f"上書きするには --force を付けて再実行してください")
    project_dir.mkdir(parents=True, exist_ok=True)

    # 1) 分離 (または既存ステムの取り込み)
    if stems_dir:
        stems = collect_stems(stems_dir)
        stems_root = Path(stems_dir)
    else:
        sep = separate_stems(src, project_dir / "stems",
                             model=model, device=device, segment=segment)
        stems = sep["stems"]
        stems_root = sep["track_dir"].parent

    # 2) 解析
    analysis: dict = {"title": name, "source": None}
    if not stems_dir:
        analysis["source"] = analyze_source(src)
    analysis["stems"] = analyze_stems(stems)
    analysis["model"] = model if not stems_dir else "external"
    (project_dir / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3) AAF 生成
    aaf_info = build_aaf(stems, project_dir / "cubase" / f"{name}.aaf",
                         title=name, subtype=subtype)

    return {
        "project_dir": project_dir,
        "aaf": aaf_info,
        "analysis": analysis,
        "stems": stems,
        "stems_root": stems_root,
    }


def cleanup_demo_artifacts(project_dir: Path) -> None:
    """将来用フック (今は何もしない)。"""
    shutil.rmtree(project_dir, ignore_errors=True)
