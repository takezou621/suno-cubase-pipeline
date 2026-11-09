"""AAF ビルダー — ステムWAV群をトラックに並べた Cubase 用 AAF を生成する。

pyaaf2 で次の構造を作る (Pro Tools 由来 AAF と同系の構成):

  CompositionMob (Usage_TopLevel)  … Cubase がタイムラインとして読む本体
    ├ TimelineMobSlot "vocals" → SourceClip → MasterMob slot 1
    ├ … ステム数分
    └ MasterMob (Usage_LowerLevel)
         └ sound slot ×N → SourceMob (PCMDescriptor + 埋め込み EssenceData)

音声は AAF 内に埋め込む (16/24bit PCM)。Cubase の「ファイル > 読み込み > AAF」で
全ステムがトラックに配置され、メディアはプロジェクトの Pool にコピーされる。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Mapping

import aaf2
import soundfile as sf

from . import STEM_ORDER

SUPPORTED_SUBTYPES = ("PCM_16", "PCM_24")


def _to_pcm_wav(src: Path, dst: Path, subtype: str = "PCM_24") -> None:
    """任意のWAV/音声を AAF 埋め込み用の PCM WAV に変換する。"""
    data, sr = sf.read(str(src), dtype="int32", always_2d=True)
    sf.write(str(dst), data, sr, subtype=subtype)


def _ordered_names(stems: Mapping[str, Path]) -> list[str]:
    names = list(stems.keys())
    known = [s for s in STEM_ORDER if s in names]
    extra = sorted(s for s in names if s not in STEM_ORDER)
    return known + extra


def build_aaf(stems: Mapping[str, Path],
              out_path: str | Path,
              title: str = "song",
              subtype: str = "PCM_24") -> dict:
    """ステムWAV群からAAFを生成する。

    stems: {ステム名: WAVパス}。サンプルレートは全ステムで一致していること。
    戻り値: {"path", "sample_rate", "duration_sec", "tracks": [ステム名...]}
    """
    if not stems:
        raise ValueError("ステムが空です")
    if subtype not in SUPPORTED_SUBTYPES:
        raise ValueError(f"subtype は {SUPPORTED_SUBTYPES} のみ対応: {subtype}")

    names = _ordered_names(stems)
    for name in names:
        if not Path(stems[name]).is_file():
            raise FileNotFoundError(f"ステムWAVがありません: {name} -> {stems[name]}")

    rates = {int(sf.info(str(stems[n])).samplerate) for n in names}
    if len(rates) != 1:
        raise ValueError(f"ステム間でサンプルレートが不一致です: {rates}")
    sample_rate = rates.pop()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="suno2cubase-pcm-") as tmp:
        pcm_paths: dict[str, Path] = {}
        for name in names:
            pcm = Path(tmp) / f"{name}.wav"
            _to_pcm_wav(Path(stems[name]), pcm, subtype)
            pcm_paths[name] = pcm

        with aaf2.open(str(out_path), "w") as f:
            master = f.create.MasterMob(title)
            master.usage = "Usage_LowerLevel"
            master["AppCode"].value = 1
            f.content.mobs.append(master)

            slot_ids: dict[str, int] = {}
            lengths: dict[str, int] = {}
            for name in names:
                slot = master.import_audio_essence(str(pcm_paths[name]), sample_rate)
                slot.name = name
                slot.segment.mob.name = name
                slot_ids[name] = slot.slot_id
                lengths[name] = slot.segment.length

            comp = f.create.CompositionMob(title)
            comp.usage = "Usage_TopLevel"
            f.content.mobs.append(comp)

            for name in names:
                ts = comp.create_sound_slot(sample_rate)
                ts.name = name
                ts.segment = master.create_source_clip(slot_ids[name],
                                                       length=lengths[name])

    duration_sec = round(max(lengths.values()) / sample_rate, 3)
    return {
        "path": out_path,
        "sample_rate": sample_rate,
        "duration_sec": duration_sec,
        "tracks": names,
    }
