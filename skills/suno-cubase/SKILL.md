---
name: suno-cubase
description: Separate a Suno song into stems and build a Cubase-ready AAF project file. Use when the user asks to stem-separate a Suno track, turn Suno audio into a Cubase project, or import Suno stems into Cubase.
---

# Suno → Cubase パイプライン

Suno 曲（音源ファイル、または Suno 公式 MCP で取得した曲）を 6 ステムに分離し、
Cubase に取り込める **AAF プロジェクトファイル**を生成する。処理本体はこの
リポジトリの CLI（`suno2cubase`）が担う。エージェントの役割は曲の特定、実行、
結果の確認と報告に限定する。

## 準備

- CLI はリポジトリの venv で実行する（既定: `~/dev/suno-cubase-pipeline`）。
  `.venv/bin/suno2cubase` が無い場合は `./setup.sh` を先に実行する。
- 分離は CPU で数分〜十数分かかる。開始前にユーザーへ目安を伝える。
- 出力先（既定 `output/`）に同名プロジェクトがある場合は、上書き前にユーザーへ確認する。

## Workflow

1. **曲を一つに特定する。** ユーザーの指定がローカルファイルならそのパスを使う。
   Suno 曲 ID・URL の指定があり Suno 公式 MCP が使える環境なら、`audio-retrieve` で
   メタデータと音源 URL を取得し、ダウンロードして WAV/MP3 を保存する。曲 ID は
   依頼の中で一つに統一し、一覧の順番だけで別の曲を選び直さない。取得できた
   曲名・スタイルは `--title` とユーザーへの報告に使う。利用可能な MCP ツールと
   認証は実行時に確認し、認証情報をファイルや Git に残さない。
2. **パイプラインを実行する。**

   ```sh
   .venv/bin/suno2cubase run /path/to/song.mp3 -o output --title "曲名"
   ```

   分離済みステムがある場合は `--stems-dir` で分離を省略できる。
   4 ステムでよい指定のときは `--model htdemucs`。
3. **結果を確認して報告する。** `analysis.json` と `report.md` を読み、
   BPM（推定）・尺・ステム別レベル・生成された AAF のパスを報告する。
   欠損や異常（無音ステム、極端に短いステム）があればそのまま伝える。
   実際の分離精度は推定であることを外さない。
4. **Cubase への取り込みを案内する。** [references/cubase-import.md](references/cubase-import.md)
   の手順を伝える。ユーザーが GUI 自動化ブリッジ（MIDI Remote / AX 経由の
   Cubase 制御環境）を持つ場合は、読み込みと保存を自動化できる旨を添える。

## Guardrails

- Suno 生成物の商用利用の可否は Suno の利用規約に従う。Skill 自体は判断しない。
- 分析・解析の失敗を隠さない。demucs のエラーはその理由とともに報告する。
- ユーザーの音源を外部サービスへアップロードしない（本パイプラインは完全ローカル）。
- BPM は推定値。Cubase のテンポとして断定しない。
