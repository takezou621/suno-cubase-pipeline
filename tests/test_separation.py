"""separation.py のテスト — subprocess をモックし demucs 実行なしで検証する。"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import numpy as np
import pytest
import soundfile as sf

from suno_cubase import separation
from suno_cubase.separation import MODEL_STEMS, find_demucs_cli, separate_stems


def _write_wavs(out_root: Path, model: str, track: str, stems: list[str]) -> None:
    d = out_root / model / track
    d.mkdir(parents=True)
    t = np.linspace(0.0, 0.2, 8820, endpoint=False)
    y = (0.3 * np.sin(2 * np.pi * 440 * t)).astype("float32")
    for name in stems:
        sf.write(str(d / f"{name}.wav"), np.stack([y, y], axis=1), 44100,
                 subtype="FLOAT")


def test_find_demucs_cli_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(separation.shutil, "which", lambda _: None)
    monkeypatch.setattr(separation.sys, "executable", str(tmp_path / "python"))
    assert find_demucs_cli() is None


def test_find_demucs_cli_in_venv(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(separation.shutil, "which", lambda _: None)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "demucs").write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(separation.sys, "executable", str(bindir / "python"))
    assert find_demucs_cli() == str(bindir / "demucs")


def test_separate_missing_audio(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        separate_stems(tmp_path / "no_such.wav", tmp_path / "out")


def test_separate_demucs_not_found(monkeypatch, tmp_path: Path) -> None:
    src = tmp_path / "song.wav"
    src.write_bytes(b"")
    monkeypatch.setattr(separation, "find_demucs_cli", lambda: None)
    with pytest.raises(FileNotFoundError, match="demucs"):
        separate_stems(src, tmp_path / "out")


def test_separate_success(monkeypatch, tmp_path: Path) -> None:
    src = tmp_path / "song.wav"
    src.write_bytes(b"")
    _write_wavs(tmp_path, "htdemucs_6s", "song",
                list(MODEL_STEMS["htdemucs_6s"]))
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return mock.Mock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(separation.subprocess, "run", fake_run)
    sep = separate_stems(src, tmp_path, model="htdemucs_6s", segment=4.0)

    assert set(sep["stems"]) == set(MODEL_STEMS["htdemucs_6s"])
    assert sep["model"] == "htdemucs_6s"
    cmd = calls[0]
    assert cmd[0].endswith("demucs")
    assert "-n" in cmd and "htdemucs_6s" in cmd
    assert "-d" in cmd and "cpu" in cmd
    assert "--segment" in cmd and "4.0" in cmd
    assert cmd[-1] == str(src)


def test_separate_missing_stem_raises(monkeypatch, tmp_path: Path) -> None:
    src = tmp_path / "song.wav"
    src.write_bytes(b"")
    _write_wavs(tmp_path, "htdemucs_6s", "song", ["vocals"])  # 5 不足
    monkeypatch.setattr(separation.subprocess, "run",
                        lambda cmd, **kw: mock.Mock(returncode=0, stdout="",
                                                    stderr=""))
    with pytest.raises(RuntimeError, match="出揃いません"):
        separate_stems(src, tmp_path)


def test_separate_demucs_failure(monkeypatch, tmp_path: Path) -> None:
    src = tmp_path / "song.wav"
    src.write_bytes(b"")
    monkeypatch.setattr(separation.subprocess, "run",
                        lambda cmd, **kw: mock.Mock(returncode=1, stdout="",
                                                    stderr="boom"))
    with pytest.raises(RuntimeError, match="demucs が失敗"):
        separate_stems(src, tmp_path)
