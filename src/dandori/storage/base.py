from abc import ABC, abstractmethod

from pyresults import Result

from dandori.core.models import Task
from dandori.util.dirs import ensure_dirs, load_env


class Store(ABC):
    """ストレージ抽象基底クラス。

    このクラスは、YAML/SQLiteなどのストレージ実装の共通インターフェースを定義します。
    実装クラスは、以下のpublicメソッドを提供する必要があります。

    Public API:
        - load(): ストレージからデータを読み込む
        - save(): ストレージにデータを保存する
        - add_task(): タスクを追加する
        - get(): タスクIDでタスクを取得する
        - get_all_tasks(): 全タスクを取得する
        - remove(): タスクを削除する
        - link(): タスク間の依存関係を追加する（parent -> child）
        - unlink(): タスク間の依存関係を削除する
        - archive_component(): 弱連結成分単位でアーカイブ状態を切り替える
        - reason(): タスクの依存関係情報を取得する
        - insert_between(): 既存のエッジA->Bの間に新しいタスクを挿入する

    注意: 実装クラスは内部構造（_tasks等）を直接公開してはいけません。
    """

    def __init__(
        self,
        data_path: str | None = None,
        archive_path: str | None = None,
    ) -> None:
        ensure_dirs()
        env = load_env()
        self.data_path = data_path or env["DATA_PATH"]
        self.archive_path = archive_path or env["ARCHIVE_PATH"]

    @abstractmethod
    def load(self) -> None:
        """ストレージからデータを読み込む。

        内部の_tasks辞書を更新します。
        """
        raise NotImplementedError

    @abstractmethod
    def save(self) -> None:
        """ストレージにデータを保存する。

        内部の_tasks辞書の内容を永続化します。
        """
        raise NotImplementedError

    # ---- データ操作 ----

    @abstractmethod
    def commit(self) -> None:
        """変更を永続化する"""
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        """変更を破棄する"""
        raise NotImplementedError

    # ---- データ取得 ----

    @abstractmethod
    def get_task(self, task_id: str) -> Result[Task, str]:
        """タスクIDでタスクを取得する。

        Args:
            task_id: 取得するタスクのID

        Returns:
            Ok(Task): 成功時
            Err(str): 失敗時（例: タスクが見つからない）
        """
        raise NotImplementedError

    @abstractmethod
    def get_tasks(self, task_ids: list[str]) -> Result[list[Task], str]:
        """タスクIDのリストでタスクを取得する。

        Args:
            task_ids: 取得するタスクのIDのリスト

        Returns:
            Ok(list[Task]): 成功時（タスクのリスト）
            Err(str): 失敗時
        """
        raise NotImplementedError

    @abstractmethod
    def get_all_tasks(self) -> Result[dict[str, Task], str]:
        """全タスクを取得する。

        Returns:
            Ok(dict[str, Task]): 成功時（タスクIDをキーとする辞書）
            Err(str): 失敗時
        """
        raise NotImplementedError

    # ---- タスク操作 ----

    @abstractmethod
    def add_task(self, task: Task, *, id_overwritten: str | None = None) -> Result[None, str]:
        """タスクを追加する。

        Args:
            task: 追加するタスク
            id_overwritten: タスクIDを上書きする場合に指定

        Returns:
            Ok(None): 成功時
            Err(str): 失敗時（例: 既に存在するID）
        """
        raise NotImplementedError

    @abstractmethod
    def update_task(self, task: Task) -> Result[None, str]:
        """タスクを更新する。

        Args:
            task: 更新するタスク

        Returns:
            Ok(None): 成功時
            Err(str): 失敗時（例: タスクが見つからない）
        """
        raise NotImplementedError

    @abstractmethod
    def remove_task(self, task_id: str) -> Result[None, str]:
        """タスクを削除する。

        タスクを削除する際、関連する依存関係（親子リンク）も自動的に削除されます。

        Args:
            task_id: 削除するタスクのID

        Returns:
            Ok(None): 成功時
            Err(str): 失敗時（例: タスクが見つからない）
        """
        raise NotImplementedError

    @abstractmethod
    def link_tasks(self, parent_id: str, child_id: str) -> Result[None, str]:
        """タスク間の依存関係を追加する（parent -> child）。

        循環が検出された場合はエラーを返します。

        Args:
            parent_id: 親タスクのID
            child_id: 子タスクのID

        Returns:
            Ok(None): 成功時
            Err(str): 失敗時（例: 循環検出、タスクが見つからない）
        """
        raise NotImplementedError

    @abstractmethod
    def unlink_tasks(self, parent_id: str, child_id: str) -> Result[None, str]:
        """タスク間の依存関係を削除する。

        Args:
            parent_id: 親タスクのID
            child_id: 子タスクのID

        Returns:
            Ok(None): 成功時
            Err(str): 失敗時（例: タスクが見つからない）
        """
        raise NotImplementedError

    # ---- アーカイブ (弱連結成分単位) ----

    @abstractmethod
    def weakly_connected_component(self, start: str) -> Result[list[Task], str]:
        """指定されたタスクを含む弱連結成分を取得する。

        Args:
            start: 起点となるタスクのID

        Returns:
            Ok(list[Task]): 成功時（弱連結成分のタスクリスト）
            Err(str): 失敗時（例: タスクが見つからない）
        """
        raise NotImplementedError

    @abstractmethod
    def archive_tasks(self, task_id: str) -> Result[list[str], str]:
        """弱連結成分単位でアーカイブ状態を切り替える。

        Args:
            task_id: 起点となるタスクのID
            flag: Trueでアーカイブ、Falseで復元

        Returns:
            Ok(list[str]): 成功時（更新されたタスクIDのリスト）
            Err(str): 失敗時（例: タスクが見つからない）
        """
        raise NotImplementedError

    @abstractmethod
    def unarchive_tasks(self, task_id: str) -> Result[list[str], str]:
        """弱連結成分単位でアーカイブ状態を復元する。

        Args:
            task_id: 起点となるタスクのID

        Returns:
            Ok(list[str]): 成功時（更新されたタスクIDのリスト）
            Err(str): 失敗時（例: タスクが見つからない）
        """
        raise NotImplementedError

    # ---- 依存理由表示 (why→reason) ----

    @abstractmethod
    def get_dependency_info(self, task_id: str) -> Result[dict[str, list[str]], str]:
        """タスクの依存関係情報を取得する。

        Args:
            task_id: 対象タスクのID

        Returns:
            Ok(dict): 成功時（{"task": [...], "depends_on": [...], "children": [...]}）
            Err(str): 失敗時（例: タスクが見つからない）
        """
        raise NotImplementedError

    # ---- 挿入機能 A -> (new) -> B ----

    @abstractmethod
    def insert_task(
        self,
        a: str,
        b: str,
        new_task: Task,
        *,
        id_overwritten: str | None = None,
    ) -> Result[None, str]:
        """既存のエッジA->Bの間に新しいタスクを挿入する。

        既存のエッジA->Bが存在する場合は削除し、A->new_task->Bの構造に変更します。
        エッジが存在しない場合でも、A->new_task->Bのリンクを作成します。

        Args:
            a: 親タスクのID
            b: 子タスクのID
            new_task: 挿入する新しいタスク
            id_overwritten: 新しいタスクのIDを上書きする場合に指定

        Returns:
            Ok(None): 成功時
            Err(str): 失敗時（例: 循環検出、タスクが見つからない）
        """
        raise NotImplementedError
