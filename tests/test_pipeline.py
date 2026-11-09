"""解析・CLI のテスト (合成音、重い処理なし)。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from suno_cubase.analysis import analyze_source, analyze_stems
from suno_cubase.cli import main as cli_main
from suno_cubase.project import collect_stems, sanitize_title


def _click_track(path: Path, sr: int = 44100, bpm: float = 120.0, sec: float = 8.0) -> Path:
    """BPM が分かりやすいクリック音を作る。"""
    t = np.linspace(0.0, sec, int(sr * sec), endpoint=False)
    y = np.zeros_like(t)
    beat = 60.0 / bpm
    click_sec = 0.03
    pos = 0.0
    while pos < sec:
        n = int(click_sec * sr)
        start = int(pos * sr)
        seg_t = t[:n]
        y[start:start + n] += (np.sin(2 * np.pi * 1000 * seg_t)
                               * np.exp(-seg_t / 0.005))
        pos += beat
    sf.write(str(path), np.stack([y, y], axis=1), sr, subtype="FLOAT")
    return path


def test_sanitize_title() -> None:
    assert sanitize_title("My Song: demo v2 ") == "My_Song_demo_v2"
    assert sanitize_title("///") == "song"


def test_analyze_source_stats(tmp_path: Path) -> None:
    src = _click_track(tmp_path / "click.wav")
    stats = analyze_source(src)
    assert stats["sample_rate"] == 44100
    assert stats["channels"] == 2
    assert abs(stats["duration_sec"] - 8.0) < 0.01
    assert stats["peak_dbfs"] > -1.0
    # librosa があれば BPM が 120 付近になる (無ければ None)
    if stats["bpm"] is not None:
        assert 115 <= stats["bpm"] <= 125 or 55 <= stats["bpm"] <= 65 or 230 <= stats["bpm"] <= 250


def test_analyze_stems(tmp_path: Path) -> None:
    d = tmp_path / "s"
    d.mkdir()
    for name in ["vocals", "bass"]:
        _click_track(d / f"{name}.wav")
    stats = analyze_stems({p.stem: p for p in d.glob("*.wav")})
    assert set(stats) == {"bass", "vocals"}


def test_collect_stems_flat(tmp_path: Path) -> None:
    d = tmp_path / "s"
    d.mkdir()
    _click_track(d / "vocals.wav")
    _click_track(d / "drums.wav")
    stems = collect_stems(d)
    assert set(stems) == {"vocals", "drums"}


def test_cli_build_aaf(tmp_path: Path) -> None:
    d = tmp_path / "s"
    d.mkdir()
    _click_track(d / "vocals.wav", sec=0.5)
    _click_track(d / "drums.wav", sec=0.5)
    out = tmp_path / "song.aaf"
    rc = cli_main(["build-aaf", str(d), "-o", str(out)])
    assert rc == 0
    assert out.is_file()

    rc2 = cli_main(["analyze", str(d / "vocals.wav"),
                    "--json", str(tmp_path / "a.json")])
    assert rc2 == 0
    data = json.loads((tmp_path / "a.json").read_text())
    assert "bpm" in data["source"]


def test_cli_run_with_stems_dir(tmp_path: Path) -> None:
    """分離をスキップして既存ステムから run できること (demucs 不要経路)。"""
    d = tmp_path / "stems"
    d.mkdir()
    _click_track(d / "vocals.wav", sec=0.5)
    _click_track(d / "bass.wav", sec=0.5)
    rc = cli_main(["run", "dummy.wav", "--stems-dir", str(d),
                   "-o", str(tmp_path / "out"), "--title", "テスト曲"])
    assert rc == 0
    proj = tmp_path / "out" / "テスト曲"
    assert (proj / "cubase" / "テスト曲.aaf").is_file()
    analysis = json.loads((proj / "analysis.json").read_text())
    assert analysis["source"] is None          # 入力音源が無い経路
    assert analysis["model"] == "external"
    assert set(analysis["stems"]) == {"bass", "vocals"}
    report = (proj / "report.md").read_text(encoding="utf-8")
    assert "AAF" in report
