"""suno2cubase CLI — Suno音源からステム分離し Cubase 用 AAF を作る。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .aaf_builder import build_aaf
from .analysis import analyze_source, analyze_stems
from .project import collect_stems, run_pipeline, sanitize_title
from .report import render_report
from .separation import DEFAULT_MODEL, MODEL_STEMS


def _add_model_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"分離モデル (既定: {DEFAULT_MODEL} / 対応: {', '.join(MODEL_STEMS)})")


def cmd_run(args: argparse.Namespace) -> int:
    audio = Path(args.audio)
    print(f"[1/4] 入力: {audio}")
    result = run_pipeline(
        audio,
        out_root=args.out,
        title=args.title,
        model=args.model,
        device=args.device,
        segment=args.segment,
        stems_dir=args.stems_dir,
        overwrite=args.force,
        subtype=args.subtype,
    )
    project_dir: Path = result["project_dir"]
    aaf = result["aaf"]

    print("[2/4] 解析 … 完了")
    bpm = (result["analysis"].get("source") or {}).get("bpm")
    if bpm is not None:
        print(f"      BPM(推定)={bpm}  SR={aaf['sample_rate']}Hz  "
              f"尺={aaf['duration_sec']}秒")

    print("[3/4] AAF 生成 …")
    print(f"      {aaf['path']}")

    print("[4/4] レポート生成 …")
    report_path = project_dir / "report.md"
    report_path.write_text(render_report(result), encoding="utf-8")

    print()
    print("== 完了 ==")
    print(f"  プロジェクト: {project_dir}")
    print()
    print("Cubase への取り込み:")
    print(f"  1. 新規プロジェクト (サンプルレート {aaf['sample_rate']} Hz 推奨)")
    print(f"  2. ファイル > 読み込み > AAF… で {aaf['path']} を選択")
    print("  3. 保存で .cpr 化")
    return 0


def cmd_separate(args: argparse.Namespace) -> int:
    from .separation import separate_stems

    sep = separate_stems(args.audio, args.out, model=args.model,
                         device=args.device, segment=args.segment)
    print(f"分離完了: {sep['track_dir']}")
    for name, path in sep["stems"].items():
        print(f"  {name:8s} {path}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    out: dict = {"source": analyze_source(args.audio)}
    if args.stems:
        stems = collect_stems(args.stems)
        out["stems"] = analyze_stems(stems)
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
        print(f"書き込み: {args.json}")
    else:
        print(text)
    return 0


def cmd_build_aaf(args: argparse.Namespace) -> int:
    stems = collect_stems(args.stems_dir)
    title = sanitize_title(args.title or Path(args.stems_dir).name)
    info = build_aaf(stems, args.out, title=title, subtype=args.subtype)
    print(f"AAF を生成: {info['path']}")
    print(f"  トラック: {', '.join(info['tracks'])}")
    print(f"  {info['sample_rate']} Hz / {info['duration_sec']} 秒")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="suno2cubase",
        description="Suno音源をステム分離し、Cubase用のAAFを生成する")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="分離 → 解析 → AAF生成 → レポートまで一括実行")
    p.add_argument("audio", help="入力音声 (wav/mp3/flac/m4a など)")
    p.add_argument("-o", "--out", default="output", help="出力ルート (既定: output/)")
    p.add_argument("--title", help="曲名 (既定: ファイル名)")
    p.add_argument("--device", default="cpu", help="demucs のデバイス (既定: cpu)")
    p.add_argument("--segment", type=float, default=None,
                   help="demucs のセグメント長 (VRAM/メモリ不足時は小さく)")
    p.add_argument("--stems-dir", default=None,
                   help="既存ステムWAVフォルダを指定して分離をスキップ")
    p.add_argument("--force", action="store_true",
                   help="出力先に既にプロジェクトがある場合に上書きする")
    p.add_argument("--subtype", default="PCM_24", choices=["PCM_16", "PCM_24"],
                   help="埋め込み音声のビット深度 (既定: PCM_24)")
    _add_model_arg(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("separate", help="ステム分離のみ実行")
    p.add_argument("audio", help="入力音声")
    p.add_argument("-o", "--out", default="output", help="出力ルート")
    p.add_argument("--device", default="cpu", help="デバイス (既定: cpu)")
    p.add_argument("--segment", type=float, default=None, help="セグメント長")
    _add_model_arg(p)
    p.set_defaults(func=cmd_separate)

    p = sub.add_parser("analyze", help="BPM・尺・レベル統計の解析")
    p.add_argument("audio", help="入力音声")
    p.add_argument("--stems", default=None, help="ステムWAVフォルダ (任意)")
    p.add_argument("--json", default=None, help="結果の書き込み先 JSON")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("build-aaf", help="ステムWAVフォルダからAAFのみ生成")
    p.add_argument("stems_dir", help="ステムWAVが入ったフォルダ")
    p.add_argument("-o", "--out", default="project.aaf", help="出力AAFパス")
    p.add_argument("--title", default=None, help="曲名 (既定: フォルダ名)")
    p.add_argument("--subtype", default="PCM_24", choices=["PCM_16", "PCM_24"],
                   help="埋め込み音声のビット深度 (既定: PCM_24)")
    p.set_defaults(func=cmd_build_aaf)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    except FileExistsError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 4
    except (OSError, RuntimeError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
