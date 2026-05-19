# PR 62 Re-Review — AgentMiMo

## Scope

- Mode: PR re-review（Gateflow-governed）
- PR: #62 — Host P10.5 ordinary local multi-turn public contract freeze
- Head: `feat/host-p10-5-public-contract-freeze` → `main`
- Review date: 2026-05-19
- Re-review 目标：复核本轮 PR review fix 是否真正修复 accepted findings，并检查 fix 是否引入新 blocker
- Source review artifacts：
  - `docs/reviews/pr-62-deepreview-mimo.md`（结论 FAIL）
  - `docs/reviews/pr-62-deepreview-ds.md`（结论 PASS）
  - `docs/reviews/pr-62-review-fix-codex.md`
- Included scope：10 项 accepted findings 的 fix 验证 + fix 引入新 blocker 检查
- Excluded scope：无

---

## Findings

### 1-已修复-中-HostHandle 兼容别名已删除

- **验证文件**: `dayu/host/__init__.py`、`dayu/host/api.py:2798-2865`、`tests/host/test_package_exports.py:154-170,225-228`
- **直接证据**:
  - `__init__.py` 无 `HostHandle` 导入或 `__all__` 条目
  - `api.py:2798-2865` `__all__` 不包含 `HostHandle`
  - `REMOVED_SERVICE_FACING_ALL_EXPORTS`（test_package_exports.py:154-170）包含 `"HostHandle"`
  - `test_removed_low_level_symbols_are_not_service_facing_all_exports` 验证 `HostHandle` 不进入 `host.__all__`
  - `test_removed_low_level_symbols_are_not_package_root_attributes` 验证 `HostHandle` 不作为包根模块属性
- **结论**: fix 完整，兼容别名已从包根、`api.__all__` 和模块属性三处清除。

### 2-已修复-中-api.__all__ 已移除 6 个内部类型

- **验证文件**: `dayu/host/api.py:2798-2865`、`tests/host/test_package_exports.py:10-79,190-193`
- **直接证据**:
  - `api.__all__` 不包含 `HostCommandFacet`、`HostCommandHandleOptions`、`HostEventStream`、`HostEventView`、`HostLocalExecutionOptions`、`StartRunRequest`
  - `EXPECTED_API_EXPORTS`（test_package_exports.py:10-79）不包含这 6 个名称
  - `test_api_all_stays_request_snapshot_boundary` 验证 `frozenset(api.__all__) == EXPECTED_API_EXPORTS`
- **结论**: fix 完整，`api.__all__` 只保留 request/snapshot/status/error/context/stream cursor/public opener options/HostEvent typed view。

### 3-已修复-中-HostInput 不再作为 Service-facing public export

- **验证文件**: `dayu/host/__init__.py`、`tests/host/test_package_exports.py:110-120,122-126,225-228`
- **直接证据**:
  - `__init__.py` 无 `HostInput` 导入或 `__all__` 条目
  - `ROOT_INTERNAL_API_NAMES`（test_package_exports.py:110-120）包含 `"HostInput"`
  - `EXPECTED_HOST_EXPORTS = (EXPECTED_API_EXPORTS - ROOT_INTERNAL_API_NAMES) | ...` — `HostInput` 被差集排除
  - `test_removed_low_level_symbols_are_not_service_facing_all_exports` 验证 `HostInput` 不进入 `host.__all__`
  - `test_removed_low_level_symbols_are_not_package_root_attributes` 验证 `HostInput` 不作为包根模块属性
  - `HostInput` 类定义仍保留在 `api.py` 内部，供 `admission.py`（line 32）和 `command.py` 内部使用 — 定义保留合理，不构成 public export 残留
- **结论**: fix 完整。`HostInput` 定义保留供内部使用，不再从包根或 `api.__all__` 公开导出。

### 4-已修复-低-read_api.__all__ 已移除 stream_run_events

- **验证文件**: `dayu/host/read_api.py:722`、`tests/host/test_package_exports.py:196-199`
- **直接证据**:
  - `read_api.py:722`: `__all__ = ["get_run", "get_session"]` — 不包含 `stream_run_events`
  - `test_read_api_all_keeps_service_facing_read_boundary`: `frozenset(read_api.__all__) == frozenset({"get_run", "get_session"})`
- **结论**: fix 完整。`stream_run_events` 函数定义仍保留在 `read_api` 供内部 diagnostic 使用，但不再进入 `__all__`。

### 5-已修复-低-__init__.py docstring 已清除旧 Phase 4 语义

- **验证文件**: `dayu/host/__init__.py:1-6`
- **直接证据**:
  - 当前 docstring: `"本包当前导出公共类型契约、Host construction 的业务工具输入边界，以及 Session / Run public facade。"` — 无 "Phase 4" 引用
  - 描述性文字准确反映当前代码状态
- **结论**: fix 完整，docstring 只描述当前已实现边界。

### 6-已修复-高-fake_compaction budget_after_compact 已与真实 LLM compactor clamp 同源

