"""AAF ビルダー — ステムWAV群をトラックに並べた Cubase 用 AAF を生成する。

DaVinci Resolve 書き出し AAF と同等の構成で作る。pyaaf2 既定の構造は
Cubase 15/16 の AAFfilter をクラッシュさせるため、次の差分を適用している:

  CompositionMob (Usage_TopLevel)
    ├ TimelineMobSlot (Timecode, 25fps, Start=86400)
    ├ TimelineMobSlot "vocals" (PhysicalTrackNumber) → Sequence{SourceClip}
    │     → MasterMob slot → SourceMob (WAVEDescriptor + Summary=RIFF fmt)
    └ … ステム数分

essence は WAV ファイル形式 (RIFF ヘッダ付き) で埋め込む。
Cubase 15/16 はこの構成でクラッシュせずトラックを生成する
(メディア実体の読み込みは Cubase 16.0.5 のインポーター自体の不具合あり、issue #1 参照)。
"""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path
from typing import Mapping

import aaf2
import soundfile as sf

from . import STEM_ORDER

SUPPORTED_SUBTYPES = ("PCM_16", "PCM_24")


def verify_aaf(path: str | Path, expected_rate: int | None = None) -> dict:
    """生成後のAAF内部整合性を検査する。

    CompositionMob(TopLevel) / Timecode+Soundスロット / WAVEDescriptor /
    埋め込みEssenceData(WAV形式)の長さを確認する。壊れたAAFをCubaseに渡さないためのゲート。
    """
    with aaf2.open(str(path)) as f:
        mobs = list(f.content.mobs)
        comps = [m for m in mobs if type(m).__name__ == "CompositionMob"
                 and str(m.usage) == "Usage_TopLevel"]
        if len(comps) != 1:
            raise ValueError(f"TopLevel CompositionMob が1つではありません: {len(comps)}")
        comp = comps[0]
        masters = [m for m in mobs if type(m).__name__ == "MasterMob"]
        if len(masters) != 1:
            raise ValueError(f"MasterMob が1つではありません: {len(masters)}")
        master = masters[0]

        essence_map = {ed.mob_id: ed for ed in f.content.essencedata}
        tracks = []
        for slot in comp.slots:
            if str(slot.media_kind).lower() == "timecode":
                continue
            if str(slot.media_kind).lower() != "sound":
                raise ValueError(f"slot {slot.name} の media_kind が sound ではありません")
            seq = slot.segment
            clips = [c for c in getattr(seq, "components", [])
                     if type(c).__name__ == "SourceClip"]
            if not clips:
                raise ValueError(f"slot {slot.name}: SourceClip がありません")
            clip = clips[0]
            # CompositionMob slot → MasterMob slot → SourceMob
            mslot = master.slot_at(clip.slot_id)
            seg = mslot.segment
            mclips = (getattr(seg, "components", None) or [seg])
            src_clip = next((c for c in mclips
                             if type(c).__name__ == "SourceClip"), mclips[0])
            src_mob = src_clip.mob
            d = src_mob.descriptor
            sr = int(d["SampleRate"].value)
            summary = bytes(d["Summary"].value)
            if summary[:4] != b"RIFF" or summary[8:12] != b"WAVE":
                raise ValueError(f"slot {slot.name}: Summary が RIFF ヘッダではありません")
            channels = struct.unpack("<H", summary[22:24])[0]
            bits = struct.unpack("<H", summary[34:36])[0]
            data_size = struct.unpack("<I", summary[40:44])[0]
            frames = int(d.length)
            if expected_rate is not None and sr != expected_rate:
                raise ValueError(f"slot {slot.name}: SR不一致 {sr} != {expected_rate}")
            if bits not in (16, 24):
                raise ValueError(f"slot {slot.name}: bits={bits} は未対応")
            ed = essence_map.get(src_mob.mob_id)
            if ed is None:
                raise ValueError(f"slot {slot.name}: EssenceData が埋め込まれていません")
            block_align = channels * (bits // 8)
            stream = ed.open("r")
            stream.seek(0, 2)
            size = stream.tell()
            stream.close()
            if size != 44 + data_size:
                raise ValueError(
                    f"slot {slot.name}: EssenceData長不一致 {size} != 44+{data_size}")
            if data_size != frames * block_align:
                raise ValueError(
                    f"slot {slot.name}: データ長不一致 {data_size} != {frames}x{block_align}")
            tracks.append({"name": slot.name, "sample_rate": sr,
                           "channels": channels, "bits": bits,
                           "duration_sec": round(frames / sr, 3)})
        if not tracks:
            raise ValueError("sound slot がありません")
    return {"tracks": tracks}


def _to_pcm_wav(src: Path, dst: Path, subtype: str = "PCM_24") -> None:
    """任意のWAV/音声を AAF 埋め込み用の PCM WAV に変換する。"""
    data, sr = sf.read(str(src), dtype="int32", always_2d=True)
    sf.write(str(dst), data, sr, subtype=subtype)


def _ordered_names(stems: Mapping[str, Path]) -> list[str]:
    names = list(stems.keys())
    known = [s for s in STEM_ORDER if s in names]
    extra = sorted(s for s in names if s not in STEM_ORDER)
    return known + extra


def _wav_summary_and_essence(pcm_path: Path) -> tuple[bytes, bytes, int]:
    """PCM WAV から (Summary=標準RIFFヘッダ44B, 埋め込みessence=WAV全体, frames) を得る。

    libsndfile が書く 24bit WAV は fmt 18 バイト (extensible) のためチャンクを
    歩行して取り出し、DaVinci Resolve と同一の標準 44 バイトヘッダを再構成する。
    """
    blob = pcm_path.read_bytes()
    if blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
        raise ValueError(f"WAV 形式ではありません: {pcm_path}")
    pos = 12
    fmt = None
    data = None
    while pos + 8 <= len(blob):
        cid = blob[pos:pos + 4]
        size = struct.unpack("<I", blob[pos + 4:pos + 8])[0]
        payload = blob[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt = payload
        if cid == b"data":
            data = payload
            break
        pos += 8 + size + (size & 1)
    if fmt is None or data is None or len(fmt) < 16:
        raise ValueError(f"WAV チャンク解析に失敗しました: {pcm_path}")
    channels = struct.unpack("<H", fmt[2:4])[0]
    sr = struct.unpack("<I", fmt[4:8])[0]
    block_align = struct.unpack("<H", fmt[12:14])[0]
    bits = struct.unpack("<H", fmt[14:16])[0]
    frames = len(data) // block_align if block_align else 0
    summary = (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt "
               + struct.pack("<I", 16)
               + struct.pack("<HHIIHH", 1, channels, sr, sr * block_align,
                             block_align, bits)
               + b"data" + struct.pack("<I", len(data)))
    essence = summary + data
    return summary, essence, frames


def build_aaf(stems: Mapping[str, Path],
              out_path: str | Path,
              title: str = "song",
              subtype: str = "PCM_24") -> dict:
    """ステムWAV群からAAFを生成する。

    stems: {ステム名: WAVパス}。サンプルレートは全ステムで一致していること。
    構成は DaVinci Resolve 書き出し AAF と同等 (Timecode slot + WAVEDescriptor +
    PhysicalTrackNumber + 埋め込み WAV essence)。pyaaf2 既定の構造は Cubase 15/16
    の AAFfilter をクラッシュさせるためこの構成を使う (issue #1 参照)。

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

    lengths: dict[str, int] = {}

    with tempfile.TemporaryDirectory(prefix="suno2cubase-pcm-") as tmp:
        pcm_paths: dict[str, Path] = {}
        for name in names:
            pcm = Path(tmp) / f"{name}.wav"
            _to_pcm_wav(Path(stems[name]), pcm, subtype)
            pcm_paths[name] = pcm

        with aaf2.open(str(out_path), "w") as f:
            # pyaaf2 既定の OperationalPattern は付けない (DaVinci Resolve と同一に)
            try:
                del f.header["OperationalPattern"]
            except Exception:
                pass
            try:
                f.header["Version"].value = {"major": 1, "minor": 1}
            except Exception:
                pass

            master = f.create.MasterMob(title)
            master.usage = "Usage_LowerLevel"
            f.content.mobs.append(master)

            master_slots: list[tuple[object, int, str]] = []
            for name in names:
                pcm = pcm_paths[name]
                summary, essence, frames = _wav_summary_and_essence(pcm)
                lengths[name] = frames

                src = f.create.SourceMob()
                src.name = name
                f.content.mobs.append(src)
                d = f.create.WAVEDescriptor()
                d["SampleRate"].value = sample_rate
                d["Summary"].value = summary
                d["Length"].value = frames
                d.length = frames
                src.descriptor = d
                sslot = src.create_sound_slot(edit_rate=sample_rate)
                sslot["PhysicalTrackNumber"].value = 1
                sslot.segment.length = frames
                mslot = master.create_sound_slot(edit_rate=sample_rate)
                mslot["PhysicalTrackNumber"].value = len(master_slots) + 1
                clip = src.create_source_clip(sslot.slot_id, media_kind="sound")
                clip.length = frames
                mslot.segment = clip
                master_slots.append((mslot, frames, name))

                ed = f.create.EssenceData()
                ed.mob_id = src.mob_id
                f.content.essencedata.append(ed)
                stream = ed.open("w")
                stream.write(essence)
                stream.close()

            comp = f.create.CompositionMob(title)
            comp.usage = "Usage_TopLevel"
            f.content.mobs.append(comp)

            # Timecode slot (slot 1) — Cubase がタイムライン起点として読む
            total_frames = max(lengths.values())
            tc_len = int(total_frames / sample_rate * 25)
            tcslot = comp.create_empty_sequence_slot(edit_rate=25,
                                                     media_kind="Timecode")
            tc = f.create.Timecode(fps=25, length=tc_len)
            tc["Start"].value = 86400
            tcslot.segment = tc

            # sound slots (slot 2..): Sequence{SourceClip} + PhysicalTrackNumber
            for i, (mslot, frames, name) in enumerate(master_slots):
                ts = comp.create_empty_sequence_slot(edit_rate=sample_rate,
                                                     media_kind="sound")
                ts.name = name
                ts["PhysicalTrackNumber"].value = i + 1
                ts.segment.length = frames
                clip = master.create_source_clip(mslot.slot_id,
                                                 media_kind="sound")
                clip.length = frames
                ts.segment.components.append(clip)

    # 書き込み直後に内部整合性を検査してから返す
    verify_aaf(out_path, expected_rate=sample_rate)

    duration_sec = round(max(lengths.values()) / sample_rate, 3)
    return {
        "path": out_path,
        "sample_rate": sample_rate,
        "duration_sec": duration_sec,
        "tracks": names,
    }
