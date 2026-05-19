"""P10.5 Slice 5 public real-compactor smoke。"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Mapping
from dataclasses import replace
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host import CompactorRunnerBaseline, HostEventKind, open_host
from dayu.host.context_policy import default_context_budget_policy
from tests.host.public_smoke_support import (
    PROVIDER_CASES,
    FinalAnswerWorkerFactory,
    api_key_or_skip,
    ensure_request,
    followup_request,
    next_terminal_for_run,
    open_host_options,
    runner_spec_for_case,
    skip_if_provider_exception,
    skip_if_provider_terminal_failed,
)

_SOFT_CONTEXT_WINDOW_SIZE = 110
_SOFT_RESERVED_OUTPUT_TOKENS = 10
_SOFT_HARD_THRESHOLD_TOKENS = 95
_SOFT_SAFETY_MARGIN_RATIO = 0.2
_SOFT_THRESHOLD_PROMPT_CHAR_COUNT = 220
_COMPACTOR_PROVIDER_MAX_RETRIES = 1
_COMPACTOR_MAX_ATTEMPTS_PER_OPERATION = 2
_COMPACT_ARTIFACT_KIND_FIELD = "artifact_kind"
_COMPACT_ARTIFACT_KIND = "context_compaction"
_ACCEPTED_CANDIDATE_FIELD = "accepted_candidate"
_CANDIDATE_ID_FIELD = "candidate_id"
_INPUT_SNAPSHOT_REFS_FIELD = "input_snapshot_refs"
_CURRENT_USER_INPUT_REF_FIELD = "current_user_input_ref"


@pytest.mark.asyncio
async def test_real_compactor_public_opener_compacts_and_preserves_continuity(
    tmp_path: pathlib.Path,
) -> None:
    """public opener 触发真实 compactor，并在后续 run 保持连续性。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: compact 未触发或 terminal 不成功时抛出。
    """

    case = PROVIDER_CASES[1]
    api_key = api_key_or_skip(case)
    runner_spec = runner_spec_for_case(case, api_key)
    compactor_runner_spec = replace(
        runner_spec,
        provider_request=None,
        max_retries=_COMPACTOR_PROVIDER_MAX_RETRIES,
    )
    runner_options = RunnerCallOptions(
        temperature=0.0,
        max_tokens=512,
        top_p=None,
        stream=True,
    )
    compact_artifact_root = tmp_path / "compact-artifacts"
    artifact_files_before = _compact_artifact_files(compact_artifact_root)
    worker_factory = FinalAnswerWorkerFactory()
    base_options = open_host_options(
        tmp_path,
        runner_spec=compactor_runner_spec,
        worker_factory=worker_factory,
        allow_tool_calls=False,
        max_tokens=512,
    )
    base_options = replace(
        base_options,
        ordinary_run_baseline=replace(
            base_options.ordinary_run_baseline,
            runner_options=runner_options,
        ),
    )
    options = replace(
        base_options,
        context_budget_policy=default_context_budget_policy(
            context_window_size=_SOFT_CONTEXT_WINDOW_SIZE,
            reserved_output_tokens=_SOFT_RESERVED_OUTPUT_TOKENS,
            hard_threshold_tokens=_SOFT_HARD_THRESHOLD_TOKENS,
            safety_margin_ratio=_SOFT_SAFETY_MARGIN_RATIO,
            minimum_protection_tokens=1,
            max_compaction_attempts_per_operation=(
                _COMPACTOR_MAX_ATTEMPTS_PER_OPERATION
            ),
            policy_ref="slice5-real-compact-policy",
        ),
        compactor_runner_baseline=CompactorRunnerBaseline(
            compactor_runner_spec=compactor_runner_spec,
            compactor_runner_options=runner_options,
            compact_artifact_root=compact_artifact_root,
            compact_artifact_create_parent_dirs=True,
        ),
    )

    try:
        async with open_host(options) as host:
            session = await host.ensure_session(ensure_request("real-compact"))
            watcher = host.watch_session_events(session.session_id)
            compacted = await host.submit_followup(
                session.session_id,
                followup_request(
                    session.session_id,
                    "compact-first",
                    "x" * _SOFT_THRESHOLD_PROMPT_CHAR_COUNT,
                ),
            )
            first_terminal = await next_terminal_for_run(
                watcher, compacted.accepted_run_id
            )
            skip_if_provider_terminal_failed(case, first_terminal)
            followup = await host.submit_followup(
                session.session_id,
                followup_request(
                    session.session_id,
                    "compact-second",
                    "基于已经压缩的上下文，只输出 DAYU_COMPACT_OK。",
                ),
            )
            second_terminal = await next_terminal_for_run(
                watcher, followup.accepted_run_id
            )
    except RuntimeError as exc:
        skip_if_provider_exception(case, exc)
        raise

    skip_if_provider_terminal_failed(case, second_terminal)
    assert first_terminal.kind is HostEventKind.SUCCEEDED
    assert second_terminal.kind is HostEventKind.SUCCEEDED
    assert first_terminal.session_id == session.session_id
    assert second_terminal.session_id == session.session_id
    assert first_terminal.run_id == compacted.accepted_run_id
    assert second_terminal.run_id == followup.accepted_run_id
    assert second_terminal.final_answer is not None
    assert second_terminal.final_answer.content.strip() != ""
    artifact_files_after = _compact_artifact_files(compact_artifact_root)
    new_artifacts = tuple(
        path for path in artifact_files_after if path not in artifact_files_before
    )
    assert len(new_artifacts) > 0
    artifact = _compact_artifact_for_run(new_artifacts, compacted.accepted_run_id)
    input_snapshot = _required_mapping(
        artifact[_INPUT_SNAPSHOT_REFS_FIELD],
        field_name=_INPUT_SNAPSHOT_REFS_FIELD,
    )
    current_user_input_ref = input_snapshot[_CURRENT_USER_INPUT_REF_FIELD]
    assert isinstance(current_user_input_ref, str)
    assert current_user_input_ref.strip() != ""


def _compact_artifact_files(root: pathlib.Path) -> tuple[pathlib.Path, ...]:
    """返回 compact artifact 根目录下的已发布文件。

    :param root: compact artifact 根目录。
    :returns: 按路径排序的文件 tuple。
    :raises Exception: 不主动抛出异常。
    """

    if not root.exists():
        return ()
    return tuple(sorted(path for path in root.rglob("*") if path.is_file()))


def _compact_artifact_for_run(
    paths: tuple[pathlib.Path, ...], run_id: str
) -> Mapping[str, JsonValue]:
    """从 artifact 文件集合中找出匹配指定 Run 的 compact artifact。

    :param paths: 候选 artifact 文件路径。
    :param run_id: 本次 compact 关联的 Host Run id。
    :returns: artifact JSON object。
    :raises AssertionError: 没有找到匹配 artifact 时抛出。
    """

    expected_candidate_id = f"llm-compact:{run_id}"
    for path in paths:
        artifact = _required_mapping(_read_json(path), field_name=str(path))
        if artifact.get(_COMPACT_ARTIFACT_KIND_FIELD) != _COMPACT_ARTIFACT_KIND:
            continue
        candidate = _required_mapping(
            artifact[_ACCEPTED_CANDIDATE_FIELD],
            field_name=_ACCEPTED_CANDIDATE_FIELD,
        )
        if candidate.get(_CANDIDATE_ID_FIELD) == expected_candidate_id:
            return artifact
    raise AssertionError(f"compact artifact for run {run_id} was not found")


def _read_json(path: pathlib.Path) -> JsonValue:
    """读取 JSON artifact。

    :param path: artifact 文件路径。
    :returns: JSON 值。
    :raises OSError: 文件读取失败时抛出。
    :raises json.JSONDecodeError: JSON 解析失败时抛出。
    """

    return cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))


def _required_mapping(
    value: JsonValue, *, field_name: str
) -> Mapping[str, JsonValue]:
    """校验 JSON 值为 object。

    :param value: 待校验 JSON 值。
    :param field_name: 错误字段名。
    :returns: JSON object。
    :raises AssertionError: 值不是 object 时抛出。
    """

    assert isinstance(value, Mapping), f"{field_name} must be JSON object"
    return value