- **验证文件**: `dayu/host/fake_compaction.py:196-205`、`tests/host/test_compaction_contract.py`
- **直接证据**:
  - `fake_compaction.py:203-205`:
    ```python
    half_estimate = request.budget_before_compact.estimated_input_tokens // 2
    hard_threshold_limit = request.budget_before_compact.hard_threshold_tokens - 1
    return max(0, min(half_estimate, hard_threshold_limit))
    ```
  - 与 `llm_compaction.py:450-451` 的 `min(half_estimate, estimate.hard_threshold_tokens - 1)` 语义一致
  - 增加了 `max(0, ...)` 非负 clamp，比真实 compactor 更保守但安全
  - 测试覆盖 fake compactor clamp 行为
- **结论**: fix 完整。`_budget_after_compact` 使用 `min(estimated // 2, hard_threshold_tokens - 1)` 并保持非负 clamp，与真实 LLM compactor 同源。

### 7-已修复-高-engine_ingest reactive compaction 已增加 stale input_event_sequence guard

- **验证文件**: `dayu/host/engine_ingest.py:336-345,1156,1415-1444`、`tests/host/test_engine_ingest_mapping.py:482-511`
- **直接证据**:
  - `_ReactiveCompactPending` 新增 `expected_input_event_sequence: int` 字段（line 341）
  - pending 构造时保存 `expected_input_event_sequence=context.run.input_event_sequence`（line 1156）
  - `_operation()` 内在写事务中执行 stale 检查（lines 1423-1444）：
    ```python
    sequence_stale = (
        latest.run.input_event_sequence
        != pending.expected_input_event_sequence
    )
    if latest.run.status is RunStatus.RECOVERING and sequence_stale:
        stale_failed = self._append_reactive_compaction_failed_event(
            transaction, context=latest, ...,
            failure_reason="stale_compaction_result",
        )
        return EngineIngestResult(...)
    ```
  - stale 场景写 `CONTEXT_COMPACTION_FAILED(failure_reason=stale_compaction_result)`，不写 `CONTEXT_COMPACTED`，不启动 recovery Attempt
  - `test_reactive_compaction_rejects_stale_input_sequence`（line 482）覆盖 stale 场景：使用 `_InputSequenceAdvancingCompactor` 在 compaction proposal 期间推进 durable input sequence，验证返回 `CONTEXT_COMPACTION_FAILED` 且 `failure_reason == "stale_compaction_result"`
- **结论**: fix 完整。reactive compaction 在写回前做事务内 stale guard，stale 场景写 failed event 而非 compacted event。

### 8-已修复-低-runtime/lane.py cancellation cleanup 已显式 raise cancelled

- **验证文件**: `dayu/runtime/lane.py:663-679`、`tests/runtime/test_lane.py`
- **直接证据**:
  - `lane.py:663`: `except asyncio.CancelledError as cancelled:`
  - `lane.py:668`: `raise cancelled`（RuntimeLaneClaimLostError 分支）
  - `lane.py:677`: `raise cancelled`（RuntimeLaneError 分支）
  - `lane.py:679`: `raise cancelled`（正常 refresh 完成后 re-raise）
  - 三处均为显式 `raise cancelled`，与 line 663 捕获的变量名一致
  - 无 bare `raise`，无行为回归
- **结论**: fix 完整。所有 cancellation cleanup 分支均显式 `raise cancelled`。

### 9-已修复-中-admission 大 USER_INPUT_ACCEPTED payload descriptor 修复

- **验证文件**: `dayu/host/admission.py:2962-2991`、`dayu/host/payload_resolution.py:17-55`、`dayu/host/dispatch.py:522-528`、`dayu/host/engine_ingest.py:2648-2650`、`dayu/host/run_input.py:94`
- **直接证据**:

  **admission 写入路径**:
  - `admission.py:2962-2991`（`_maybe_write_user_input_payload_descriptor`）：
    ```python
    encoded = canonical_json_dumps(payload)
    if len(encoded.encode("utf-8")) <= transaction.payload_inline_threshold_bytes:
        return None  # inline，不写 descriptor
    return PayloadStore().write_sqlite_payload(
        transaction,
        SQLitePayloadWriteRequest(
            payload_ref=f"payload-user-input-{event_id}",
            payload_id=f"sqlite-payload-user-input-{event_id}",
            payload_format=SQLitePayloadFormat.CANONICAL_JSON,
            payload_json=payload,
            ...
        ),
    )
    ```
  - 超限时把完整 payload 写入 SQLite payload 表，EventLog row 通过 `payload_ref` / `payload_digest` 引用 descriptor
  - `admission.py:2932-2933`: EventLog append 使用 `payload_ref=None if descriptor is None else descriptor.payload_ref`

  **读取路径**:
  - `payload_resolution.py:17-55`（`event_payload_object`）：inline 时直接解析 `payload_json`；有 descriptor 时校验 `PayloadKind.SQLITE_PAYLOAD`、digest 匹配、从 `TABLE_SQLITE_PAYLOADS` 读取完整 payload
  - `dispatch.py:525-528`: RunInputBuilder 使用 `event_payload_object` 读取 `USER_INPUT_ACCEPTED`
  - `engine_ingest.py:2648-2650`: ingest 使用 `event_payload_object` 读取 display_text
  - `run_input.py:94`: `from dayu.host.payload_resolution import event_payload_object`

  **设计一致性**:
  - 使用 SQLite payload descriptor 符合 `docs/host/design.md` 的 Payload 存储语义和 `dayu/README.md:161` 描述的 payload descriptor primitive
  - descriptor 校验覆盖 payload_kind、digest 匹配、sqlite_payload_id 存在性
  - digest 使用 `sha256_digest_json`，与同事务写入一致
  - 读取路径所有 consumer 统一通过 `event_payload_object` helper，不存在遗漏的 direct inline 读取

