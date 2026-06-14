"""Host assistant final answer continuity payload helper 测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.payload import (
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host._terminal_answer import assistant_final_answer_continuity_text
from dayu.host.terminal_summary_payload import (
    PayloadTextReadPolicy,
    assistant_final_answer_text_from_run_payload,
    terminal_summary_content_text_from_payload,
)

_OVERLONG_TEXT = "终态回答" * 4096


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host" / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(busy_timeout_seconds=0.25),
    )


def test_run_payload_final_answer_is_read() -> None:
    """RUN payload 的 final_answer 是 assistant final answer 来源。"""

    assert (
        assistant_final_answer_text_from_run_payload(
            {"final_answer": "最终回答"},
            text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
        )
        == "最终回答"
    )


def test_blank_run_payload_final_answer_is_missing() -> None:
    """RUN payload 空白 final_answer 按缺失处理。"""

    assert (
        assistant_final_answer_text_from_run_payload(
            {"final_answer": "   "},
            text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
        )
        is None
    )


def test_run_payload_summary_fields_are_not_final_answer_sources() -> None:
    """RUN payload 的 content、summary_text 与 nested summary 均不被读取。"""

    payload: dict[str, JsonValue] = {
        "content": "裸 content",
        "summary_text": "摘要",
        "summary": {"content": "nested content", "summary_text": "nested summary"},
    }

    assert (
        assistant_final_answer_text_from_run_payload(
            payload,
            text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
        )
        is None
    )


def test_terminal_summary_payload_content_is_read() -> None:
    """terminal summary artifact payload 的 content 可作为 final answer continuity。"""

    assert (
        terminal_summary_content_text_from_payload(
            {"content": "artifact final answer"},
            text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
        )
        == "artifact final answer"
    )


def test_blank_terminal_summary_content_is_missing() -> None:
    """terminal summary artifact payload 空白 content 按缺失处理。"""

    assert (
        terminal_summary_content_text_from_payload(
            {"content": "\n\t"},
            text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
        )
        is None
    )


def test_terminal_summary_payload_summary_fields_are_not_content_sources() -> None:
    """terminal summary artifact 的 summary_text 与 nested summary 均不被读取。"""

    payload: dict[str, JsonValue] = {
        "summary_text": "摘要",
        "summary": {"content": "nested content", "summary_text": "nested summary"},
    }

    assert (
        terminal_summary_content_text_from_payload(
            payload,
            text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
        )
        is None
    )


def test_allowed_non_string_field_strict_raises_and_lenient_returns_none() -> None:
    """允许字段非字符串时 strict 抛错，lenient 返回 None。"""

    with pytest.raises(HostDurableError):
        assistant_final_answer_text_from_run_payload(
            {"final_answer": 123},
            text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
        )

    assert (
        assistant_final_answer_text_from_run_payload(
            {"final_answer": 123},
            text_policy=PayloadTextReadPolicy.LENIENT_NON_EMPTY,
        )
        is None
    )
    with pytest.raises(HostDurableError):
        terminal_summary_content_text_from_payload(
            {"content": 123},
            text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
        )

    assert (
        terminal_summary_content_text_from_payload(
            {"content": 123},
            text_policy=PayloadTextReadPolicy.LENIENT_NON_EMPTY,
        )
        is None
    )


def test_disallowed_summary_text_type_does_not_trigger_strict_error() -> None:
    """禁用的 summary_text 字段非字符串时也不触发 strict error。"""

    assert (
        assistant_final_answer_text_from_run_payload(
            {"summary_text": 123},
            text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
        )
        is None
    )
    assert (
        terminal_summary_content_text_from_payload(
            {"summary_text": 123},
            text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
        )
        is None
    )


def test_overlong_allowed_text_is_preserved_by_source_selection() -> None:
    """source-selection helper 保留长文本，caller 自行负责截断。

    :returns: ``None``。
    :raises AssertionError: helper 截断允许文本时抛出。
    """

    assert (
        assistant_final_answer_text_from_run_payload(
            {"final_answer": _OVERLONG_TEXT},
            text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
        )
        == _OVERLONG_TEXT
    )
    assert (
        terminal_summary_content_text_from_payload(
            {"content": _OVERLONG_TEXT},
            text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
        )
        == _OVERLONG_TEXT
    )


def test_continuity_resolver_prefers_run_final_answer_over_artifact(
    tmp_path: Path,
) -> None:
    """continuity resolver 优先使用 RUN_SUCCEEDED.final_answer。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: resolver 错误使用 artifact content 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> str | None:
            """写入 terminal artifact 并读取 continuity 文本。

            :param transaction: Host transaction。
            :returns: continuity 文本。
            """

            descriptor = PayloadStore().write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-terminal-summary-preference",
                    payload_id="sqlite-terminal-summary-preference",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json={"content": "artifact fallback answer"},
                ),
            )
            return assistant_final_answer_continuity_text(
                transaction,
                {
                    "final_answer": "inline final answer",
                    "terminal_summary_ref": descriptor.payload_ref,
                    "terminal_summary_digest": descriptor.payload_digest,
                },
                text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
            )

        assert store.transaction_runner.run_write(operation) == "inline final answer"


