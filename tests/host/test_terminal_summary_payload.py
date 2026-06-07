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
