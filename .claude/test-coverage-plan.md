# テストカバレッジ計画（src/ 網羅）

## 現状サマリ（カバレッジ 30%）

| モジュール | カバー | 備考 |
| :------: | :----: | :----: |
| **0%** | | |
| `api/server.py` | 0% | REST Handler / run 未テスト |
| `core/validate.py` | 0% | detect_cycles / detect_inconsistencies は CLI 経由のみ |
| `interfaces/cli.py` | 0% | CLI 全体未テスト |
| `interfaces/tui/*` | 0% | app, data, endpoint, helper, style, view すべて未テスト |
| `io/std_io.py` | 0% | print_task 未テスト |
| **低カバー** | | |
| `storage/sqlite3_store.py` | 34% | 永続化テストはあるが Store 単体の各メソッド・エラー経路が不足 |
| `util/ids.py` | 19% | parse_id / parse_ids / *_with_msg 未テスト |
| `util/time.py` | 32% | now_iso / format_requested_sla の分岐未テスト |
| `core/ops.py` | 77% | ready_only / bottleneck_only / component_of / \_is_ready / \_is_bottleneck 等 |
| `core/sort.py` | 80% | order_with_no_start, topo の「残りノード」経路 |
| `storage/base.py` | 72% | 抽象クラス（実装は子経由でカバー可） |
| `storage/yaml_store.py` | 62% | 一部メソッド・エラー経路 |
| `io/json_io.py` | 79% | export の FileExistsError / import の FileNotFoundError |
| `util/dirs.py` | 78% | 一部ブランチ |
| `util/meta_parser.py` | 74% | 一部ブランチ |
| **高カバー** | | |
| `core/models.py` | 86% | from_dict の TypeError 補正のみ未カバー |
| `util/logger.py` | 88% | ほぼ十分 |

---

## 追加すべきテストの計画

### 1. core/validate.py（新規: `tests/test_validate.py`）

- **detect_cycles**
  - サイクルなし → 空リスト
  - 直接サイクル A→A
  - 長いサイクル A→B→C→A
  - 複数サイクル
- **detect_inconsistencies**
  - 一貫したグラフ → 空リスト
  - missing_child: 親の children に子が含まれていない
  - missing_parent: 子の depends_on に親が含まれていない
  - 参照先が tasks に存在しない場合はスキップ（既存仕様）

### 2. util/ids.py（新規: `tests/test_ids.py`）

- **gen_task_id**
  - 戻り値が `uuid_YYYYMMDDHHMMSS_username` 形式であること
- **parse_id**
  - 空文字 → Err("Empty ID")
  - 完全一致 1 件 → Ok(id)
  - プレフィックス一致 1 件 → Ok(id)
  - プレフィックス一致 2 件以上 → Err(Ambiguous)
  - 0 件 → Err(Unknown)
- **parse_ids**
  - カンマ区切りで複数 Ok
  - 一つでも Err なら Err を返す
- **parse_id_with_msg**
  - None → ""
  - Ok → id
  - Err + can_raise=True → ValueError
  - Err + can_raise=False → ""
  - msg_buffer にメッセージが追記されること
- **parse_ids_with_msg**
  - 上と同様（None→[]、Err で ValueError または []、msg_buffer）

### 3. util/time.py（新規: `tests/test_time.py`）

- **now_iso**
  - 戻り値が ISO 形式（例: `%Y-%m-%dT%H:%M:%S`）であること
- **format_requested_sla**
  - requested_at なし → Ok("")
  - requested_at のみ → 経過日時表示（+NdNh）
  - due_date あり → " / SLA:NdNh"
  - パース失敗 → Err("???h..." または " / SLA:???")

### 4. io/std_io.py（新規: `tests/test_std_io.py`）

- **print_task**
  - 標準出力をキャプチャし、id / title / status / priority / is_archived / due_date / start_at / depends_on / children / created_at / updated_at が出力されること
  - assigned_to / requested_by / tags が None または空のときはその行が出ない（または出る）ことを仕様に合わせて検証

### 5. api/server.py（新規: `tests/test_api_server.py`）

- **Handler**
  - GET /health → 200, body `{"ok":true}`
  - GET /other → 404, body `{"error":"not_found"}`
- **run**
  - スレッドでサーバーを起動し、GET /health を送って 200 を確認したあと shutdown（または `serve_forever` をモックして run の呼び出しのみ検証）

### 6. core/ops.py の不足分（既存: `tests/test_ops.py` に追加）

- **list_tasks**
  - `ready_only=True`: 依存がすべて完了しているタスクのみ
  - `bottleneck_only=True`: 未完了の子がいるタスクのみ
  - `component_of=task_id`: 指定タスクと同じ弱連結成分のみ
  - `component_of` に存在しない ID を渡す → OpsError（weakly_connected_component の Err 経路）
- **_is_ready / _is_bottleneck**
  - 上記フィルタのテストで間接的にカバー可能。必要なら list_tasks の戻り件数・内容で検証

