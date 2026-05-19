# Host-owned Compactor Final Review — DeepReview DS

## Scope

- Mode: current changes
- Branch: `feat/host-p10-5-public-contract-freeze`
- Base: `main`
- Output file: `docs/reviews/host-owned-compactor-final-review-ds.md`
- Included scope: `dayu/host/__init__.py`, `dayu/host/api.py`, `dayu/host/llm_compaction.py`, `dayu/host/open_host.py`, `dayu/host/compaction_operation.py`, `dayu/host/context_events.py`, `dayu/host/context_policy.py`, `dayu/host/dispatch.py` (proactive compact), `dayu/host/engine_ingest.py` (reactive compact), `dayu/host/read_api.py` (HostEvent mapping), `utils/smoke_host_public_multiturn.py`, `tests/host/test_public_compact_smoke.py`, `tests/host/test_public_open_host_options.py`, `tests/host/test_llm_compaction.py`, `tests/host/test_context_compact_events.py`, `tests/host/test_package_exports.py`, `tests/host/test_open_host_runtime.py`, `tests/host/test_dispatch_scheduler.py`, `tests/host/test_engine_ingest_mapping.py`, `README.md`, `dayu/host/README.md`, `tests/README.md`, `docs/host/design.md`, `docs/host/host-owned-compactor-plan.md`, 及所有 `docs/reviews/` 下的已完成 review artifacts。
- Excluded scope: `dayu/render/`、`utils/`（除 `smoke_host_public_multiturn.py` 外）、`dayu/engine/`、`dayu/fins/`、`dayu/service/`、`dayu/ui/`、`dayu/runtime/` — 不在此次 Host-owned compactor 变更范围。
- Parallel review coverage: 无 — 本 review 为第二路独立 reviewer 对完整 PR 的统一 review。

## Verdict

**PASS** — 未发现必须修复的 correctness、stability 或 security finding。

## Findings

未发现实质性问题。

### Review 覆盖的七个检查维度

#### 1. Service-facing public contract 是否仍有 ContextCompactor/prompt/candidate/quality/policy_ref 泄漏

**结论：无泄漏。**

- `CompactorRunnerBaseline` (`api.py:921-953`) 只包含 `compactor_runner_spec`、`compactor_runner_options`、`compact_artifact_root`、`compact_artifact_create_parent_dirs` 四个字段；不含 `ContextCompactor`、prompt、candidate builder、quality callback 或 raw `policy_ref`。
- `OpenHostOptions.compactor_runner_baseline` (`api.py:1022`) 替代了旧字段 `compactor_baseline`。
- `CompactorExecutionBaseline` 在全量生产代码中已彻底移除（`grep` 结果：仅在 `tests/host/test_package_exports.py` 的 `REMOVED_SERVICE_FACING_ALL_EXPORTS` 集中出现，用于断言不存在于包根）。
- `dayu/host/__init__.py` 包根导出 `CompactorRunnerBaseline`，不导出 `ContextCompactor`、`CompactorExecutionBaseline`、`HostLocalExecutionOptions`。
- `api.py:34` 保留 `from dayu.host.compaction import ContextCompactor`，仅用于 `HostLocalExecutionOptions.context_compactor` 的类型注解；`HostLocalExecutionOptions` 是 Host 内部类型，不进入包根 `__all__` 或 Service-facing public contract。
- `HostLocalExecutionOptions.compactor_policy_ref` (`api.py:749`) 保留为 `str | None = None`，`open_host.py:643` 始终传 `None`；Service 无法通过 `OpenHostOptions` 或 `CompactorRunnerBaseline` 设置该字段。

**验证路径：**
```
grep -r "CompactorExecutionBaseline" dayu/          # 无结果
grep -r "CompactorExecutionBaseline" utils/         # 无结果
grep "from dayu.host import.*ContextCompactor" tests/ utils/  # 无结果
```

#### 2. Host ownership 是否被 smoke/test 或 OpenHostOptions 破坏

**结论：Host ownership 完整。**

- `LLMContextCompactor` 只在 `open_host.py:611-614` 的 `_local_execution_options_from_open_host_options` 中构造，构造参数仅来自 `CompactorRunnerBaseline` 的 runner spec/options。
- `utils/smoke_host_public_multiturn.py`：不再定义 `DeepSeekContextCompactor` 或任何 `ContextCompactor` 子类；只通过 `CompactorRunnerBaseline` 传 runner/config/artifact root；stdout 不再打印 `compactor.call_count` / `last_summary`。
- `tests/host/test_public_compact_smoke.py`：从 `dayu.host` 导入 `CompactorRunnerBaseline`，不导入 `ContextCompactor`；不定义 `_RealLLMContextCompactor`。
- 低层测试（`test_dispatch_scheduler.py`、`test_engine_ingest_mapping.py`）使用 `from dayu.host.compaction import ContextCompactor` 和 `from dayu.host.fake_compaction import FakeContextCompactor`，直接注入 `HostLocalExecutionOptions(context_compactor=...)` 作为 low-level test seam——符合 plan §3.5。

