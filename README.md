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
- PyResults >=0.2.0

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

## 基本的な使い方

### タスクの追加

```bash
# 基本的なタスク追加
dandori add "タスクのタイトル" --description "説明" --priority 2

# 依存関係を指定して追加
dandori add "子タスク" --depends-on <親タスクID1> <親タスクID2>

# 期限と開始日を指定
dandori add "タスク" --due 2025-12-31 --start 2025-01-01
```

### タスクの一覧表示

```bash
# 全タスクを表示
dandori list

# フィルタリング
dandori list --status done
dandori list --archived true
dandori list --query "キーワード"

# 詳細表示
dandori list --details

# トポロジカル順で表示
dandori list --topo
```

### タスクの表示・更新

```bash
# タスクの詳細表示
dandori show <TASK_ID>

# タスクの更新
dandori update <TASK_ID> --title "新しいタイトル" --status in_progress --priority 3

# 完了マーク
dandori done <TASK_ID>
```

### 依存関係の管理

```bash
# 依存関係の表示
dandori deps <TASK_ID>

# 依存関係の説明（なぜこのタスクがブロックされているか）
dandori reason <TASK_ID>

# エッジの追加（updateコマンドで代替可能）
dandori update <TASK_ID> --add-parent <親ID>

# エッジの削除
dandori update <TASK_ID> --remove-parent <親ID>
```

### 間に挿入

既存のエッジ（A→B）に対して新タスクCを挿入し、A→C→Bに変換：

```bash
dandori insert <A_ID> <B_ID> --title "挿入するタスク" --description "説明"
```

### アーカイブ

連結成分（ツリー）単位でアーカイブ/復元：

```bash
# アーカイブ
dandori archive <TASK_ID>

# 復元
dandori restore <TASK_ID>
```

### エクスポート/インポート

```bash
# JSON形式でエクスポート
dandori export tasks.json

# JSON形式でインポート（ID衝突時はスキップ）
dandori import tasks.json
```

### 依頼機能

タスクを他者に依頼：

```bash
dandori request <TASK_ID> --to <担当者名> --by <依頼者名> --note "メモ"
```

### 整合性チェック

DAGのサイクルや不整合を検出：

```bash
dandori check
```

## アーキテクチャ

### ディレクトリ構成

```text
src/dandori/
  core/           # ドメインモデルとコアロジック
    models.py     # Task/Edge のデータクラス
    sort.py       # ソート処理
    validate.py   # サイクル検出・整合性チェック
  storage/        # ストレージ層
    base.py       # Storage インターフェース
    yaml_store.py # YAML実装
  cli/            # CLI実装
    parser.py     # コマンドパーサー
  io/             # 入出力
    json_io.py    # JSONエクスポート/インポート
    std_io.py     # 標準出力フォーマット
  util/           # ユーティリティ
    ids.py        # ID生成
    time.py       # 日時処理
```

### ストレージ層

現在はYAMLストレージのみ実装済み。SQLiteドライバは将来追加予定。

ストレージは `Storage` インターフェースを実装し、以下のメソッドを提供：

- `load()`: グラフを読み込み
- `save()`: グラフを保存
- `add_task()`: タスク追加
- `update_task()`: タスク更新
- `get()`: タスク取得
- `link()` / `unlink()`: エッジの追加/削除
- `archive_component()`: 連結成分のアーカイブ
- `insert_between()`: 間に挿入操作

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
    status: str                # pending / in_progress / done / requested
    depends_on: list[str]      # 親タスクIDのリスト
    children: list[str]        # 子タスクIDのリスト
    is_archived: bool          # アーカイブフラグ
    assigned_to: str | None    # 担当者
    requested_by: str | None   # 依頼者
    requested_at: str | None   # 依頼日時
    requested_note: str | None # 依頼メモ
    created_at: str            # 作成日時
    updated_at: str            # 更新日時
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
- [ ] TUI / REST API への足がかり

## ライセンス

MIT License