- **结论**: fix 完整。超过 `payload_inline_threshold_bytes` 时 admission 写 SQLite payload descriptor，dispatch / engine_ingest / RunInputBuilder 统一通过 `event_payload_object` 跟随 descriptor 读取完整 payload。设计符合 Host payload store 边界。

### 10-已修复-低-README 同步只写当前已实现边界

- **验证文件**: `dayu/README.md`、`dayu/host/README.md`、`tests/README.md`
- **直接证据**:
  - `dayu/README.md`: 无 "Phase 4"、"Phase 9"、"Phase 10" 等过程阶段标记（除核心术语段中对 Host-owned LLM compaction 的稳定描述）；无 "未来计划"、"待实现" 等过程状态
  - `dayu/host/README.md:30`: `HostInput`、低层 `StartRunRequest`、command-handle construction types、本地执行配置契约类型与 run-level stream DTO 不进入 public `__all__` — 准确描述当前状态
  - `dayu/host/README.md:157`: `canonical_fact 的 inline payload_json 受当前 durable store 注入的 payload inline 阈值约束，超限内容必须使用 payload descriptor / artifact ref 与 digest 边界；USER_INPUT_ACCEPTED 的完整 prompt payload 可通过 SQLite payload descriptor 保存，RunInputBuilder 与 ingest 读取时跟随 descriptor 取得真源内容` — 准确描述已实现行为
  - `tests/README.md:99`: 包含 `canonical fact inline payload size guard 与 store policy 注入`、`大 USER_INPUT_ACCEPTED descriptor 溢出` — 准确描述已覆盖测试
  - 文档示例对应当前接口、命令、参数名
  - 无旧术语、旧路径、旧入口、旧架构表述
  - 文档职责未越界
- **结论**: fix 完整。README 只写当前已实现边界，无过程状态/未来计划/旧语义残留。

---

## Fix 引入新 Blocker 检查

### 无新 blocker

逐项检查 fix 变更：

1. **HostHandle / HostInput / api.__all__ 清理**：纯删除操作，不影响运行时行为。
2. **fake_compaction budget clamp**：单行预算计算逻辑变更，`max(0, min(...))` 比原实现更保守，不可能引入 regression。
3. **reactive compaction stale guard**：新增 `_ReactiveCompactPending.expected_input_event_sequence` 字段和事务内 stale 检查。stale 时写 `CONTEXT_COMPACTION_FAILED` 而非静默跳过——比 proactive 路径更显式，是合理的差异（reactive 路径已有 LLM 开销，静默跳过会浪费诊断信息）。不写 `CONTEXT_COMPACTED`、不启动 recovery Attempt，无状态泄漏。
4. **lane.py cancellation cleanup**：bare `raise` 改为显式 `raise cancelled`，行为等价。
5. **payload descriptor**：新增 `payload_resolution.py` helper 和 admission 写入逻辑。读取路径统一通过 `event_payload_object`，无 direct inline 读取遗漏。descriptor 校验覆盖 payload_kind、digest、sqlite_payload_id 三重验证。
6. **README 同步**：纯文档变更。

---

## Open Questions

无。

## Residual Risk

1. **proactive 路径 stale 检查窄于 reactive 路径**：`dispatch.py:940-943` 的 proactive stale 检查（status + input_event_sequence）在 compaction 成功后若发现 stale，静默跳过不写任何 event。reactive 路径在同样场景下写 `CONTEXT_COMPACTION_FAILED(failure_reason=stale_compaction_result)`。两路径行为差异在当前 PR scope 内可接受，但后续应统一。此为已有 residual risk，非本次 fix 引入。

2. **`stream_run_events` 函数定义仍保留在 `read_api` 内部**：不再进入 `__all__`，但内部 diagnostic / 低层测试仍可显式模块路径导入。符合 fix 设计意图。

3. **`HostInput` 类定义仍保留在 `api.py` 内部**：供 `admission.py` / `command.py` 使用，不再作为 public export。符合 fix 设计意图。

---

## 结论

**PASS**

全部 10 项 accepted findings 已修复，fix 未引入新 blocker。各项 fix 均有直接代码证据支撑，测试覆盖对应行为和边界条件。
