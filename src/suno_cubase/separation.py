"""ステム分離 — demucs CLI (htdemucs_6s) のラッパ。

6 ステム (vocals/drums/bass/guitar/piano/other) に分離する。
demucs は subprocess で呼ぶため、本パッケージ自体は torch に依存しない。
初回実行時にモデル重み (~320MB) を自動ダウンロードする。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_MODEL = "htdemucs_6s"

# モデル別の期待ステム
MODEL_STEMS = {
    "htdemucs_6s": ("vocals", "drums", "bass", "guitar", "piano", "other"),
    "htdemucs": ("vocals", "drums", "bass", "other"),
    "htdemucs_ft": ("vocals", "drums", "bass", "other"),
}


def find_demucs_cli() -> str | None:
    """demucs CLI を探す。PATH 加えて、実行中 venv の bin も見る。"""
    found = shutil.which("demucs")
    if found:
        return found
    candidate = Path(sys.executable).parent / "demucs"
    return str(candidate) if candidate.is_file() else None


def separate_stems(audio_path: str | Path,
                   out_dir: str | Path,
                   model: str = DEFAULT_MODEL,
                   device: str = "cpu",
                   segment: float | None = None,
                   timeout: int = 7200) -> dict:
    """音声ファイルをステムに分離する。

    出力は demucs の慣例に従い `<out_dir>/<model>/<track>/<stem>.wav`。

    戻り値: {"stems": {stem名: Path}, "model", "track_dir", "source"}
    """
    src = Path(audio_path)
    if not src.is_file():
        raise FileNotFoundError(f"音声ファイルがありません: {src}")

    demucs = find_demucs_cli()
    if not demucs:
        raise FileNotFoundError(
            "demucs CLI が見つかりません。setup.sh を実行するか "
            "`pip install 'suno-cubase-pipeline[separate]'` で導入してください")

    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    cmd = [demucs, "-n", model, "-d", device, "--out", str(out_root)]
    if segment:
        cmd += ["--segment", str(segment)]
    cmd.append(str(src))

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"demucs が失敗しました (exit {proc.returncode}):\n"
            f"{(proc.stderr or proc.stdout).strip()[-600:]}")

    track_dir = out_root / model / src.stem
    stems: dict[str, Path] = {}
    for wav in sorted(track_dir.glob("*.wav")):
        stems[wav.stem.lower()] = wav

    expected = MODEL_STEMS.get(model, ())
    missing = [s for s in expected if s not in stems]
    if missing:
        raise RuntimeError(
            f"ステムが出揃いません: 不足={missing}, 実際={sorted(stems)} "
            f"(出力先: {track_dir})")

    return {
        "stems": stems,
        "model": model,
        "track_dir": track_dir,
        "source": src,
    }
