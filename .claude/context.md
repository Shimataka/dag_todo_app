# MVP仕様（DAG TODO「段ドリ」）

## 0. ゴール/非ゴール

* **ゴール**: DAGで依存関係を持つタスク管理。CLI/TUIを最小UIとして提供。YAML/SQLiteの両ストアを切替可能。タスク配布（エクスポート/インポート）。完了タスクは即削除せずアーカイブ可能。DAGの途中挿入が可能。
* **非ゴール**: 親がすべてdoneでないと着手不可…などの厳格ブロックは入れない。通知やクラウド同期、認証の本格実装は後回し。

---

## 1. ドメインモデル

### 1.1 エンティティ

```yaml
Task:
  id: string            # 例: "t_550e8400-e29b-41d4-a716-446655440000"（UUID v4に "t_" 接頭辞）
  title: string
  description: string | null
  priority: int         # 高いほど優先（例: 3:高, 2:中, 1:低）
  due_at: datetime | null
  start_at: datetime | null   # 無指定は now 扱い（ソート時ルール）
  status: "pending" | "in_progress" | "done"   # MVPはこれだけ。厳格なブロックはしない
  is_archived: bool     # アーカイブ表示制御（元ステータスは保持）
  created_at: datetime
  updated_at: datetime
  created_by: string | null   # 例: ローカルユーザ名
  assigned_to: string | null  # 依頼先（任意）
  tags: [string]

Edge:
  from: TaskID
  to:   TaskID
```

* **多親・多子OK**（DAG）。サイクルは禁止（検出して拒否）。
* **IDポリシー**: 既定は **UUID v4**。将来「UUID+日時+ユーザー名」形式の**表示用スラッグ**（例: `t_550e...@2025-11-14@shimataka`）を**別フィールド `slug`**として任意付与可。内部参照は常に `id`（UUID）で行う。**衝突時は再生成**。

### 1.2 表示ソート

1. `start_at`（nullは now と見做す）
2. `priority`（降順）
3. `created_at`（昇順）
4. `id`（昇順）
   ※「トポロジカル順」はオプション出力で提供（`--topo`）。

### 1.3 アーカイブの木単位制御

* **連結成分**（有向辺の向き無視）を「ツリー」と見做す。
* 「ツリーをアーカイブ」= その成分の全 Task に `is_archived=true` を一括適用。解除は `false` に一括戻し。
* **元の `status` は保持**（`is_archived` は独立フラグ）。

---

## 2. ストレージ層

### 2.1 ストレージ・ドライバ共通IF

```python
class Storage:
    def load(self) -> Graph: ...
    def save(self, graph: Graph) -> None: ...
    def add_task(self, task: Task) -> None: ...
    def update_task(self, task: Task) -> None: ...
    def delete_task(self, task_id: str) -> None: ...
    def add_edge(self, a: str, b: str) -> None: ...
    def remove_edge(self, a: str, b: str) -> None: ...
    def connected_component_ids(self, seed_id: str) -> set[str]: ...
```

### 2.2 YAMLドライバ（必須依存: **PyYAML** のみ）

* 物理ファイル例: `tasks.yaml`
* 構造:

```yaml
version: 1
tasks:
  - {id: "...", title: "...", ...}
edges:
  - {from: "taskIdA", to: "taskIdB"}
meta:
  created_with: "dandori/0.1.0"
  exported_at: "2025-11-14T10:20:30Z"
```

* 競合は単純ロック（`tasks.yaml.lock`）で回避。

### 2.3 SQLiteドライバ（標準ライブラリ `sqlite3`）

* テーブル:

```sql
CREATE TABLE tasks (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT,
  priority INTEGER NOT NULL,
  due_at TEXT,
  start_at TEXT,
  status TEXT NOT NULL,
  is_archived INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  created_by TEXT,
  assigned_to TEXT
);

CREATE TABLE edges (
  src TEXT NOT NULL,
  dst TEXT NOT NULL,
  PRIMARY KEY (src, dst),
  FOREIGN KEY (src) REFERENCES tasks(id) ON DELETE CASCADE,
  FOREIGN KEY (dst) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE INDEX edges_src_idx ON edges(src);
CREATE INDEX edges_dst_idx ON edges(dst);
```

* トランザクションで整合性確保。

### 2.4 差分管理（履歴）

* **最低限**: 「スナップショット」テーブル（SQLite）または `snapshots/yyyymmdd-hhmmss.yaml`（YAML）を任意タイミングで保存。

  * スナップショットは `version` と `commit_message` を持つ。
