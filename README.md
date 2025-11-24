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

### 環境変数を設定

```bash
export DD_HOME_DIR=~/.dandori  # デフォルトは ~/.dandori
export DD_USERNAME=your_username  # デフォルトは anonymous
export DD_DATA_PATH=~/.dandori/tasks.yaml  # デフォルトは $DD_HOME_DIR/tasks.yaml
export DD_ARCHIVE_PATH=~/.dandori/archive.yaml  # デフォルトは $DD_HOME_DIR/archive.yaml
```

### 設定ファイルの作成

[OS環境変数](#環境変数を設定)に上書きされるので注意

```bash
# $DD_HOME_DIR/config.env を作成
touch $DD_HOME_DIR/config.env
echo "DD_USERNAME=your_username" >> $DD_HOME_DIR/config.env
echo "DD_DATA_PATH=$DD_DATA_PATH" >> $DD_HOME_DIR/config.env
echo "DD_ARCHIVE_PATH=$DD_ARCHIVE_PATH" >> $DD_HOME_DIR/config.env
```

## 基本的な使い方

- CLI コマンドの使い方は [CLI コマンド](docs/cli.md) を参照。
- TUI の使い方は [TUI](docs/tui.md) を参照。

## アーキテクチャ

### ディレクトリ構成

```text
src/dandori/
  api/            # API実装 (将来拡張予定)
    server.py     # HTTPサーバ実装
  core/           # ドメインモデルとコアロジック
    models.py     # Task/Edge のデータクラス
    ops.py        # コア操作ロジック
    sort.py       # ソート処理
    validate.py   # サイクル検出・整合性チェック
  interfaces/     # 外部インターフェース
    cli.py        # CLI実装
    tui.py        # TUI実装
  io/             # 入出力
    json_io.py    # JSONエクスポート/インポート
    std_io.py     # 標準出力フォーマット
  storage/        # ストレージ層
    base.py       # Storage インターフェース
    yaml_store.py # YAML実装
  util/           # ユーティリティ
    dirs.py       # ディレクトリ関連
    ids.py        # ID生成
    time.py       # 日時処理
```

### ストレージ層

現在はYAMLストレージのみ実装済み。SQLiteドライバは将来追加予定。

ストレージは `Storage` インターフェースを実装し、以下のメソッドを提供：

- `load()`: グラフを読み込み
- `save()`: グラフを保存
- `get_task()`: タスク取得
- `get_all_tasks()`: 全タスク取得
- `add_task()`: タスク追加
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
mypy src/

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
