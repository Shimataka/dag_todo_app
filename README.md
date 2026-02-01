# Dandori（段ドリ）

DAG（有向非巡回グラフ）で依存関係を管理するタスク管理システム。

## 特徴

- **多親・多子DAG**: 1つのタスクが複数の親・子を持つことが可能
- **厳格ブロック無し**: 親タスクが完了していなくても着手可能（ガイドとして依存関係を表示）
- **間に挿入**: 既存のエッジ（A→B）に対して新タスクCを挿入（A→C→B）する操作をサポート
- **木単位アーカイブ**: 連結成分（ツリー）単位でアーカイブ/復元が可能（`is_archived`フラグで非破壊）
- **ストレージ切替**: YAML（PyYAML）とSQLite（標準ライブラリ）の2ドライバを同一インターフェースで切替可能
- **サイクル検出**: エッジ追加時に自動でサイクルを検出し、DAGの整合性を保証

## インストール

### 要件

- Python >=3.13
- PyYAML >=6.0.1
- [PyResults](https://github.com/Shimataka/resulttype_python) >=0.2.0

### セットアップ

```bash
# リポジトリをクローン
git clone <repository-url>
cd dag_todo_app

# 依存関係のインストール（uv推奨）
uv sync

# または pip を使用
pip install -e .
```

## 設定

本ツールには、`USERNAME`、`PROFILE`、`DATA_PATH`、`ARCHIVE_PATH` の4つの変数が設定可能です。
これらの変数は、次の順に決定されるため、必ずしも全ての変数を設定する必要はありません。

- `USERNAME` の場合：
    1. CLI コマンドで `--username` オプションを指定した場合
    2. OS環境変数 `DD_USERNAME` で設定した場合
    3. OS環境変数 `DD_HOME_DIR` にある設定ファイル `config.env` で `USERNAME` キーで設定した場合
    4. Python標準ライブラリによる `getpass.getuser()` で取得したユーザー名
    5. デフォルト値 `anonymous`

- `PROFILE` の場合：
    1. CLI コマンドで `--profile` オプションを指定した場合
    2. OS環境変数 `DD_PROFILE` で設定した場合
    3. OS環境変数 `DD_HOME_DIR` にある設定ファイル `config.env` で `PROFILE` キーで設定した場合
    4. デフォルト値 `default`

- `DATA_PATH` の場合：
    1. OS環境変数 `DD_DATA_PATH` で設定した場合
    2. OS環境変数 `DD_HOME_DIR` にある設定ファイル `config.env` で `DATA_PATH` キーで設定した場合
    3. デフォルト値 `~/.dandori/tasks.yaml` or `~/.dandori/<PROFILE>/tasks.yaml`

- `ARCHIVE_PATH` の場合：
    1. OS環境変数 `DD_ARCHIVE_PATH` で設定した場合
    2. OS環境変数 `DD_HOME_DIR` にある設定ファイル `config.env` で `ARCHIVE_PATH` キーで設定した場合
    3. デフォルト値 `~/.dandori/archive.yaml` or `~/.dandori/<PROFILE>/archive.yaml`

## 基本的な使い方

- CLI コマンドの使い方は [CLI コマンド](docs/cli.md) を参照。
- TUI の使い方は [TUI](docs/tui.md) を参照。

## アーキテクチャ

### ディレクトリ構成

```text
src/dandori/
  api/                  # API実装 (将来拡張予定)
    server.py           # HTTPサーバ実装
  core/                 # ドメインモデルとコアロジック
    models.py           # Task/Edge のデータクラス
    ops.py              # コア操作ロジック
    sort.py             # ソート処理
    validate.py         # サイクル検出・整合性チェック
  interfaces/           # 外部インターフェース
    cli.py              # CLI実装
    tui/                # TUI実装
      app.py            # アプリケーションメイン
      data.py           # アプリケーションデータ
      endpoint.py       # エンドポイント
      helper.py         # ヘルパー
      style.py          # スタイル
      view.py           # ビュー
  io/                   # 入出力
    json_io.py          # JSONエクスポート/インポート
    std_io.py           # 標準出力フォーマット
  storage/              # ストレージ層
    base.py             # Storage インターフェース
    sqlite3_store.py    # SQLite実装
    yaml_store.py       # YAML実装
  util/                 # ユーティリティ
    dirs.py             # ディレクトリ関連
    ids.py              # ID生成
    time.py             # 日時処理
    logger.py           # ロギング
    meta_parser.py      # メタデータパーサ
```

### ストレージ層

現在はYAMLとSQLiteの2つのストレージを実装。
DBファイルの拡張子が `.yaml` の場合は YAML ストレージ、
`.db` の場合は SQLite ストレージを使用する。

ストレージは `Storage` インターフェースを実装し、以下のメソッドを提供：

- `load()`: グラフを読み込み
- `save()`: グラフを保存
- `get_task()`: タスク取得
- `get_all_tasks()`: 全タスク取得
- `add_task()`: タスク追加
- `update_task()`: タスク更新
- `remove_task()`: タスク削除
- `link_tasks()`: エッジの追加
- `unlink_tasks()`: エッジの削除
- `archive_tasks()`: 連結成分のアーカイブ
- `unarchive_tasks()`: 連結成分の復元
- `weakly_connected_component()`: 弱連結成分の取得
- `get_dependency_info()`: 依存関係情報の取得
- `insert_task()`: 間に挿入操作

## データモデル

### Task

```python
Task(
    id: str                    # UUID(v4)_日時_ユーザー名形式
    title: str                 # タイトル
    description: str           # 説明
    priority: int              # 優先度（高いほど優先）
    due_date: str | None       # 期限
    start_date: str | None     # 開始日
    status: str                # status
    # pending / in_progress / done / requested / removed
    depends_on: list[str]      # 親タスクIDのリスト
    children: list[str]        # 子タスクIDのリスト
    is_archived: bool          # アーカイブフラグ
    assigned_to: str | None    # 担当者
    requested_by: str | None   # 依頼者
    requested_at: str | None   # 依頼日時
    requested_note: str | None # 依頼メモ
    created_at: str            # 作成日時
    updated_at: str            # 更新日時
    tags: list[str]            # タグのリスト
    metadata: dict[str, Any]   # メタデータの辞書
)
```

### ソート順

デフォルトのソート順：

1. `start_date`（nullは現在時刻として扱う）
2. `priority`（降順）
3. `created_at`（昇順）
4. `id`（昇順）

`--topo` オプションでトポロジカル順序で表示可能。

## 開発

### テスト

```bash
# テスト実行
pytest

# カバレッジ付き
pytest --cov=src/dandori
```

### コード品質

```bash
# 型チェック
ty check src/

# リント
ruff check src/
```

## ロードマップ

- [x] テスト & リファクタリング
- [x] 共有・配布フロー（JSONテンプレ・インポートモード）
- [x] TUI 実装
- [ ] REST API 実装

## ライセンス

MIT License
