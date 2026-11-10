"""report.md 生成 — パイプライン成果物のまとめと Cubase 取り込み手順。"""

from __future__ import annotations

from pathlib import Path


def _fmt(v) -> str:
    if v is None:
        return "-"
    return str(v)


def render_report(result: dict) -> str:
    analysis = result["analysis"]
    aaf = result["aaf"]
    project_dir: Path = result["project_dir"]
    src = analysis.get("source") or {}
    bpm = src.get("bpm")
    sr = aaf["sample_rate"]

    lines: list[str] = []
    lines.append(f"# {analysis.get('title', 'song')} — Suno → Cubase パイプライン結果")
    lines.append("")
    lines.append("| 項目 | 値 |")
    lines.append("|---|---|")
    if src:
        lines.append(f"| 入力 | `{src.get('path', '-')}` |")
        lines.append(f"| 尺 | {src.get('duration_sec', '-')} 秒 |")
        lines.append(f"| BPM (推定) | {_fmt(bpm)} |")
        lines.append(f"| サンプルレート | {src.get('sample_rate', '-')} Hz |")
    lines.append(f"| 分離モデル | {analysis.get('model', '-')} |")
    lines.append(f"| ステム数 | {len(aaf['tracks'])} |")
    lines.append(f"| AAF | `{Path(aaf['path']).name}` ({sr} Hz / {aaf['duration_sec']} 秒) |")
    lines.append("")
    if src.get("sample_rate") and src["sample_rate"] != sr:
        lines.append(f"> ステムと AAF は demucs の出力レート (**{sr} Hz**) です。"
                     f"入力 ({src['sample_rate']} Hz) から自動的にリサンプルされています。")
        lines.append("")

    lines.append("## ステム")
    lines.append("")
    lines.append("| トラック | 尺 (秒) | Peak (dBFS) | RMS (dBFS) |")
    lines.append("|---|---:|---:|---:|")
    for name, s in sorted(analysis.get("stems", {}).items()):
        lines.append(f"| {name} | {s.get('duration_sec', '-')} "
                     f"| {s.get('peak_dbfs', '-')} | {s.get('rms_dbfs', '-')} |")
    lines.append("")

    lines.append("## Cubase への取り込み")
    lines.append("")
    lines.append("1. Cubase で新規プロジェクトを作成 (サンプルレートは "
                 f"**{sr} Hz** を推奨)")
    lines.append(f"2. メニュー「ファイル > 読み込み > AAF…」で "
                 f"`{Path(aaf['path'])}` を選ぶ")
    lines.append("3. ステムがトラックに並ぶ。必要ならトラック色・アイコンを調整")
    lines.append("4. 「ファイル > 保存」でプロジェクト (.cpr) として保存")
    lines.append("")
    lines.append("> AAF には音声が埋め込まれている。元の stems/ フォルダはバックアップ用。")
    lines.append("")
    lines.append("## Cubase 15/16 での読み込みについて (2026-11 検証)")
    lines.append("")
    lines.append("- v0.1.0 の構成では AAF 読み込み時に Cubase がクラッシュしましたが、"
                 "v0.2.0 から DaVinci Resolve 書き出しと同等の構成になり、"
                 "クラッシュせずトラック構成を読み込めます (Cubase 15 / 16.0.5 で確認)")
    lines.append("- ただし Cubase 16.0.5 の AAF インポーターは埋め込みメディアの解決に"
                 "不具合があり、クリップは未配置のまま残ります"
                 " (DaVinci Resolve 製 AAF でも同様のため Steinberg 側の問題)")
    lines.append("- 確実に音源まで入れる方法: Cubase の空プロジェクトに `stems/` フォルダの"
                 " WAV を「ファイル > 読み込み > オーディオファイル…」で直接読み込む")
    lines.append("- 詳細と自動化手順は skills/suno-cubase/references/cubase-import.md 参照")
    lines.append("")
    lines.append("## 注意")
    lines.append("")
    lines.append("- ステム分離は推定を含む。ボーカルとギター等の混在は完全には分かれない")
    lines.append("- Suno 生成物の商用利用は Suno の利用規約に従うこと")
    lines.append("- BPM は推定値。Cubase 側でテンポトラックに反映するかは任意")
    lines.append("")
    return "\n".join(lines)