#### 3. Compactor dirty-data / provider failure 的 attempt rejected、failed、retry 语义是否可观察

**结论：可观察，语义完整。**

- `compaction_operation.py:run_compaction_operation()` 按 `max_attempts` 编排 bounded attempts：每次 attempt 尝试 `compactor.compact(request)` → quality check → hard threshold check，三类失败均生成 `CompactionAttemptRejected` 摘要。
- `dispatch.py:_execute_proactive_compaction()` (line 882-965) 和 `engine_ingest.py:_execute_reactive_compaction()` (line 1325-1435) 均将 rejected attempts 通过 `_append_compaction_attempt_rejected_event` 写入 EventLog `CONTEXT_COMPACTION_ATTEMPT_REJECTED` canonical fact。
- `context_events.py` 定义了完整的 `build/validate_context_compaction_attempt_rejected_payload`，必填字段包含 `operation_id`、`attempt_number`（正整型校验）、`failure_category`、`repairable`、`runner_attempt_summary_refs`、`diagnostic_refs`、`next_policy_decision`、`budget_after_attempted_compact`。
- `read_api.py:_host_event_from_row()` (line 408-436) 只对 `RUN_SUCCEEDED`/`RUN_FAILED`/`RUN_CANCELLED` 映射为 terminal `HostEventKind`，其余所有 EventLog row（含 `CONTEXT_COMPACTION_*` 全部四种 event type）统一映射为 `HostEventKind.PROGRESS`——保守映射，符合 design §3.6。
- Engine runner 内部 HTTP retry 不写 EventLog compact fact，不 emit HostEvent——符合 plan §3.6。

#### 4. Artifact 与 memory projection 边界是否符合设计

**结论：边界符合设计。**

- `llm_compaction.py:_candidate_from_summary()` (line 345-411) 负责将 LLM summary 文本映射为 `CompactionCandidate`；LLM 只提供 summary 文本，refs、preservation evidence、budget estimate、pinned patch 均由 Host 代码构造。
- Quality check (`context_governance.check_compaction_candidate`) 在 `compaction_operation.py:117` 被调用，拒绝丢失当前用户输入、伪造 verified fact、缺失 preservation evidence 等情况。
- `CONTEXT_COMPACTED` 是唯一进入 memory projection 的 compact 事实（`dayu/host/README.md:135`）；`CONTEXT_COMPACTION_FAILED` 和 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 不进入 memory projection filter。
- Artifact store (`compact_artifact.py`) 和 memory projection consumer (`durable/memory.py`) 的所有权保持在 Host 内部——不变更。

#### 5. 日志/异常诊断是否可能泄漏 secret 或造成噪音

**结论：不泄漏，噪音可控。**

- `llm_compaction.py:_safe_outcome_text()` (line 274-290) 在构造异常消息前对 provider/runner 错误文本执行两层脱敏：`_BEARER_SECRET_PATTERN` 匹配 Bearer token 并替换为 `<redacted>`，`_ASSIGNMENT_SECRET_PATTERN` 匹配 `api_key=...` / `authorization: ...` 赋值并替换值部分为 `<redacted>`；脱敏后截断至 240 字符。
- 脱敏后的异常消息仅进入 `LLMCompactionProposalError` 实例；在 `compaction_operation.py:96-106` 被 `except Exception as exc` 捕获后，仅 `exc.__class__.__name__`（即 `"LLMCompactionProposalError"`）作为 `diagnostic_suffix` 使用——异常消息从不进入 EventLog 或任何持久化存储。
- `compaction_operation.py` 不包含 `logging.exception()` 或 `exc_info=True` 调用。
- `dispatch.py` 和 `engine_ingest.py` 的 compact 执行路径（`_execute_proactive_compaction` / `_execute_reactive_compaction`）不包含对 `run_compaction_operation` 返回值的 `exc_info=True` 日志。
- dispatcher worker event stream 中的 `exc_info=True`（dispatch.py:2405, 2441）属于 worker lifecycle 异常处理，不直接涉及 compactor prompt/secret 泄漏——这些日志只包含 `run_id`、`attempt_id`、`execution_id`、`error_type`（类名），不包含异常消息或 provider payload。
- 未观察到可产生 EventLog/HostEvent 噪音的情况：runner 内部 HTTP retry 不写 EventLog compact fact。

#### 6. README 是否有旧语义残留

**结论：无旧语义残留。**

- 根 `README.md`：manual smoke 描述更新为"脚本只通过 `OpenHostOptions` 提供 runner/config/artifact root"；不提及 `DeepSeekContextCompactor`、`CompactorExecutionBaseline` 或 Service 注入 compactor port。
- `dayu/host/README.md`：
  - 公开命名空间列表（line 18）将 `CompactorExecutionBaseline` 替换为 `CompactorRunnerBaseline`。
  - Context Governance Boundary 章节（line 129-147）明确：`CompactorRunnerBaseline` 不进入低层装配语义、"普通调用方不能传入 compact prompt、candidate builder、quality override、raw policy ref 或低层 compactor port"、`ContextCompactor` 只作为 Host 内部/低层测试 seam 使用。
  - 无 `CompactorExecutionBaseline` 残留引用。
