# Code Review

## Scope

- Mode: current workspace changes (S2 only)
- Branch: `phaseflow/host-issues-control`
- Base: P3-D S1 implementation commit `d009ad11`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-code-review-ds.md`
- Included scope: P3-D S2 tracked modifications and S2 artifacts (31 files, 1226 insertions, 129 deletions)
- Excluded scope:
  - Untracked `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`
  - Untracked prior review artifacts `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`
  - S1 artifacts (accepted at `d009ad11`) and unrelated P3-D slices
- Parallel review coverage: 无（主 reviewer 单人走读全部 S2 变更文件）

## Findings

### 1-未修复-低-Read API `PROVIDER_PROTOCOL_ERROR` 与 `PROVIDER_DIAGNOSTIC` 共用同一 `HostActivityKind.PROVIDER_DIAGNOSTIC`

- **入口/函数**: `_activity_from_row` → `_provider_protocol_error_activity` / `_provider_diagnostic_activity`
- **文件(行号)**: `dayu/host/read_api.py:1412-1470`
- **输入场景**: Read API 投影 `PROVIDER_PROTOCOL_ERROR` (fatal) 或 `PROVIDER_DIAGNOSTIC` (non-fatal) EventLog row
- **实际分支**: `_provider_protocol_error_activity` (line 1434) 返回 `kind=HostActivityKind.PROVIDER_DIAGNOSTIC` 搭配 `status=FAILED`；`_provider_diagnostic_activity` (line 1462) 返回同一 `kind` 搭配 `status=COMPLETED`
- **预期行为**: Fatal protocol error 与 non-fatal diagnostic 应在 activity kind 层面有明确区分，使 UI/调用方不必依赖 `status` 字段的隐式约定来区分两类语义
- **实际行为**: 两个不同语义的 activity 共用 `HostActivityKind.PROVIDER_DIAGNOSTIC`，仅以 `status` 字段（`FAILED` vs `COMPLETED`）区分
- **直接证据**: `read_api.py:1434` 的 `kind=HostActivityKind.PROVIDER_DIAGNOSTIC` 与 `read_api.py:1462` 的 `kind=HostActivityKind.PROVIDER_DIAGNOSTIC` 完全相同
- **影响**: UI 层仅凭 `kind` 字段无法区分 fatal protocol error 与 non-fatal diagnostic；需要额外读取 `status` 或 `event_type` 才能正确展示。当前不造成数据损坏或状态错误，但增加了消费侧的认知负担和误判风险
- **建议改法和验证点**: 考虑为 `PROVIDER_PROTOCOL_ERROR` 新增独立的 `HostActivityKind`（如 `HostActivityKind.PROVIDER_ERROR`），或将 `HostActivityKind.PROVIDER_DIAGNOSTIC` 重命名为更准确涵盖两者的名称。验证点：Read API 投影测试覆盖两类 event 的 kind 区分
- **修复风险（低）**: 仅影响 HostActivityKind 枚举命名/新增，UI 消费侧可能需要同步调整
- **严重程度（低）**: 不造成数据错误或状态异常；属于 API 语义清晰度问题，可在后续迭代中处理

### 2-未修复-低-`_extract_diagnostic_trace` 在 `PROVIDER_DIAGNOSTIC` 分支将 `provider_error_ref` 设为 `None`

- **入口/函数**: `_extract_diagnostic_trace`
- **文件(行号)**: `dayu/host/tool_trace.py:984-987`
- **输入场景**: Tool Trace 投影 `PROVIDER_DIAGNOSTIC` (non-fatal) EventLog row
- **实际分支**: `event.event_type == _EVENT_TYPE_PROVIDER_DIAGNOSTIC` 时，`provider_error_ref` 被显式设为 `None`（line 985-987）：
  ```python
  provider_error_ref=(
      None
      if event.event_type == _EVENT_TYPE_PROVIDER_DIAGNOSTIC
      else raw_payload_ref
  ),
  ```
- **预期行为**: 非致命 diagnostic 不应携带 `provider_error_ref`，这一行为与设计一致
- **实际行为**: 行为正确——`PROVIDER_DIAGNOSTIC` 不设置 `provider_error_ref`。但条件判断依赖事件类型字符串比较 `== _EVENT_TYPE_PROVIDER_DIAGNOSTIC`，而非依赖更稳定的 `EventClass.DIAGNOSTIC` 分类。当 `_EVENT_TYPE_PROVIDER_PROTOCOL_ERROR` 进入同一分支时，`provider_error_ref` 被设为 `raw_payload_ref`
- **直接证据**: `tool_trace.py:934-996`，`_extract_diagnostic_trace` 对 `PROVIDER_DIAGNOSTIC` 和 `PROVIDER_PROTOCOL_ERROR` 的分支仅依赖 `event.event_type` 字符串比较（line 985-987）
- **影响**: 当前工具 trace 中 `PROVIDER_DIAGNOSTIC` 行正确不含 `provider_error_ref`。但如果未来新增同属 `EventClass.DIAGNOSTIC` 的新 event type，该条件可能漏判，导致新的 diagnostic type 误带 `provider_error_ref`。风险低，因为当前只有两个 diagnostic event type
- **建议改法和验证点**: 考虑将条件从 `event.event_type == _EVENT_TYPE_PROVIDER_DIAGNOSTIC` 改为按语义分类判断（如基于 `EventClass.DIAGNOSTIC` 加事件 type allowlist），减少未来新增 event type 时的遗漏风险。验证点：新增 diagnostic event type 时 Tool Trace 投影测试
- **修复风险（低）**: 仅重构条件判断逻辑，不改变运行时行为
- **严重程度（低）**: 当前行为正确；仅存在未来新增 diagnostic event type 时被误判的远期风险

## Open Questions

1. **S3 typed Engine error-code contract 是否需要调整 `HostActivityKind` 分类？** 当前 `PROVIDER_PROTOCOL_ERROR` 使用 `HostActivityKind.PROVIDER_DIAGNOSTIC`，S3 引入 typed Engine error-code 后可能需要重新审视 activity kind 的语义边界。此问题不影响 S2，但建议 S3 plan 中纳入考虑。
2. **`_append_projection_signal` 与 `_append_provider_diagnostic` 是否应统一为 diagnostic 追加模式？** 当前 `USAGE_REPORTED` 使用 `EventClass.PROJECTION_SIGNAL`，`PROVIDER_DIAGNOSTIC` 使用 `EventClass.DIAGNOSTIC`，两者在 Host ingest 中走不同附加路径。这是有意设计（usage 是 projection signal 而非纯 diagnostic），但值得在 S3 复查时确认分类一致性。

## Residual Risk

1. **S3 typed Engine error-code contract 缺失**：S2 仅在 `RunnerHTTPErrorCode` 和 `RunnerDiagnosticSeverity`/`RunnerDiagnosticSource` 层面做了类型化，Engine 层错误码（`RunFailedData.error_code`）仍为自由字符串。S3 实现时若改变错误码语义，可能影响 Host ingest 中 `recoverable` 字段的判断逻辑（`engine_ingest.py:1029`）。
2. **`dayu/engine/runners/openai/runner.py` 覆盖率 82%**：略高于 80% 阈值。runner 中 `_call_impl` 的重试分支（retriable after event、retry exhausted）和 stream idle timeout 路径的覆盖依赖集成级测试触发，单元测试难以构造。建议 S3 或后续 phase 中针对这些路径补充集成测试。
3. **`dayu/host/read_api.py` 覆盖率 82%**：`_provider_diagnostic_activity` 和 `_provider_protocol_error_activity` 的新增路径已被测试覆盖（`test_host_activity_event_projection.py`），但 Read API 中 `_activity_from_row` 的 `CONTEXT_COMPACTION_*` 等已有分支的覆盖率可能拉低了整体数字，与 S2 无关。
4. **Tool Trace 中 `PROVIDER_DIAGNOSTIC` 的 cold JSONL 行包含 `provider_error_ref=None`**：冷存储中该字段为 `null`，有利于区分；但若未来 cold JSONL 消费者不理解 `null` 语义而做 loose parsing，可能误读。风险很低。

---

S2 code review complete.
