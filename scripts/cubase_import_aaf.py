#!/usr/bin/env python3
"""実験的: Cubase への AAF 取り込み自動化 (macOS, 画面ロック解除中のみ動作)。

cubase-midi-remote-api リポジトリの GUI 自動化プリミティブを借りて、
「ファイル > 読み込み > AAF...」→ ファイル選択までを実行する。
Cubase の AX 階層は特殊なため、パネル内部はキーボード経路 (Cmd+Shift+G) で操作する。
実行には Cubase が最前面に来られる状態 (ロック解除・ユーザーが他操作中でないこと) が必要。

使い方:
  python3 scripts/cubase_import_aaf.py <file.aaf> [--save-to DIR] [--shots DIR]

動作:
  1. Cubase をアクティブ化
  2. ファイル > 読み込み > AAF... を実行
  3. 「読み込み AAF」パネルに Cmd+Shift+G でパスを入力して開く
  4. 読み込み後のウィンドウ変化を報告 (--save-to があれば Cmd+S で保存まで)

注意: Cubase のバージョン・UI 言語・ダイアログ構成により失敗し得る。
失敗したら手動での読み込み (skills/suno-cubase/references/cubase-import.md) を使うこと。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_HINTS = [
    Path.home() / "dev" / "suno-cubase-pipeline",
    Path.home() / "dev" / "cubase-midi-remote-api",
]


def load_primitives():
    for base in REPO_HINTS:
        p = base / "gui_agent"
        if p.is_dir():
            sys.path.insert(0, str(base))
            from gui_agent import primitives as P  # noqa: PLC0415
            return P
    sys.exit("gui_agent プリミティブが見つかりません (~/dev/cubase-midi-remote-api)")


def shot(P, t, name: str, outdir: Path | None) -> None:
    if not outdir:
        return
    try:
        r = P.screenshot(t, name)
        print(f"  [shot] {r}")
    except Exception as e:  # noqa: BLE001
        print(f"  [shot 失敗] {e}")


def wait_window(P, t, needle: str, timeout: float = 15.0) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for w in P.list_windows(t):
            if needle in w.get("title", ""):
                return w
        time.sleep(0.5)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("aaf", help="読み込む AAF ファイル")
    ap.add_argument("--save-to", default=None,
                    help="読み込み後のプロジェクト保存先ディレクトリ (Cmd+S まで自動)")
    ap.add_argument("--shots", default=None, help="スクリーンショット保存先")
    ap.add_argument("--panel-title", default="読み込み AAF",
                    help="読み込みパネルのウィンドウタイトル (UI言語で変わる)")
    args = ap.parse_args()

    aaf = Path(args.aaf).expanduser().resolve()
    if not aaf.is_file():
        sys.exit(f"AAF がありません: {aaf}")
    outdir = Path(args.shots) if args.shots else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)

    P = load_primitives()
    t = P.find_app()
    print(f"target: pid={t.pid} {t.name}")

    # アクティブ化 (フォーカス保護が働く環境では失敗する → 手動で前面に出してから再実行)
    subprocess.run(["open", "-a", t.name], check=False)
    time.sleep(1.0)
    if not P.frontmost(t):
        try:
            P.ensure_frontmost(t)
        except Exception as e:  # noqa: BLE001
            print(f"警告: アクティブ化できません ({e}) — 手動でCubaseを前面にして再実行")
            return 2

    print("[1] ファイル > 読み込み > AAF... を実行")
    P.menu_press(t, ["ファイル", "読み込み", "AAF..."])
    panel = wait_window(P, t, args.panel_title)
    if not panel:
        sys.exit("読み込みパネルが出ません (メニュー名が違う可能性)")
    print(f"[2] パネル出現: {panel['title']}")
    shot(P, t, "panel_open", outdir)

    print("[3] Cmd+Shift+G でパス入力")
    P.send_key(t, "cmd+shift+g")
    time.sleep(1.0)
    P.type_text(t, str(aaf))
    time.sleep(0.5)
    P.send_key(t, "return")
    time.sleep(1.2)
    P.send_key(t, "return")  # 開く

    print("[4] 読み込み完了を待機…")
    deadline = time.time() + 120
    while time.time() < deadline:
        wins = [w["title"] for w in P.list_windows(t)]
        if args.panel_title not in wins:
            print(f"  パネルが閉じました: {wins}")
            break
        time.sleep(2.0)
    else:
        print("  タイムアウト — パネルが開いたままです。手動で確認してください。")
        shot(P, t, "timeout", outdir)
        return 3

    time.sleep(3.0)
    wins = [w["title"] for w in P.list_windows(t)]
    print(f"[5] 現在のウィンドウ: {wins}")
    shot(P, t, "after_import", outdir)

    if args.save_to:
        print(f"[6] Cmd+S → {args.save_to} に保存")
        P.send_key(t, "cmd+s")
        time.sleep(1.5)
        P.send_key(t, "cmd+shift+g")
        time.sleep(1.0)
        P.type_text(t, str(Path(args.save_to).expanduser().resolve()))
        time.sleep(0.5)
        P.send_key(t, "return")
        time.sleep(1.0)
        P.send_key(t, "return")
        time.sleep(2.0)
        shot(P, t, "after_save", outdir)
        print("  保存ウィンドウ/ファイルを確認してください")

    print("完了。Cubase の画面を確認してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
