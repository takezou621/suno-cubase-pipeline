"""AAF生成プロトタイプ — 6ステムをトラックに並べたAAFを pyaaf2 で作る。

Cubase の「ファイル > 読み込み > AAF」を想定した構造:
  CompositionMob (Usage_TopLevel)  … タイムライン本体。6つの TimelineMobSlot
    └ SourceClip → MasterMob (Usage_LowerLevel) の各 sound slot
         └ SourceMob (PCMDescriptor, 埋め込み EssenceData)
"""
from __future__ import annotations

import fractions
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import aaf2

STEM_NAMES = ["vocals", "drums", "bass", "guitar", "piano", "other"]


def make_test_wavs(out_dir: Path, sr: int = 44100, sec: float = 3.0) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0, sec, int(sr * sec), endpoint=False)
    freqs = {"vocals": 440, "drums": 110, "bass": 82, "guitar": 330, "piano": 261, "other": 523}
    paths = []
    for name in STEM_NAMES:
        tone = 0.4 * np.sin(2 * np.pi * freqs[name] * t)
        stereo = np.stack([tone, tone], axis=1).astype(np.float32)
        src = out_dir / f"{name}_f32.wav"
        sf.write(src, stereo, sr, subtype="FLOAT")
        dst = out_dir / f"{name}.wav"  # 24bit PCM に揃える
        data, _ = sf.read(src, dtype="int32")
        sf.write(dst, data, sr, subtype="PCM_24")
        src.unlink()
        paths.append(dst)
    return paths


def build_aaf(wavs: list[Path], out_path: Path, name: str = "test_song",
              edit_rate: int = 44100) -> Path:
    with aaf2.open(str(out_path), "w") as f:
        master = f.create.MasterMob(name)
        master.usage = "Usage_LowerLevel"
        master["AppCode"].value = 1
        f.content.mobs.append(master)

        lengths = []
        slot_ids = []
        for wav in wavs:
            slot = master.import_audio_essence(str(wav), edit_rate)
            stem = wav.stem
            slot.name = stem
            src_mob = slot.segment.mob
            src_mob.name = stem
            slot_ids.append(slot.slot_id)
            lengths.append(slot.segment.length)

        comp = f.create.CompositionMob(name)
        comp.usage = "Usage_TopLevel"
        f.content.mobs.append(comp)

        for stem, slot_id, length in zip([w.stem for w in wavs], slot_ids, lengths):
            ts = comp.create_sound_slot(edit_rate)
            ts.name = stem
            ts.segment = master.create_source_clip(slot_id, length=length)
    return out_path


def dump_aaf(path: Path) -> None:
    with aaf2.open(str(path)) as f:
        print("== mobs ==")
        for mob in f.content.mobs:
            print(f"  {type(mob).__name__} name={mob.name!r} usage={mob.usage.get() if 'usage' in mob else None}")
            for slot in mob.slots:
                seg = slot.segment
                length = getattr(seg, "length", None)
                print(f"    slot={slot.slot_id} name={slot.name!r} kind={slot.media_kind} "
                      f"rate={slot.edit_rate} len={length} seg={type(seg).__name__}")
        print("== essencedata ==", len(list(f.content.essencedata)))


def main() -> None:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "output/prototype")
    wavs = make_test_wavs(out_dir / "stems")
    aaf_path = build_aaf(wavs, out_dir / "test_song.aaf")
    print("wrote", aaf_path, aaf_path.stat().st_size, "bytes")
    dump_aaf(aaf_path)


if __name__ == "__main__":
    main()