* **（将来）履歴テーブル**: `task_history(task_id, at, field, old, new)` を追加可能。MVPではスナップショットのみ。

---

## 3. コアアルゴリズム

### 3.1 サイクル検出

* **Kahn** もしくは **DFS（白灰黒）** で追加辺ごとにチェック。
* `add_edge(a,b)` の直後に検証し、サイクル発生なら即座にロールバック。

### 3.2 トポロジカルソート

* Kahn法で `O(|V|+|E|)`。オプション表示（`--topo`）。

### 3.3 「間に挿入」操作（insert-between）

* **前提**: 既存の辺(A→B)に対し新タスクCを挿入。
* **処理**:

  1. edge(A,B) が存在することを検証
  2. edge(A,B) を削除
  3. 新Task Cを追加
  4. edge(A,C), edge(C,B) を追加（サイクル検証）
* **多親/多子の場合**:

  * 明示的に **対象エッジを指定**（`--edge A B`）。UIでは「Aの詳細画面で Insert beneath→B を選ぶ」「Bの画面で Insert above←A を選ぶ」など**片側からもエッジが確定**する導線を用意。

### 3.4 連結成分（ツリー）特定

* 無向グラフとしてBFS/DFSで到達可能ノード集合を抽出。アーカイブ切替はこの集合に一括適用。

---

## 4. API（REST / ローカル用最小実装）

> 社内でも使えるよう、まずは標準ライブラリの `http.server` でJSON RESTを提供（後にFastAPIへ差し替え可能）。
> 認証はMVPでは未実装（ローカル前提）。ポート固定例: `127.0.0.1:8787`

### 4.1 エンドポイント

* `GET /tasks?archived=(0|1|all)&topo=(0|1)` … 一覧
* `POST /tasks` … 追加
* `GET /tasks/{id}` … 詳細
* `PATCH /tasks/{id}` … 部分更新（status/priority/…）
* `DELETE /tasks/{id}` … 削除
* `POST /edges` … 追加 `{from, to}`
* `DELETE /edges` … 削除（クエリ `from`, `to`）
* `POST /insert-between` … `{from, to, new_task:{title,...}}`
* `POST /archive-tree/{id}` … 連結成分を `is_archived=true`
* `POST /unarchive-tree/{id}` … 連結成分を `is_archived=false`
* `GET /export.yaml` … 現在のグラフをYAMLでダウンロード
* `POST /import.yaml` … YAMLをアップロードしてマージ（ID衝突は新ID振り直しまたは別オプション）

#### 例: 追加

```json
POST /tasks
{
  "title": "Cの実装",
  "priority": 2,
  "due_at": "2025-11-30T23:59:59+09:00",
  "start_at": null,
  "description": "A,B完了後に着手想定だが厳格には縛らない",
  "assigned_to": null,
  "tags": ["impl"]
}
```

---

## 5. CLI/TUI

### 5.1 コマンド例（CLI）

```bash
dandori init --store yaml|sqlite --path ./tasks.yaml
dandori add "タイトル" [-p 1..3] [--due YYYY-MM-DD] [--start YYYY-MM-DD] [-d DESC] [--tag t1 --tag t2]
dandori ls [--archived] [--topo]
dandori show <TASK_ID>
dandori set <TASK_ID> status=done priority=3 title="..."
dandori rm <TASK_ID>

dandori link <A_ID> <B_ID>          # A -> B
dandori unlink <A_ID> <B_ID>
dandori insert-between --edge <A_ID> <B_ID> --title "C" [--p 2] [--due ...] [...]

dandori archive-tree <ANY_TASK_ID>
dandori unarchive-tree <ANY_TASK_ID>

dandori export > graph.yaml
dandori import graph.yaml [--on-id-collision regenerate|skip|fail]

dandori blocked-by <TASK_ID>        # ★ 「why」の代替: 依存元(親)を列挙＋未完了を強調
dandori deps <TASK_ID>              # 依存関係（親/子）をリスト
```

* `why` の代替は **`blocked-by`** を正式コマンド名に。

  * 仕様: 厳格ブロックはしないが、「このタスクに論理的に先行する親」はガイドとして提示。未完了の親にマークを付けて「なぜ今やると混乱するか」を説明する役割。

### 5.2 TUI（MVP）

