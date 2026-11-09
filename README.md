# suno-cubase-pipeline

Suno で作曲した音源を **6 ステムに分離**し、**Cubase 用の AAF プロジェクトファイル**を
生成するローカル CLI です。Cubase の「ファイル > 読み込み > AAF」で全ステムが
トラックに並んだ状態のプロジェクトを作れます。音声・モデル・音源はすべてローカルで処理され、
外部へ送信されません。

```text
Suno音源 (wav/mp3) ──► demucs htdemucs_6s ──► 6ステムWAV ──► pyaaf2 ──► <曲名>.aaf
                     (vocals/drums/bass/                              (音声埋め込み)
                      guitar/piano/other)                      Cubase: 読み込み > AAF
                                                                    └► トラック6本 + Pool → .cpr 保存
```

## なぜ AAF か

Cubase 13 以降のプロジェクトファイル (.cpr) は独自バイナリ形式 (RIF2) のため、
外部ツールからの直接生成は非現実的です。そこで本ツールは:

- ステムを**音声ごと AAF に埋め込み**、Cubase に「読み込み」させます
- Cubase 側はトラック配置・Pool 登録・サンプルレートをネイティブに解釈します
- 読み込み後「保存」すれば、**Cubase 自身が作った完全な .cpr** になります
- AAF は Cubase Pro / Artist の AAF 読み込み (Cubase 12 以降で対応) で開けます

Cubase での詳細な手順は [skills/suno-cubase/references/cubase-import.md](skills/suno-cubase/references/cubase-import.md) を参照してください。

## 必要な環境

| 項目 | 内容 |
|---|---|
| OS / CPU | macOS (Apple Silicon で検証) / Linux / Windows。分離は CPU で動作 (GPU があると速い) |
| Python | 3.10〜3.12 ([uv](https://docs.astral.sh/uv/) での 3.12 venv 構築を推奨) |
| demucs | v4 系 (`pip install demucs`)。初回実行時にモデル重み (~320MB) を自動取得 |
| ffmpeg | PATH にあること (mp3/m4a 入力や demucs の内部処理で使用) |
| Cubase | AAF 読み込みに対応する版 (Pro / Artist。実機検証は Cubase 16 Pro) |

分離エンジンは [Demucs v4 (htdemucs_6s)](https://github.com/facebookresearch/demucs) (MIT)、
AAF 生成は [pyaaf2](https://github.com/markreidvfx/pyaaf2) (MIT) を使用しています。

Apple M4 の CPU で 3〜4 分曲を分離する場合、数分〜十数分かかります。
短い試聴用クリップで確認してから全編を実行することを推奨します。

## セットアップ

```sh
git clone <this repo>
cd suno-cubase-pipeline
./setup.sh
```

## 使い方

### 1. 一括実行 (分離 → 解析 → AAF → レポート)

```sh
.venv/bin/suno2cubase run /path/to/suno_song.mp3 -o output --title "My Song"
```

出力構成:

```text
output/My_Song/
├── stems/htdemucs_6s/My_Song/   vocals.wav drums.wav bass.wav guitar.wav piano.wav other.wav
├── cubase/My_Song.aaf           ← Cubase に読み込むファイル (音声埋め込み)
├── analysis.json                BPM(推定)・尺・ステム別レベル統計
└── report.md                    結果まとめと取り込み手順
```

### 2. サブコマンド

| コマンド | 役割 |
|---|---|
| `run` | 分離 → 解析 → AAF 生成 → レポートまで一括 |
| `separate` | ステム分離のみ (`--model htdemucs` で 4 ステムも可) |
| `analyze` | BPM・尺・レベル統計のみ (`--json` で保存) |
| `build-aaf` | 既存ステムWAVフォルダから AAF のみ生成 |

分離済みのステムから始める場合:

```sh
.venv/bin/suno2cubase run song.wav --stems-dir /path/to/stems -o output
```

### 3. Skill として使う (Suno MCP 連携)

Claude Code / Codex 用の Skill を同梱しています。
`skills/suno-cubase/` を `~/.claude/skills/` または `~/.codex/skills/` に配置すると、
「この Suno の曲を Cubase 用にステム分離して」のような依頼で:

1. Suno 公式 MCP (`audio-retrieve`) で曲を特定し、音源とメタデータ (曲名・スタイル等) を取得
2. 音源をダウンロードして本 CLI を実行
3. `analysis.json` / `report.md` の内容と Cubase への取り込み手順を報告

までをエージェントが行います。詳細は [skills/suno-cubase/SKILL.md](skills/suno-cubase/SKILL.md) を参照してください。

## テスト

```sh
.venv/bin/python -m pytest tests -v
```

テストは合成音のみを使用し、モデルのダウンロードや Cubase の起動は行いません。

## 制約と注意

- **ステム分離は推定です。** ボーカルとギターなど帯域が重なる音源は完全には分かれません。
  分離結果の音質は Demucs の特性と元音源に依存します。
- **BPM は推定値です。** 倍 / 半テンポの曖昧さがあります。Cubase のテンポトラックへ
  反映するかどうかは任意です (現在はテンポは書き込んでいません)。
- **Suno 生成物の権利処理は Suno の利用規約に従ってください。** 本ツールは
  手元の音源を加工するだけであり、利用権を付与するものではありません。
- AAF の音声は **16/24bit PCM に量子化して埋め込みます** (既定 24bit)。
  32bit float のステム WAV は `stems/` に元のまま保存されます。
- 商用利用の可否は、Suno のプラン規約と各モデルの配布条件を必ず確認してください。

## リポジトリ構成

```text
src/suno_cubase/
├── cli.py           コマンド定義 (suno2cubase)
├── separation.py    demucs CLI ラッパ
├── analysis.py      BPM・レベル統計
├── aaf_builder.py   AAF 生成 (pyaaf2) + 生成後の内部検証
├── project.py       出力構成・パイプライン
└── report.py        report.md 生成
skills/suno-cubase/  Claude Code / Codex 用 Skill
scripts/             cubase_import_aaf.py (実験的: GUI自動化での取り込み補助)
tests/               合成音による単体テスト
```

## ライセンス

本リポジトリのコードは MIT License です。依存する demucs / pyaaf2 / モデル重みや、
Suno のサービス・生成物・Cubase の権利はそれぞれの提供元の条件に従います。