def test_continuity_resolver_requires_complete_terminal_descriptor(
    tmp_path: Path,
) -> None:
    """terminal summary descriptor 缺任一侧时不读取 fallback。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: resolver 错误读取裸 content 或 summary_text 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> tuple[str | None, str | None]:
            """读取缺失 descriptor 的 continuity 文本。

            :param transaction: Host transaction。
            :returns: 只有 ref 或只有 digest 时的读取结果。
            """

            only_ref = assistant_final_answer_continuity_text(
                transaction,
                {
                    "content": "裸 content 不应读取",
                    "summary_text": "summary 不应读取",
                    "terminal_summary_ref": "payload-terminal-summary-missing",
                },
                text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
            )
            only_digest = assistant_final_answer_continuity_text(
                transaction,
                {
                    "content": "裸 content 不应读取",
                    "summary_text": "summary 不应读取",
                    "terminal_summary_digest": "sha256:missing",
                },
                text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
            )
            return only_ref, only_digest

        assert store.transaction_runner.run_read(operation) == (None, None)


def test_continuity_resolver_rejects_malformed_terminal_descriptor(
    tmp_path: Path,
) -> None:
    """terminal summary descriptor 字段类型非法时抛出 durable error。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: resolver 未拒绝 malformed descriptor 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> None:
            """读取 malformed descriptor。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostDurableError: descriptor 字段类型非法时抛出。
            """

            assistant_final_answer_continuity_text(
                transaction,
                {
                    "terminal_summary_ref": 123,
                    "terminal_summary_digest": "sha256:missing",
                },
                text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
            )

        with pytest.raises(HostDurableError, match="terminal_summary_ref"):
            store.transaction_runner.run_read(operation)


def test_continuity_resolver_rejects_malformed_terminal_digest(
    tmp_path: Path,
) -> None:
    """terminal summary digest 字段类型非法时抛出 durable error。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: resolver 未拒绝 malformed digest 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> None:
            """读取 malformed digest descriptor。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostDurableError: digest 字段类型非法时抛出。
            """

            assistant_final_answer_continuity_text(
                transaction,
                {
                    "terminal_summary_ref": "payload-terminal-summary",
                    "terminal_summary_digest": 123,
                },
                text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
            )

        with pytest.raises(HostDurableError, match="terminal_summary_digest"):
            store.transaction_runner.run_read(operation)


def test_continuity_resolver_reads_digest_checked_terminal_content(
    tmp_path: Path,
) -> None:
    """continuity resolver 缺失 final_answer 时读取 digest-checked artifact content。"""

    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> str | None:
            """写入 terminal summary artifact 并读取 continuity 文本。

            :param transaction: Host transaction。
            :returns: continuity 文本。
            """

            descriptor = PayloadStore().write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-terminal-summary",
                    payload_id="sqlite-terminal-summary",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json={
                        "content": "artifact final answer",
                        "summary_text": "artifact summary",
                    },
                ),
            )
            return assistant_final_answer_continuity_text(
                transaction,
                {
                    "final_answer": "  ",
                    "content": "裸 content 不应被读取",
                    "summary_text": "run summary 不应被读取",
                    "terminal_summary_ref": descriptor.payload_ref,
                    "terminal_summary_digest": descriptor.payload_digest,
                },
                text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
            )

        assert store.transaction_runner.run_write(operation) == "artifact final answer"