### 7. storage/sqlite3_store.py（新規: `tests/test_sqlite3_store.py` または `test_store_basic` 拡張）

- **StoreToSQLite 単体**
  - add_task / get_task / get_tasks / get_all_tasks / remove / link / unlink / insert_between / archive_component / reason
  - commit / rollback（test_db_persistent と重複するが、メソッド単位で網羅）
- **エラー系**
  - 重複 ID で add_task → Err
  - 存在しない ID で get_task → Err
  - get_tasks で一部存在しない ID を含む → Err または部分 Ok（仕様に合わせる）
- **デコード**
  - tags が不正 JSON のとき _decode_tags が [] にフォールバック（間接的にカバー可）

### 8. storage/yaml_store.py の不足分（既存: `tests/test_store_basic.py` / `test_db_persistent.py` に追加）

- get_tasks の正常・Err
- weakly_connected_component の Err（存在しない ID）
- insert_between のエラー経路（親/子が見つからない等）
- カバレッジで赤い行に対応するブランチのテスト

### 9. core/models.py（既存: 新規テストクラスまたは `test_ops` 等に追加）

- **Task.from_dict**
  - 必須キー欠損で TypeError が出る場合に、d["id"] / d["owner"] / d["title"] を補正して Task が生成されること

### 10. core/sort.py（新規: `tests/test_sort.py` または `test_ops` に追加）

- **task_sort_key**
  - order_with_no_start="now" → start_at が None のとき now_iso() が使われる
  - order_with_no_start="end_of_time" → "9999-12-31T23:59:59"
- **topo_sort**
  - 通常 DAG → トポ順
  - 部分グラフで「子が tasks に含まれない」→ スキップ
  - サイクルや分離成分で「残った node がいる」経路（56–61 行）を踏むケース

### 11. io/json_io.py の不足分（既存: `tests/test_import_export.py` に追加）

- export_json: 既存ファイルに上書きしようとしたとき FileExistsError
- import_json: 存在しないパスで FileNotFoundError

### 12. util/dirs.py / util/meta_parser.py

- カバレッジの「Missing」行に対応するブランチを 1 本ずつテスト追加（ensure_dirs / load_env のエラー経路、meta_parser の invalid 系など）

---

## 優先度と実施順序

| 優先度 | 対象 | 理由 |
| :------: | :----: | :----: |
| 高 | validate, ids, time | 純粋関数・ユーティリティで書きやすく、バグの影響が大きい |
| 高 | api/server | 公開 API の振る舞い保証 |
| 高 | ops list_tasks の ready_only / bottleneck_only / component_of | 既存テストで未カバーの重要なフィルタ |
| 中 | sqlite3_store 単体 | 永続化はテストありだが、Store インターフェースの網羅が薄い |
| 中 | sort, models.from_dict, json_io の例外 | 少数の追加でカバー向上 |
| 中 | std_io.print_task | 軽量 |
| 低 | yaml_store の残り行 | 既存テストでかなりカバー済み |
| 低 | interfaces/cli, interfaces/tui | 統合・E2E またはモックで対応。工数大のため後回しでよい |

---

## 実施時の注意

- 既存の `test_*` は「機能・ユースケース」単位でまとまっているため、**ユーティリティ単体**は `test_validate.py` / `test_ids.py` / `test_time.py` のようにモジュール名に対応したファイルを新規作成すると見通しが良い。
- **storage** は `test_store_basic.py` が YAML のみ参照しているため、SQLite 単体のメソッド網羅は `test_sqlite3_store.py` を新規にするか、`test_store_basic.py` を Store 抽象化して両バックエンドで同じケースを走らせる形がよい。
- **CLI / TUI** は subprocess で `dandori ...` を実行して exit code と stdout/stderr を検証する統合テスト、またはハンドラ単位のモックテストで対応する。curses 依存の TUI は CI で扱いづらいため、計画の最後に回す。

---

## 実行結果（実施済み）

- **実施日**: 計画に沿ってテストを追加済み。
- **カバレッジ**: 30% → **39%**（TOTAL）。
- **テスト数**: 105 → **165**（+60）。

### カバー向上したモジュール

| モジュール | 実施前 | 実施後 |
| :------: | :----: | :----: |
| api/server.py | 0% | **83%** |
| core/models.py | 86% | **100%** |
| core/ops.py | 77% | **84%** |
| core/sort.py | 80% | **100%** |
| core/validate.py | 0% | **98%** |
| io/json_io.py | 79% | **100%** |
| io/std_io.py | 0% | **100%** |
| storage/sqlite3_store.py | 34% | **56%** |
| util/ids.py | 19% | **77%** |
| util/time.py | 32% | **100%** |

### 未実施（低優先）

- **interfaces/cli.py**, **interfaces/tui/\***: 0% のまま。統合・E2E またはモックで対応する想定。

この計画に沿ってテストを追加した結果、`src/` の主要モジュール（core / io / api / util / storage の大部分）は高カバレッジとなった。全体は CLI・TUI の行数が多いため 39% にとどまるが、ビジネスロジックとストレージ・API は十分にカバーされている。