* ライブラリは標準優先。まずはCLI中心、TUIは後追い（将来 `curses`/`textual` 可）。
* 画面例: 左リスト（フィルタ＆ソート適用）＋右ペイン詳細。DAG全体表示は非対応、代わりに `deps <ID>` の結果を折りたたみ表示。

---

## 6. 共有（配布）

### 6.1 エクスポート/インポート（YAML）

* **PyYAMLを必須採用**。JSONは記述不要。
* `export.yaml` は `version`, `tasks`, `edges`, `meta` を含む。
* インポートはID衝突ポリシーを選択可（`regenerate|skip|fail`）。既定は `regenerate`。

---

## 7. セキュリティ/認証（MVP）

* ローカル運用前提で**未実装**。
* もし簡易パスワードが必要なら、「アプリ起動時にベーシック認証をかける」程度を将来追加。DB内にハッシュを置いても**ファイル自体が平文**なので過信しない方針。

---

## 8. エラーポリシー

* **サイクル検出**: `409 Conflict` + `{"error":"cycle_detected","edge":{"from":A,"to":B}}`
* **存在しないID**: `404`
* **整合性違反**（例: insert-betweenでA→Bがない）: `422`

---

## 9. ディレクトリ構成（Lean Feature-First）

```bash
dandori/
  src/
    dandori/
      core/
        models.py         # dataclass Task/Edge, validators
        graph.py          # in-memory Graph（辞書＋隣接表）
        topo.py           # cycle check / topo sort / components
        ops.py            # add/link/insert-between/archive-tree 等のユースケース
      storage/
        base.py           # Storage IF
        yaml_store.py     # PyYAML実装
        sqlite_store.py   # sqlite3実装
      cli/
        __main__.py       # argparse / コマンド実装
      api/
        server.py         # http.server ベース簡易REST
      io/
        exporter.py       # YAML export
        importer.py       # YAML import（衝突ポリシー）
      util/
        ids.py            # UUID生成 / slugユーティリティ
        time.py           # now扱い・パース
  tests/
    test_ops.py
    test_topo.py
    test_import_export.py
```

---

## 10. 主要ユースケース疑似コード

### 10.1 insert-between

```python
def insert_between(store: Storage, a: str, b: str, new_task: Task):
    g = store.load()
    if not g.has_edge(a, b):
        raise Unprocessable("edge_not_found")

    store.add_task(new_task)
    store.remove_edge(a, b)
    try:
        store.add_edge(a, new_task.id)
        store.add_edge(new_task.id, b)
    except CycleDetected:
        # rollback
        store.remove_edge(a, new_task.id)
        store.remove_edge(new_task.id, b)
        store.add_edge(a, b)
        store.delete_task(new_task.id)
        raise
```

### 10.2 blocked-by（why代替）

```python
def blocked_by(g: Graph, task_id: str) -> list[tuple[Task, bool]]:
    # 親を遡って収集、(Task, is_done) で返す
    parents = g.ancestors(task_id)        # 方向有りで親方向
    return [(t, t.status == "done") for t in parents]
```

### 10.3 アーカイブ/解除

```python
def toggle_archive_tree(store: Storage, seed_id: str, archived: bool):
    g = store.load()
    ids = g.undirected_component(seed_id)
    for tid in ids:
        t = g.tasks[tid]
        if t.is_archived != archived:
            t.is_archived = archived
            store.update_task(t)
```

---

## 11. ビルド・依存

* **必須**: Python 3.11+ / **PyYAML** / （SQLiteは標準）
* プライベート豪華版に拡張時:

  * Web: FastAPI + Uvicorn、フロントは任意（Cytoscape.js/Graphviz/Mermaid.js 等）
  * すべてCore（`core/`, `storage/`, `ops.py`）は再利用

---

## 12. 将来拡張のための余白

* GraphQL層は将来オプション（RESTを薄く保つ）
* 通知（Slack/メール）は外部スクリプトからREST叩けば連携可能
* 履歴テーブル導入で変更追跡を強化
* 認証はトークン（ローカルのみ）→社内はLDAP連携に昇格可能

---

### まとめ

* **多親・多子DAG**／**厳格ブロック無し**／**「間に挿入」明示エッジ指定**／**木単位アーカイブは `is_archived` で非破壊**。
* ストレージは **YAML(P yYAML)** と **SQLite** の2ドライバを同一IFで切替。
* CLIは `blocked-by` を採用、`insert-between --edge A B` を中核操作に。
* RESTは標準ライブラリで最小実装、のち豪華UIを前面差し替え可能。
