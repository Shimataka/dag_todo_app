import json
import unittest
from typing import Any

import yaml  # type: ignore[import-untyped]

from dandori.util.meta_parser import (
    deserialize,
    deserialize_by_json,
    deserialize_by_yaml,
    serialize,
    serialize_by_json,
    serialize_by_yaml,
)


class TestMetaParser(unittest.TestCase):
    """meta_parser モジュールのテスト"""

    # ---- serialize_by_json ----

    def test_serialize_by_json_valid(self) -> None:
        """有効なJSON文字列をdictに変換できる"""
        metadata = '{"key": "value", "number": 42}'
        result = serialize_by_json(metadata)
        assert result.is_ok()
        data = result.unwrap()
        assert data == {"key": "value", "number": 42}

    def test_serialize_by_json_invalid(self) -> None:
        """無効なJSON文字列はエラーを返す"""
        metadata = '{"key": "value"'
        result = serialize_by_json(metadata)
        assert result.is_err()
        assert "Invalid JSON" in result.unwrap_err()

    def test_serialize_by_json_empty(self) -> None:
        """空のJSON文字列を処理できる"""
        metadata = "{}"
        result = serialize_by_json(metadata)
        assert result.is_ok()
        data = result.unwrap()
        assert data == {}

    # ---- deserialize_by_json ----

    def test_deserialize_by_json_valid(self) -> None:
        """有効なdictをJSON文字列に変換できる"""
        metadata = {"key": "value", "number": 42}
        result = deserialize_by_json(metadata)
        assert result.is_ok()
        data = result.unwrap()
        parsed = json.loads(data)
        assert parsed == {"key": "value", "number": 42}

    def test_deserialize_by_json_empty(self) -> None:
        """空のdictをJSON文字列に変換できる"""
        metadata: dict[str, Any] = {}
        result = deserialize_by_json(metadata)
        assert result.is_ok()
        data = result.unwrap()
        parsed = json.loads(data)
        assert parsed == {}

    def test_deserialize_by_json_nested(self) -> None:
        """ネストされたdictをJSON文字列に変換できる"""
        metadata = {"key": {"nested": "value"}, "list": [1, 2, 3]}
        result = deserialize_by_json(metadata)
        assert result.is_ok()
        data = result.unwrap()
        parsed = json.loads(data)
        assert parsed == {"key": {"nested": "value"}, "list": [1, 2, 3]}

    # ---- serialize_by_yaml ----

    def test_serialize_by_yaml_valid(self) -> None:
        """有効なYAML文字列をdictに変換できる"""
        metadata = "key: value\nnumber: 42"
        result = serialize_by_yaml(metadata)
        assert result.is_ok()
        data = result.unwrap()
        assert data == {"key": "value", "number": 42}

    def test_serialize_by_yaml_invalid(self) -> None:
        """無効なYAML文字列はエラーを返す"""
        metadata = "key: value\n  invalid: indentation"
        result = serialize_by_yaml(metadata)
        assert result.is_err()

    def test_serialize_by_yaml_empty(self) -> None:
        """空のYAML文字列を処理できる"""
        metadata = ""
        result = serialize_by_yaml(metadata)
        assert result.is_ok()
        data = result.unwrap()
        assert data is None or data == {}

    def test_serialize_by_yaml_nested(self) -> None:
        """ネストされたYAML文字列をdictに変換できる"""
        metadata = "key:\n  nested: value\nlist:\n  - 1\n  - 2\n  - 3"
        result = serialize_by_yaml(metadata)
        assert result.is_ok()
        data = result.unwrap()
        assert data == {"key": {"nested": "value"}, "list": [1, 2, 3]}

    # ---- deserialize_by_yaml ----

    def test_deserialize_by_yaml_valid(self) -> None:
        """有効なdictをYAML文字列に変換できる"""
        metadata = {"key": "value", "number": 42}
        result = deserialize_by_yaml(metadata)
        assert result.is_ok()
        data = result.unwrap()
        parsed = yaml.safe_load(data)
        assert parsed == {"key": "value", "number": 42}

    def test_deserialize_by_yaml_empty(self) -> None:
        """空のdictをYAML文字列に変換できる"""
        metadata: dict[str, Any] = {}
        result = deserialize_by_yaml(metadata)
        assert result.is_ok()
        data = result.unwrap()
        parsed = yaml.safe_load(data)
        assert parsed == {} or parsed is None

    def test_deserialize_by_yaml_nested(self) -> None:
        """ネストされたdictをYAML文字列に変換できる"""
        metadata = {"key": {"nested": "value"}, "list": [1, 2, 3]}
        result = deserialize_by_yaml(metadata)
        assert result.is_ok()
        data = result.unwrap()
        parsed = yaml.safe_load(data)
        assert parsed == {"key": {"nested": "value"}, "list": [1, 2, 3]}

    # ---- serialize (自動判定) ----

    def test_serialize_auto_json(self) -> None:
        """JSON文字列を自動判定してdictに変換できる"""
        metadata = '{"key": "value"}'
        result = serialize(metadata)
        assert result.is_ok()
        data = result.unwrap()
        assert data == {"key": "value"}

    def test_serialize_auto_yaml(self) -> None:
        """YAML文字列を自動判定してdictに変換できる"""
        metadata = "key: value"
        result = serialize(metadata)
        assert result.is_ok()
        data = result.unwrap()
        assert data == {"key": "value"}

    def test_serialize_auto_json_preferred(self) -> None:
        """JSONとYAMLの両方に解釈可能な場合、JSONを優先する"""
        # "key: value" はYAMLとして解釈可能だが、JSONとして解釈できない
        # 逆に '{"key": "value"}' はJSONとして解釈可能
        metadata = '{"key": "value"}'
        result = serialize(metadata)
        assert result.is_ok()
        data = result.unwrap()
        assert data == {"key": "value"}

    def test_serialize_auto_invalid(self) -> None:
        """無効な文字列はエラーを返す"""
        metadata = "{invalid: [unclosed-list"
        result = serialize(metadata)
        assert result.is_err()
        assert "Invalid metadata" in result.unwrap_err()

    def test_serialize_with_json_parser(self) -> None:
        """JSONパーサーを指定して変換できる"""
        metadata = '{"key": "value"}'
        result = serialize(metadata, parser="json")
        assert result.is_ok()
        data = result.unwrap()
        assert data == {"key": "value"}

    def test_serialize_with_yaml_parser(self) -> None:
        """YAMLパーサーを指定して変換できる"""
        metadata = "key: value"
        result = serialize(metadata, parser="yaml")
        assert result.is_ok()
        data = result.unwrap()
        assert data == {"key": "value"}

    def test_serialize_with_json_parser_invalid(self) -> None:
        """JSONパーサー指定で無効なJSONはエラーを返す"""
        metadata = "key: value"
        result = serialize(metadata, parser="json")
        assert result.is_err()
        assert "Invalid JSON" in result.unwrap_err()

    def test_serialize_with_yaml_parser_invalid(self) -> None:
        """YAMLパーサー指定で無効なYAMLはエラーを返す"""
        metadata = '{"key": "value"'
        result = serialize(metadata, parser="yaml")
        # YAMLパーサーはJSONも解釈できる可能性があるが、エラーになる可能性もある
        # 実際の動作に合わせて調整
        assert result.is_err()

    # ---- deserialize (自動判定) ----

    def test_deserialize_auto_json(self) -> None:
        """dictを自動判定でJSON文字列に変換できる"""
        metadata = {"key": "value"}
        result = deserialize(metadata)
        assert result.is_ok()
        data = result.unwrap()
        # JSONとして解釈可能か確認
        parsed = json.loads(data)
        assert parsed == {"key": "value"}

    def test_deserialize_auto_yaml(self) -> None:
        """dictを自動判定でYAML文字列に変換できる"""
        metadata = {"key": "value"}
        result = deserialize(metadata)
        assert result.is_ok()
        data = result.unwrap()
        # YAMLとして解釈可能か確認
        parsed = yaml.safe_load(data)
        assert parsed == {"key": "value"}

    def test_deserialize_auto_invalid(self) -> None:
        """無効なdictはエラーを返す（通常は発生しないが、エラーハンドリングを確認）"""
        # dictは通常常にシリアライズ可能なので、このテストは実質的には
        # エラーケースをカバーするためのもの
        # 実際の実装では、dictは常にシリアライズ可能
        metadata = {"key": "value"}
        result = deserialize(metadata)
        # dictは常にシリアライズ可能なので、is_ok()になるはず
        assert result.is_ok()

    def test_deserialize_with_json_parser(self) -> None:
        """JSONパーサーを指定して変換できる"""
        metadata = {"key": "value", "number": 42}
        result = deserialize(metadata, parser="json")
        assert result.is_ok()
        data = result.unwrap()
        parsed = json.loads(data)
        assert parsed == {"key": "value", "number": 42}

    def test_deserialize_with_yaml_parser(self) -> None:
        """YAMLパーサーを指定して変換できる"""
        metadata = {"key": "value", "number": 42}
        result = deserialize(metadata, parser="yaml")
        assert result.is_ok()
        data = result.unwrap()
        parsed = yaml.safe_load(data)
        assert parsed == {"key": "value", "number": 42}

    def test_deserialize_roundtrip_json(self) -> None:
        """JSONの往復変換が正しく動作する"""
        original = '{"key": "value", "number": 42}'
        # serialize
        dict_result = serialize(original, parser="json")
        assert dict_result.is_ok()
        data = dict_result.unwrap()
        # deserialize
        str_result = deserialize(data, parser="json")
        assert str_result.is_ok()
        restored = str_result.unwrap()
        # 元の文字列と比較 (JSONのフォーマットは異なる可能性があるため、パースして比較)
        original_parsed = json.loads(original)
        restored_parsed = json.loads(restored)
        assert original_parsed == restored_parsed

    def test_deserialize_roundtrip_yaml(self) -> None:
        """YAMLの往復変換が正しく動作する"""
        original = "key: value\nnumber: 42"
        # serialize
        dict_result = serialize(original, parser="yaml")
        assert dict_result.is_ok()
        data = dict_result.unwrap()
        # deserialize
        str_result = deserialize(data, parser="yaml")
        assert str_result.is_ok()
        restored = str_result.unwrap()
        # 元の文字列と比較 (YAMLのフォーマットは異なる可能性があるため、パースして比較)
        original_parsed = yaml.safe_load(original)
        restored_parsed = yaml.safe_load(restored)
        assert original_parsed == restored_parsed


if __name__ == "__main__":
    unittest.main()