- `tests/README.md`（line 96）：public compact smoke 描述使用 `CompactorRunnerBaseline`，并区分 env-gated real provider smoke 与 no-network unit tests。

#### 7. Correctness / Stability / Security 必须修复的 finding

**结论：无。**

沿以下关键路径逐行走读未发现 correctness 缺陷：

- **LLM 调用事务边界**：`dispatch.py:853-858` 先 `run_write(_operation)`（冻结 input snapshot + `CONTEXT_COMPACTION_REQUESTED`），再 `_execute_proactive_compaction(stage.compact_pending)`（事务外）；`_execute_proactive_compaction:900` 调用 `run_compaction_operation()`（事务外 LLM call），`line 965` 再 `run_write(_operation)`（recheck + write result）。`engine_ingest.py:533-535` 同理。两条路径均保证真实 LLM 调用不持有 Host write transaction。

- **Stale result 策略**：proactive（dispatch.py:907-924）和 reactive（engine_ingest.py:1357-1369）均在写入结果前 recheck run status、expected input event sequence/cursor、recovering context；状态不匹配时写入 `CONTEXT_COMPACTION_FAILED` 或 `failure_reason="stale_compaction_result"`，不写 `CONTEXT_COMPACTED`。

- **CancellationToken 隔离**：`LLMContextCompactor` 使用 `_NeverCancelledToken`（`llm_compaction.py:89-115`），不接收 Service cancellation token；外部 LLM 调用完成后由 dispatch/ingest 在写入结果前重新检查 durable state——符合 plan §3.2。

- **Budget policy 校验**：`ContextBudgetPolicy.__post_init__` 对 `max_compaction_attempts_per_operation` 使用 `_require_positive_int`（`context_policy.py:123-128`），拒绝 0、负数和 bool。

- **Candidate 构造保守性**：`_candidate_from_summary` 中的 refs、evidence、budget 均来自 immutable `CompactionRequest`；LLM 只提供 summary 文本；`_budget_after_compact` 使用保守估算（取 estimated_input_tokens 的一半与 hard_threshold 的最小值）。

- **EventLog 幂等**：event_id 由 `_event_id()` helper 基于 session/run/event_class/event_type/sequence 生成；同一 event_type 重复 append 由 EventLog primitive 幂等处理。

- **Stale state 不污染**：`HostLocalExecutionOptions.compactor_policy_ref` 始终为 `None`（`open_host.py:643`），不会因遗留值被误解为有效 policy ref。

## Open Questions

- `_safe_outcome_text` 的脱敏正则 `_ASSIGNMENT_SECRET_PATTERN` 只覆盖 `api_key` 和 `authorization` 两种 key 名。若 Engine runner 返回的错误消息中以其他 key 名（如 `x-api-key`、`token`、`secret`）传递密钥，当前脱敏不会捕获。但此函数的输出仅进入异常消息，该异常被 `run_compaction_operation` 捕获后只取类名（`__class__.__name__`），消息文本不进入 EventLog 或任何持久化存储——实际暴露风险极低。若未来代码在 `run_compaction_operation` 内部或上游增加 `exc_info=True` 日志，需要同步扩展脱敏覆盖。

## Residual Risk

- **真实 provider 行为不稳定**：Host-owned `LLMContextCompactor` 依赖真实 LLM provider；pytest 已通过 env-gated skip 避免默认依赖网络。人工 smoke 需要有效的 `DEEPSEEK_API_KEY` 和网络连接。
- **单 attempt 默认值**：`DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION = 1`（`context_policy.py:25`）意味着默认配置下不会有 semantic repair retry——首次 proposal 失败或 quality reject 即 `CONTEXT_COMPACTION_FAILED`。这是第一版保守默认值，符合 plan 5.2 "不做事项"（不引入网络 pytest，不把 semantic repair 交给 Service replay）。
- **未覆盖的 adversary 场景**：
  - LLM 返回合法 summary 但内容不相关（幻觉摘要）——quality check 不做语义相关性校验，仅做结构性校验。
  - Compactor runner 返回 delayed/stale final answer 而 durable state 恰好在 recheck 后、write 前发生变化——极端 TOCTOU 窗口。dispatch.py:907 的 recheck 与新 write transaction 在同一 `run_write(_operation)` 闭包内，`HostTransaction` 的 SQLite 串行化隔离级别提供防御，但不承诺分布式场景下的外部并发安全。
  - Provider 5xx 持续不可用且 Engine runner retry exhausted 后，proactive compact 会在 dispatch 前收口为 `RUN_FAILED`——该 Run 不会有 Attempt，对调用方表现为 instant fail。当前行为是 fail-closed，符合设计意图。
