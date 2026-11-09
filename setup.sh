#!/bin/sh
# セットアップ — uv で Python 3.12 の venv を作り、依存を入れる。
# 既存の CUDA 環境を持つ Windows 等では、torch だけ各自の環境に合わせて入れてから
# `uv pip install --python .venv/bin/python -e ".[separate]"` を実行してもよい。
set -e
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv が見つかりません。https://docs.astral.sh/uv/ から導入するか、"
  echo "python3 -m venv .venv と pip install -e '.[separate]' を手動で実行してください。"
  exit 1
fi

uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[separate,dev]"

echo
echo "完了。次のコマンドで確認できます:"
echo "  .venv/bin/suno2cubase --help"
echo "初回の分離実行時に demucs のモデル重み (~320MB) をダウンロードします。"
