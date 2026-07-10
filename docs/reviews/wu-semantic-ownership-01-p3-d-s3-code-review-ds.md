# Code Review — WU-SEMANTIC-OWNERSHIP-01 / P3-D / S3

## Scope

- Mode: current changes (relative to `main`)
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-D - Engine provider protocol normalization`
- Slice: `S3 - Typed Engine error codes and propagation audit`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-code-review-ds.md`
- Included scope: P3-D S3 changes only — Engine error code typing contract (`dayu/engine/contracts/error_codes.py`), Engine contract dataclass field type changes, Agent construction site migration, OpenAI runner adapter error-code wrapping, Host ingest serialization boundary, weak-typing guard, related tests and docs.
- Excluded scope: unrelated untracked files (`docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`); non-S3 changes in the branch (P3-A, P3-B, P3-C, P3-D S1/S2, fins, cli, etc.).
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-implementation-codex.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-controller-validation.md`
- Prior commits: plan `c52519f0`, S1 `d009ad11`, S2 `43510168`

## Review Method

本 review 沿 S3 要求的完整传播链路逐条走读：

1. Engine 契约定义层（`error_codes.py`、`engine_events.py`、`runner_events.py`、`agent_run.py`）
2. Runner adapter 错误码构造点（`sse_parser.py`、`non_stream_parser.py`、`tool_call_aggregator.py`、`runner.py`）
3. Agent 消费与提升路径（`agent.py` 全部 `RunFailedData` / `ProviderProtocolErrorData` 构造点）
4. Host ingest 序列化边界（`engine_ingest.py` 全部 `serialize_engine_error_code` 调用点）
5. Host 下游消费层（`read_api.py`、`tool_trace.py`、`outbox.py`）
6. 弱类型守卫测试（`tests/engine/test_weak_typing_guard.py`）
7. 公共导出、pyright、README/design 对齐
8. LLM-facing leakage 扫描

每个关键 `if`/`elif`/`match` 分支均按顺序独立走读：入参 → 条件驱动因素 → 下游调用 → 返回值/raise → 副作用。root cause 必须与触发事实处在同一逻辑/数据路径上。

## Findings

### 逐项审查结论

#### 1. Engine-owned run failure codes 是 typed closed enum

`EngineRunErrorCode`（`StrEnum`）覆盖 S3 计划要求的全部 18 个已知 Agent/Engine 失败码（`dayu/engine/contracts/error_codes.py:18-39`）。`RunnerSpecificErrorCode` 作为 `str` 子类用 `__slots__` 承载 `source: RunnerSpecificErrorSource`（闭集 `RUNNER_PROTOCOL` / `HTTP_PROVIDER` / `ADAPTER`），构造时 trim 并拒绝空串、纯空白、超长（`error_codes.py:50-81`）。`EngineErrorCode` TypeAlias 为 `EngineRunErrorCode | RunnerSpecificErrorCode` 联合（`error_codes.py:93`）。

已验证各枚举成员值与计划一致，未发现缺失或冗余成员。

#### 2. 无兼容性 shim、旧别名、getattr/hasattr 类型逃逸、extra payload 隐藏

已对 `dayu/engine/` 全量扫描：

- `rg -n "hasattr|getattr|compat|alias|legacy|old_" dayu/engine/` — 无命中与 error_code 相关的兼容性代码。
- `rg -n "error_code: str" dayu/engine/contracts/` — 无命中（contract 层所有 error_code 字段已迁移为 typed union）。
- `rg -n "extra\|extra_payload\|_extra" dayu/engine/contracts/error_codes.py dayu/engine/contracts/engine_events.py dayu/engine/contracts/runner_events.py dayu/engine/contracts/agent_run.py` — 无命中。
- adapter 私有 `_choice_policy.py:ChoicePolicyError.error_code: str`（line 80）是 adapter 内部类型，进入 public `RunnerProtocolErrorData` 前经 `runner_protocol_error_code(...)` 包装（`sse_parser.py:487`，`non_stream_parser.py:407`）。不属于 S3 禁止范围。

#### 3. Agent 构造点全部使用 enum/wrapper

已逐点验证 `agent.py` 所有 `RunFailedData(...)` 构造（共 ~25 处）：

- 全部 `_ERROR_*` 常量均为 `EngineRunErrorCode` enum member（`agent.py:146-189`）。
- Runner protocol error pass-through：`error_code=data.error_code`（line 1435）— `data.error_code` 是 `RunnerSpecificErrorCode`，属于 `EngineErrorCode` 联合成员。
- HTTP non-context failure：`adapter_error_code(data.error_code.value)`（line 1500）— 经 wrapper 构造，非空 wrapper。
- Provider protocol error：`error_code=data.error_code`（line 1446）— 同样 typed pass-through。
- 缺失 provider detail：`_ERROR_RUNNER_ERROR_DONE_WITHOUT_DETAIL`（line 1711）— Engine-owned fallback enum。
- 未发现任何裸字符串字面量传入 `error_code=`。
- 弱类型守卫测试 `test_engine_error_code_constructors_do_not_use_literal_strings`（`tests/engine/test_weak_typing_guard.py:293-328`）通过 AST 扫描覆盖 Engine 和 tests/engine 目录，会在未来新增 literal string 构造时失败。

#### 4. Host ingest 边界序列化

已逐点验证 `engine_ingest.py` 全部 `serialize_engine_error_code` 调用：

| 位置 | 用途 | 是否正确 |
| --- | --- | --- |
| Line 1030 | `_close_terminal` RUN_FAILED 路径 | ✅ |
| Line 3280 | `_append_provider_protocol_error_event` 诊断 payload | ✅ |
| Line 3309 | 同上，reason dict | ✅ |
| Line 5015 | `_run_failed_plan` terminal fact plan | ✅ |
| Line 6935 | `_provider_protocol_failure_metadata` provider_error_code | ✅ |

所有 `engine_ingest.py` 中的 `error_code: str` / `stream_error_code: str | None` 字段均为 Host-owned durable text 或 plan-level 自用字段（如 `_HostTerminalPlan.error_code: str | None` at line 465），不是 Engine typed code object。

弱类型守卫 `test_host_typed_error_code_boundary_uses_serializer`（`test_weak_typing_guard.py:331-350`）通过行级扫描确保 `data.error_code` / `event.data.error_code` 访问点均伴随 `serialize_engine_error_code` 调用。

#### 5. Host read/tool_trace/outbox 消费 durable text

- `read_api.py:1422-1432`：从 durable payload 读 `provider_error_code` 和 `error_code` 文本，不检查 wrapper internals。
- `tool_trace.py:1734-1781`：`failure_kind` 驱动校验闭集，`provider_error_code` 通过 `_require_text_field` 读取文本。
- `outbox.py`：未引用 `error_code` 或 Engine typed code object。
- Host 不按 provider-specific runner code 分支。

#### 6. 缺失 provider detail 使用 Engine-owned fallback

`agent.py:1709-1716`：`finish_reason=ERROR` 且 `failure_candidate=None` 时使用 `EngineRunErrorCode.RUNNER_ERROR_DONE_WITHOUT_DETAIL`。

测试覆盖：`tests/engine/contracts/test_runner_events.py:293-298`（`test_missing_provider_detail_uses_engine_fallback_enum`）。

#### 7. 弱类型守卫

守卫测试 `tests/engine/test_weak_typing_guard.py` 覆盖四个维度：

1. `test_contracts_disallow_weak_typing` — 禁止 `Any`/`object`/未注解/裸容器（全 engine 包）
2. `test_engine_run_error_code_annotations_are_typed` — 四个关键 contract 类的 `error_code` 字段注解断言
3. `test_engine_error_code_constructors_do_not_use_literal_strings` — 禁止 `RunFailedData(... error_code="...")` 字面量
4. `test_host_typed_error_code_boundary_uses_serializer` — Host 边界必须走 serializer

守卫基于 AST 扫描，对新增代码引入的弱类型回归有效。四个断言均有明确的失败消息，便于定位。

#### 8. 公共导出、pyright、docs/README、测试对齐

- `dayu/engine/contracts/__init__.py` 和 `dayu/engine/__init__.py` 均正确导出所有 S3 新增符号（`EngineErrorCode`, `EngineRunErrorCode`, `RunnerSpecificErrorCode`, `RunnerSpecificErrorSource`, 三个工厂函数, `serialize_engine_error_code`）。
- `pyright` 零错误零警告。
- `dayu/engine/README.md`、`dayu/host/README.md`、`tests/README.md`、`docs/engine/design.md`、`docs/host/design.md` 均已按各 README 的 Agent 更新约束更新。
- LLM-facing leakage 窄扫描：`rg` 在 `dayu/config`、`dayu/host/memory.py`、`dayu/host/compact_material.py`、`dayu/host/compact_payload.py`、`dayu/host/compact_pipeline.py`、`dayu/host/compaction.py`、`dayu/host/llm_compaction.py`、`dayu/host/run_input.py`、`dayu/host/_terminal_answer.py`、`dayu/host/accepted_result_projection.py` 中搜索 `PROVIDER_DIAGNOSTIC|message_marker_fallback|provider_diagnostic|provider_error_code|RunnerSpecificErrorCode|EngineRunErrorCode` — 无命中。typed error-code 类型名和 provider diagnostic 标识符未进入 LLM-facing 路径。

#### 9. Branch-order / malformed code value / state/projection inconsistency / semantic ownership drift / overcoupling

已逐条走读：

- **Branch order**：`agent.py:_classify_iteration`（line 1674-1804）按 `!done_seen → ERROR → tool_calls → TOOL_CALLS signal → final content` 顺序排他判断，各分支互斥，无宽条件抢先命中问题。
- **Malformed code value gaps**：`RunnerSpecificErrorCode.__new__` 拒绝空串/纯空白/超长。所有 adapter 错误码常量均为非空字符串。provider error "error" object 路径使用常量 `_PROVIDER_ERROR_CODE`（如 `"sse_provider_error"`）而非从 provider payload 提取动态 code，避免了 provider 返回空 code 导致 ValueError 的风险。
- **State/projection inconsistency**：`RunFailedData.error_code` 在 Engine contract 层（typed union）→ Host ingest（serialized text）→ Host durable JSON（text）→ Host read projection（text）全链路一致。`failure_metadata.provider_error_code` 同为 serialized text。
- **Semantic ownership drift**：未发现。Error code 语义真源在 Engine contract；Host 不重新解释、不分叉；read/tool_trace/outbox 只消费 durable text。
- **Overcouping**：未发现。`EngineErrorCode` 联合类型使 Engine 和 Host 通过 `serialize_engine_error_code` 这一个契约 helper 解耦，Host 不依赖 wrapper source 或 enum member identity。

### 结论

**Findings: 未发现实质性问题。**

经过对 8 个 review emphasis 维度的逐链路走读，P3-D S3 的 typed error code 实现与传播审计在 Engine contract typing、Agent 构造迁移、Runner adapter wrapping、Host 边界序列化、Host 下游消费、弱类型守卫、公共导出与 LLM-facing leakage 防护各方面均符合计划要求。每一条业务事实（provider protocol code → Agent failure candidate → Engine run_failed → Host RUN_FAILED → tool trace failure metadata → public host event / read API / outbox）均可追溯至 Engine contract 层的 typed 真源，Host 不按 wrapper internals 分支，缺失 provider detail 使用 Engine-owned fallback enum，无兼容性 shim 或 hasattr/getattr 逃逸。

## Open Questions

- 无。所有 review emphasis 维度均已获得直接证据，无阻碍 confident judgment 的问题。

## Residual Risk

- S3 有意破坏旧 string-only Engine 构造兼容性，这匹配 approved non-goal/prohibition。若未来有外部调用方（非常规 Engine/Host/Test 路径）仍持有旧 string 构造，需独立迁移。
- Provider-specific code source（`RunnerSpecificErrorSource`）在 Host 边界序列化为 text 后不可恢复为 wrapper；若未来 public API 需要暴露 source discriminator，需在 Engine/Host 公共契约层单独设计序列化格式，不应从 Host 消费者 ad hoc 读取 wrapper internals。
- adapter 私有 `_choice_policy.py:ChoicePolicyError.error_code: str` 不属于 public contract，但任何对 ChoicePolicyError 处理路径的修改需确保 `runner_protocol_error_code(...)` 包装不被绕过。

S3 code review complete.
