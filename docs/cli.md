# CLI コマンド

## タスクの追加

```bash
# 基本的なタスク追加
dandori add "タスクのタイトル" --description "説明" --priority 2

# 依存関係を指定して追加
dandori add "子タスク" --depends-on <親タスクID1> <親タスクID2>

# 期限と開始日を指定
dandori add "タスク" --due 2025-12-31 --start 2025-01-01
```

## タスクの一覧表示

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

## タスクの表示・更新

```bash
# タスクの詳細表示
dandori show <TASK_ID>

# タスクの更新
dandori update <TASK_ID> --title "新しいタイトル" --status in_progress --priority 3

# 完了マーク
dandori done <TASK_ID>
```

## 依存関係の管理

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

## 間に挿入

既存のエッジ（A→B）に対して新タスクCを挿入し、A→C→Bに変換：

```bash
dandori insert <A_ID> <B_ID> --title "挿入するタスク" --description "説明"
```

## アーカイブ

連結成分（ツリー）単位でアーカイブ/復元：

```bash
# アーカイブ
dandori archive <TASK_ID>

# 復元
dandori restore <TASK_ID>
```

## エクスポート/インポート

```bash
# JSON形式でエクスポート
dandori export tasks.json

# JSON形式でインポート（ID衝突時はスキップ）
dandori import tasks.json
```

## 依頼機能

タスクを他者に依頼：

```bash
dandori request <TASK_ID> --to <担当者名> --by <依頼者名> --note "メモ"
```

## 整合性チェック

DAGのサイクルや不整合を検出：

```bash
dandori check
```
