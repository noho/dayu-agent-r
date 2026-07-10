"""Host assistant final answer continuity payload helper 测试。"""

from __future__ import annotations

import sqlite3
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
    PayloadDescriptor,
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.schema import TABLE_SQLITE_PAYLOADS
from dayu.host.durable.transaction import HostTransaction
from dayu.host._terminal_answer import (
    assistant_final_answer_continuity_text,
    required_assistant_final_answer_continuity_text,
)
from dayu.host.terminal_payload import (
    PayloadTextReadPolicy,
    assistant_final_answer_text_from_run_payload,
    terminal_payload_content_text_from_payload,
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


def _write_terminal_payload(
    transaction: HostTransaction,
    *,
    payload_ref: str,
    payload_id: str,
    payload_json: JsonValue,
) -> PayloadDescriptor:
    """写入 resolver 测试用 SQLite terminal payload。

    :param transaction: 当前 Host write transaction。
    :param payload_ref: descriptor ref。
    :param payload_id: SQLite payload id。
    :param payload_json: 待写入 JSON 值。
    :returns: 已持久化 descriptor。
    :raises HostDurableError: payload 无法持久化时抛出。
    """

    return PayloadStore().write_sqlite_payload(
        transaction,
        SQLitePayloadWriteRequest(
            payload_ref=payload_ref,
            payload_id=payload_id,
            payload_format=SQLitePayloadFormat.CANONICAL_JSON,
            payload_json=payload_json,
        ),
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


def test_terminal_payload_content_is_read() -> None:
    """terminal artifact payload 的顶层 content 可作为 final answer continuity。"""

    assert (
        terminal_payload_content_text_from_payload(
            {"content": "artifact final answer"},
            text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
        )
        == "artifact final answer"
    )


def test_blank_terminal_payload_content_is_missing() -> None:
    """terminal artifact payload 空白 content 按缺失处理。"""

    assert (
        terminal_payload_content_text_from_payload(
            {"content": "\n\t"},
            text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
        )
        is None
    )


def test_terminal_payload_summary_preview_fields_are_not_content_sources() -> None:
    """terminal artifact 的 summary、preview 与 nested content 均不被读取。"""

    payload: dict[str, JsonValue] = {
        "summary_text": "摘要",
        "preview": "preview 不应读取",
        "result_preview": "result preview 不应读取",
        "summary": {"content": "nested content", "summary_text": "nested summary"},
    }

    assert (
        terminal_payload_content_text_from_payload(
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
        terminal_payload_content_text_from_payload(
            {"content": 123},
            text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
        )

    assert (
        terminal_payload_content_text_from_payload(
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
        terminal_payload_content_text_from_payload(
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
        terminal_payload_content_text_from_payload(
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
                    payload_ref="payload-terminal-payload-preference",
                    payload_id="sqlite-terminal-payload-preference",
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
    """terminal artifact descriptor 缺任一侧时 fail closed。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
        :raises AssertionError: resolver 未拒绝单边 descriptor 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:

        def operation(transaction: HostTransaction) -> None:
            """读取单边 descriptor 的 continuity 文本。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostDurableError: 任一 descriptor pair 不完整时抛出。
            """

            for payload in (
                {"terminal_summary_ref": "payload-terminal-payload-missing"},
                {"terminal_summary_digest": "sha256:missing"},
            ):
                for policy in (
                    PayloadTextReadPolicy.STRICT_NON_EMPTY,
                    PayloadTextReadPolicy.LENIENT_NON_EMPTY,
                ):
                    with pytest.raises(
                        HostDurableError,
                        match=(
                            "terminal_summary_ref and terminal_summary_digest must pair"
                        ),
                    ):
                        assistant_final_answer_continuity_text(
                            transaction,
                            payload,
                            text_policy=policy,
                        )

        store.transaction_runner.run_read(operation)


def test_continuity_resolver_rejects_malformed_terminal_descriptor(
    tmp_path: Path,
) -> None:
    """terminal artifact descriptor 字段类型非法时抛出 durable error。

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
    """terminal artifact digest 字段类型非法时抛出 durable error。

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
                    "terminal_summary_ref": "payload-terminal-payload",
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
            """写入 terminal artifact 并读取 continuity 文本。

            :param transaction: Host transaction。
            :returns: continuity 文本。
            """

            descriptor = PayloadStore().write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref="payload-terminal-payload",
                    payload_id="sqlite-terminal-payload",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json={
                        "content": "artifact final answer",
                        "summary_text": "artifact summary",
                        "summary": {"content": "nested summary content must not win"},
                        "preview": "preview must not win",
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


def test_required_continuity_resolver_rejects_missing_sources(
    tmp_path: Path,
) -> None:
    """required resolver 拒绝 inline 与 descriptor pair 同时缺失。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: optional/required 缺失策略不符合契约时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        optional = store.transaction_runner.run_read(
            lambda transaction: assistant_final_answer_continuity_text(
                transaction,
                {},
                text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
            )
        )
        assert optional is None
        with pytest.raises(
            HostDurableError,
            match="inline answer and descriptor pair are missing",
        ):
            store.transaction_runner.run_read(
                lambda transaction: required_assistant_final_answer_continuity_text(
                    transaction,
                    {},
                )
            )


def test_required_continuity_resolver_rejects_missing_descriptor_row(
    tmp_path: Path,
) -> None:
    """required resolver 为缺失 descriptor row 提供稳定诊断。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: descriptor 缺失未 fail closed 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        with pytest.raises(HostDurableError, match="descriptor is missing"):
            store.transaction_runner.run_read(
                lambda transaction: assistant_final_answer_continuity_text(
                    transaction,
                    {
                        "terminal_summary_ref": "payload-missing",
                        "terminal_summary_digest": "sha256:missing",
                    },
                    text_policy=PayloadTextReadPolicy.LENIENT_NON_EMPTY,
                )
            )
        with pytest.raises(HostDurableError, match="descriptor is missing"):
            store.transaction_runner.run_read(
                lambda transaction: required_assistant_final_answer_continuity_text(
                    transaction,
                    {
                        "terminal_summary_ref": "payload-missing",
                        "terminal_summary_digest": "sha256:missing",
                    },
                )
            )


def test_required_continuity_resolver_rejects_digest_mismatch(
    tmp_path: Path,
) -> None:
    """required resolver 拒绝 canonical digest 与 descriptor 不一致。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: digest mismatch 未 fail closed 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        descriptor = store.transaction_runner.run_write(
            lambda transaction: _write_terminal_payload(
                transaction,
                payload_ref="payload-digest-mismatch",
                payload_id="sqlite-digest-mismatch",
                payload_json={"content": "answer"},
            )
        )
        with pytest.raises(HostDurableError, match="payload digest mismatch"):
            store.transaction_runner.run_read(
                lambda transaction: assistant_final_answer_continuity_text(
                    transaction,
                    {
                        "terminal_summary_ref": descriptor.payload_ref,
                        "terminal_summary_digest": "sha256:not-the-descriptor-digest",
                    },
                    text_policy=PayloadTextReadPolicy.LENIENT_NON_EMPTY,
                )
            )
        with pytest.raises(HostDurableError, match="payload digest mismatch"):
            store.transaction_runner.run_read(
                lambda transaction: required_assistant_final_answer_continuity_text(
                    transaction,
                    {
                        "terminal_summary_ref": descriptor.payload_ref,
                        "terminal_summary_digest": "sha256:not-the-descriptor-digest",
                    },
                )
            )


@pytest.mark.parametrize(
    ("payload_json", "expected_fragment"),
    (
        ({}, "content is missing"),
        ({"content": " \n\t"}, "content is blank"),
    ),
)
def test_required_continuity_resolver_distinguishes_missing_and_blank_content(
    tmp_path: Path,
    payload_json: JsonValue,
    expected_fragment: str,
) -> None:
    """optional 省略 missing/blank content，required 保留分类诊断。

    :param tmp_path: pytest 临时目录。
    :param payload_json: terminal payload JSON。
    :param expected_fragment: required error 稳定片段。
    :returns: ``None``。
    :raises AssertionError: missing/blank taxonomy 不符合契约时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        descriptor = store.transaction_runner.run_write(
            lambda transaction: _write_terminal_payload(
                transaction,
                payload_ref=f"payload-{expected_fragment.replace(' ', '-')}",
                payload_id=f"sqlite-{expected_fragment.replace(' ', '-')}",
                payload_json=payload_json,
            )
        )
        run_payload: dict[str, JsonValue] = {
            "terminal_summary_ref": descriptor.payload_ref,
            "terminal_summary_digest": descriptor.payload_digest,
        }
        for policy in (
            PayloadTextReadPolicy.STRICT_NON_EMPTY,
            PayloadTextReadPolicy.LENIENT_NON_EMPTY,
        ):
            assert (
                store.transaction_runner.run_read(
                    lambda transaction: assistant_final_answer_continuity_text(
                        transaction,
                        run_payload,
                        text_policy=policy,
                    )
                )
                is None
            )
        with pytest.raises(HostDurableError, match=expected_fragment):
            store.transaction_runner.run_read(
                lambda transaction: required_assistant_final_answer_continuity_text(
                    transaction,
                    run_payload,
                )
            )


def test_continuity_resolver_rejects_non_text_descriptor_content_even_lenient(
    tmp_path: Path,
) -> None:
    """descriptor content 非文本时 strict/lenient/required 均 fail closed。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: lenient 吞掉 descriptor content 损坏时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        descriptor = store.transaction_runner.run_write(
            lambda transaction: _write_terminal_payload(
                transaction,
                payload_ref="payload-content-non-text",
                payload_id="sqlite-content-non-text",
                payload_json={"content": 42},
            )
        )
        run_payload: dict[str, JsonValue] = {
            "terminal_summary_ref": descriptor.payload_ref,
            "terminal_summary_digest": descriptor.payload_digest,
        }
        for policy in (
            PayloadTextReadPolicy.STRICT_NON_EMPTY,
            PayloadTextReadPolicy.LENIENT_NON_EMPTY,
        ):
            with pytest.raises(HostDurableError, match="content must be text"):
                store.transaction_runner.run_read(
                    lambda transaction, policy=policy: (
                        assistant_final_answer_continuity_text(
                            transaction,
                            run_payload,
                            text_policy=policy,
                        )
                    )
                )
        with pytest.raises(HostDurableError, match="content must be text"):
            store.transaction_runner.run_read(
                lambda transaction: required_assistant_final_answer_continuity_text(
                    transaction,
                    run_payload,
                )
            )


@pytest.mark.parametrize(
    ("payload_json", "expected_fragment"),
    (
        (b"123", "JSON is invalid"),
        ("{", "JSON is invalid"),
        ("[]", "JSON must be object"),
    ),
)
def test_required_continuity_resolver_rejects_invalid_sqlite_payload_json(
    tmp_path: Path,
    payload_json: str | bytes,
    expected_fragment: str,
) -> None:
    """required resolver 拒绝非文本、非法或非 object 的 SQLite payload JSON。

    :param tmp_path: pytest 临时目录。
    :param payload_json: test-only corruption 后的 SQLite 值。
    :param expected_fragment: 期望稳定错误片段。
    :returns: ``None``。
    :raises AssertionError: JSON 损坏未分类时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        descriptor = store.transaction_runner.run_write(
            lambda transaction: _write_terminal_payload(
                transaction,
                payload_ref=f"payload-invalid-json-{expected_fragment}-{payload_json}",
                payload_id=f"sqlite-invalid-json-{expected_fragment}-{payload_json}",
                payload_json={"content": "valid"},
            )
        )
        assert descriptor.sqlite_payload_id is not None
        store.transaction_runner.run_write(
            lambda transaction: transaction.execute(
                f"UPDATE {TABLE_SQLITE_PAYLOADS} SET payload_json = ? WHERE payload_id = ?",
                (payload_json, descriptor.sqlite_payload_id),
            )
        )
        with pytest.raises(HostDurableError, match=expected_fragment):
            store.transaction_runner.run_read(
                lambda transaction: assistant_final_answer_continuity_text(
                    transaction,
                    {
                        "terminal_summary_ref": descriptor.payload_ref,
                        "terminal_summary_digest": descriptor.payload_digest,
                    },
                    text_policy=PayloadTextReadPolicy.LENIENT_NON_EMPTY,
                )
            )
        with pytest.raises(HostDurableError, match=expected_fragment):
            store.transaction_runner.run_read(
                lambda transaction: required_assistant_final_answer_continuity_text(
                    transaction,
                    {
                        "terminal_summary_ref": descriptor.payload_ref,
                        "terminal_summary_digest": descriptor.payload_digest,
                    },
                )
            )


def test_required_continuity_resolver_rejects_missing_sqlite_payload_row(
    tmp_path: Path,
) -> None:
    """required resolver 为 descriptor 指向的缺失 SQLite row 提供诊断。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: SQLite row 缺失未 fail closed 时抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        descriptor = store.transaction_runner.run_write(
            lambda transaction: _write_terminal_payload(
                transaction,
                payload_ref="payload-sqlite-row-missing",
                payload_id="sqlite-row-missing",
                payload_json={"content": "valid"},
            )
        )
        assert descriptor.sqlite_payload_id is not None
        with sqlite3.connect(options.db_path) as connection:
            connection.execute(
                f"DELETE FROM {TABLE_SQLITE_PAYLOADS} WHERE payload_id = ?",
                (descriptor.sqlite_payload_id,),
            )
        with pytest.raises(HostDurableError, match="sqlite payload row is missing"):
            store.transaction_runner.run_read(
                lambda transaction: assistant_final_answer_continuity_text(
                    transaction,
                    {
                        "terminal_summary_ref": descriptor.payload_ref,
                        "terminal_summary_digest": descriptor.payload_digest,
                    },
                    text_policy=PayloadTextReadPolicy.LENIENT_NON_EMPTY,
                )
            )
        with pytest.raises(HostDurableError, match="sqlite payload row is missing"):
            store.transaction_runner.run_read(
                lambda transaction: required_assistant_final_answer_continuity_text(
                    transaction,
                    {
                        "terminal_summary_ref": descriptor.payload_ref,
                        "terminal_summary_digest": descriptor.payload_digest,
                    },
                )
            )
