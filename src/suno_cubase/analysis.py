"""曲・ステムの解析 — 尺・サンプルレート・レベル統計・BPM 推定。

BPM は librosa が入っている環境だけ推定する (無ければ null のまま進める)。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def _dbfs(x: np.ndarray) -> float:
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    return round(20.0 * float(np.log10(peak)), 2) if peak > 0 else -120.0


def audio_stats(path: str | Path) -> dict:
    """1 ファイル分の基本統計 (peak/rms dBFS, 尺, ch, sr)。"""
    info = sf.info(str(path))
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    rms = float(np.sqrt(np.mean(mono ** 2))) if mono.size else 0.0
    return {
        "path": str(path),
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "duration_sec": round(float(info.frames) / info.samplerate, 3),
        "peak_dbfs": _dbfs(data),
        "rms_dbfs": _dbfs(np.array([rms])),
    }


def estimate_bpm(path: str | Path) -> float | None:
    """librosa によるテンポ推定。未導入環境では None。"""
    try:
        import librosa
    except ImportError:
        return None
    y, sr = librosa.load(str(path), sr=None, mono=True)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr, units="time")
    tempo = float(np.atleast_1d(tempo)[0])
    # 倍テンポ / 半テンポの曖昧さはそのまま返す (判断はユーザー側)
    return round(tempo, 1)


def analyze_source(audio_path: str | Path) -> dict:
    """入力音源の解析結果 (BPM 込み)。"""
    stats = audio_stats(audio_path)
    stats["bpm"] = estimate_bpm(audio_path)
    return stats


def analyze_stems(stems: dict[str, Path]) -> dict:
    """ステムごとの統計。"""
    return {name: audio_stats(p) for name, p in sorted(stems.items())}
