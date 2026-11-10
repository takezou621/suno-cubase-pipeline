"""AAF ビルダーのテスト — 合成WAVから生成し、pyaaf2 で読み戻して検証する。"""

from __future__ import annotations

from pathlib import Path

import aaf2
import numpy as np
import pytest
import soundfile as sf

from suno_cubase.aaf_builder import build_aaf

SR = 44100


def _make_wav(path: Path, sr: int = SR, sec: float = 1.0, freq: float = 440.0) -> Path:
    t = np.linspace(0.0, sec, int(sr * sec), endpoint=False)
    tone = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    sf.write(str(path), np.stack([tone, tone], axis=1), sr, subtype="FLOAT")
    return path


@pytest.fixture()
def stems_dir(tmp_path: Path) -> Path:
    d = tmp_path / "stems"
    d.mkdir()
    for i, name in enumerate(["vocals", "drums", "bass", "guitar", "piano", "other"]):
        _make_wav(d / f"{name}.wav", freq=200.0 + 100 * i)
    return d


def _load_stems(stems_dir: Path) -> dict[str, Path]:
    return {p.stem: p for p in sorted(stems_dir.glob("*.wav"))}


def test_build_aaf_structure(stems_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.aaf"
    info = build_aaf(_load_stems(stems_dir), out, title="テスト曲")

    assert info["sample_rate"] == SR
    assert info["tracks"][0] == "vocals"  # STEM_ORDER 順
    assert info["tracks"][-1] == "other"
    assert out.is_file() and out.stat().st_size > 100_000

    with aaf2.open(str(out)) as f:
        mobs = list(f.content.mobs)
        comps = [m for m in mobs if type(m).__name__ == "CompositionMob"]
        masters = [m for m in mobs if type(m).__name__ == "MasterMob"]
        sources = [m for m in mobs if type(m).__name__ == "SourceMob"]
        assert len(comps) == 1 and len(masters) == 1
        assert len(sources) == 6
        assert str(comps[0].usage) == "Usage_TopLevel"

        # Timecode slot (slot 1) + sound slots (slot 2..)
        assert len(comps[0].slots) == 7
        assert str(comps[0].slots[0].media_kind).lower() == "timecode"
        names = [s.name for s in comps[0].slots if s.name]
        assert names == info["tracks"]

        for slot in comps[0].slots:
            if str(slot.media_kind).lower() == "timecode":
                continue
            assert slot.media_kind.lower() == "sound"
            assert int(slot.edit_rate) == SR
        # 埋め込み EssenceData がステム数分ある (WAV 形式)
        eds = list(f.content.essencedata)
        assert len(eds) == 6
        for ed in eds:
            st = ed.open("r")
            head = bytes(st.read(12))
            st.close()
            assert head[:4] == b"RIFF" and head[8:12] == b"WAVE"


def test_build_aaf_structure_wavedescriptor(stems_dir: Path, tmp_path: Path) -> None:
    """Descriptor が WAVEDescriptor (Summary=RIFF fmt) であること。"""
    out = tmp_path / "wd.aaf"
    build_aaf(_load_stems(stems_dir), out, title="wd")
    with aaf2.open(str(out)) as f:
        descs = []
        for mob in f.content.mobs:
            d = getattr(mob, "descriptor", None)
            if d is not None:
                descs.append(d)
        assert descs and all(type(d).__name__ == "WAVEDescriptor" for d in descs)
        for d in descs:
            summary = bytes(d["Summary"].value)
            assert summary[:4] == b"RIFF" and summary[8:12] == b"WAVE"
            channels = int.from_bytes(summary[22:24], "little")
            bits = int.from_bytes(summary[34:36], "little")
            assert (channels, bits) == (2, 24)


def test_build_aaf_48k(stems_dir: Path, tmp_path: Path) -> None:
    d = tmp_path / "stems48"
    d.mkdir()
    for name in ["vocals", "drums"]:
        _make_wav(d / f"{name}.wav", sr=48000)
    info = build_aaf({p.stem: p for p in d.glob("*.wav")}, tmp_path / "o48.aaf")
    assert info["sample_rate"] == 48000
    assert info["tracks"] == ["vocals", "drums"]


def test_build_aaf_pcm16(stems_dir: Path, tmp_path: Path) -> None:
    d = tmp_path / "s16"
    d.mkdir()
    _make_wav(d / "vocals.wav")
    info = build_aaf({"vocals": d / "vocals.wav"}, tmp_path / "o16.aaf",
                     subtype="PCM_16")
    assert info["sample_rate"] == SR
    # build_aaf 内で verify_aaf が走る。bits=16 で読み戻せることを明示確認
    from suno_cubase.aaf_builder import verify_aaf
    r = verify_aaf(tmp_path / "o16.aaf", expected_rate=SR)
    assert r["tracks"] == [{"name": "vocals", "sample_rate": SR,
                            "channels": 2, "bits": 16, "duration_sec": 1.0}]


def test_build_aaf_rejects_mixed_rates(stems_dir: Path, tmp_path: Path) -> None:
    d = tmp_path / "mixed"
    d.mkdir()
    _make_wav(d / "vocals.wav", sr=44100)
    _make_wav(d / "drums.wav", sr=48000)
    stems = {p.stem: p for p in d.glob("*.wav")}
    with pytest.raises(ValueError):
        build_aaf(stems, tmp_path / "bad.aaf")


def test_build_aaf_rejects_missing_file(tmp_path: Path) -> None:
    stems = {"vocals": tmp_path / "not_found.wav"}
    with pytest.raises(FileNotFoundError):
        build_aaf(stems, tmp_path / "x.aaf")
