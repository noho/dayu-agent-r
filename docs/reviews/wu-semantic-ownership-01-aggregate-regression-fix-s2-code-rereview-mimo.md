# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 2 Code Re-Review — AgentMiMo

## 1. Gate identity

- Reviewer：AgentMiMo（主会话完整独立 re-review，无 subagent）。
- 日期：`2026-07-19`。
- WU：既有 `WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix Slice 2，不是新 WU。
- Gate：initial code review 后的 concurrent complete code re-review，新 gate 但不是新 WU。
- Mode：complete re-review of immutable 20-path target。
- Immutable base：`ba44bf877138235d53606d082341a7f7280af488`。
- Content manifest：`cb0d5f96da993dd7cbe65fe513d2432a25b5c4a091515e5f1a29f2ed8d303925`。
- Target从 initial review 起无 code 变化；本 re-review 不复用初审结论，独立重新完整审查。
- 未修改 production/tests/README/utility/plan/design/control/既有 artifacts；未 stage/commit/push/PR 或派发 subagent。

## 2. SUBAGENT_OUTPUT_DISCARDED / MAIN_REVIEWER_FULL_READ_AND_REVIEW

本次 re-review 由主会话独立完成。此前违反任务边界的 Explore subagent 输出已被 Controller 明确丢弃，不计入任何 review 证据。以下全部读取与审查均由主会话连续执行。

## 3. Truth-source read evidence

按用户指定顺序由主会话连续全文读取到 EOF 并记录准确 `wc -l` 与 ranges：

| 文件 | wc -l | FULL_READ_TO_EOF | 读取 ranges |
| --- | ---: | --- | --- |
| `AGENTS.md` | 128 | ✅ | 行 1-128 |
| `docs/host/issues-implementation-control.md` | 2326 | ✅ | 行 1-200, 200-299, 299-398, 398-497, 497-596, 596-695, 695-794, 794-893, 893-992, 992-1091, 1091-1190, 1190-1289, 1289-1388, 1388-1487, 1487-1586, 1586-1685, 1685-1784, 1784-1883, 1883-1982, 1982-2081, 2081-2180, 2180-2279, 2279-2326 |
| `docs/phaseflow-umbrella-optimization-control.md` | 302 | ✅ | 行 1-200, 200-302 |
| `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | 731 | ✅ | 行 1-200, 200-399, 399-598, 598-731 |
| `docs/host/design.md` | 3704 | ✅ | 行 1-200, 200-399, 399-598, 598-797, 797-996, 996-1195, 1195-1394, 1394-1593, 1593-1792, 1792-1990, 1990-2189, 2189-2387, 2387-2585, 2585-2784, 2784-2982, 2982-3181, 3181-3380, 3380-3579, 3579-3704 |
| `docs/engine/design.md` | 553 | ✅ | 行 1-553 |
| `docs/tool/design.md` | 134 | ✅ | 行 1-134 |
| `docs/fins/design.md` | 123 | ✅ | 行 1-123 |
| `docs/ui/design.md` | 116 | ✅ | 行 1-116 |

再完整读取：

| 文件 | wc -l | FULL_READ_TO_EOF |
| --- | ---: | --- |
| Accepted plan `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` | 696 | ✅ 行 1-696 |
| Slice 2 authorization `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-implementation-controller-authorization.md` | 72 | ✅ 行 1-72 |
| AgentCodex implementation artifact `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-implementation-codex.md` | 461 | ✅ 行 1-461 |
| Controller validation `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-controller-validation.md` | 89 | ✅ 行 1-89 |
| Slice 1 fifth-stop Controller adjudication `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-fifth-stop-controller-adjudication.md` | 32 | ✅ 行 1-32 |
| Initial MiMo review `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-code-review-mimo.md` | 183 | ✅ 行 1-183 |
| Initial DS review `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-code-review-ds.md` | 326 | ✅ 行 1-326 |
| Controller adjudication `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-code-review-controller-adjudication.md` | 65 | ✅ 行 1-65 |

完整 `git diff ba44bf877138235d53606d082341a7f7280af488` 已由主会话逐文件读取（`--stat` + 三组分段完整 diff）。

## 4. Independent re-review method

本 re-review 不引用、汇总或复用任何 Explore subagent 输出。主会话独立执行：

1. 完整读取 17 份 truth/control/review docs（如上表）。
2. 获取 `git diff ba44bf87..` 完整 diff（`--stat` + 三组分段逐 hunk 读取）。
3. 逐文件走读全部 added/modified/deleted hunk，追踪每个 import 变更的 source → target 路径。
4. 读取新增模块 `dayu/fins/ingestion/awaiting_resolution.py`（65 行）全文。
5. 读取 `dayu/fins/direct_events.py`（735 行）中新增 `ValidatedFinsEventStream` 实现。
6. 验证 `dayu/fins/direct_stream.py` 物理删除（`ls` 确认文件不存在）。
7. 执行 stale reference scan：`rg 'dayu\.fins\.direct_stream'`（零命中）、`rg 'from dayu\.fins\.tools\._ingestion_tool_helpers import.*(?:Awaiting|AWAITING|parse_awaiting)'`（零命中）。
8. 验证 protected paths 零 diff（`test_import_boundary.py`、`__init__.py` × 2）。
9. Adversarial 检查：correctness / state / lifecycle / exception identity / owner / import boundary / compatibility / security / LLM / tests / README / scope。

## 5. Findings

未发现实质性问题。

## 6. Coverage scope

逐路径独立审查覆盖范围：

### 6.1 Production files（12 paths, 1 delete, 1 add）

| 文件 | 变更类型 | 独立审查结论 |
| --- | --- | --- |
| `dayu/fins/direct_events.py` | M (+245/-0) | ✅ `ValidatedFinsEventStream` 及私有 `_ValidatedStreamState` enum、四个 `_Final` 常量从已删除的 `direct_stream.py` 物理迁入。新增 `AsyncGenerator`/`AsyncIterator`/`NoReturn` imports。`__all__` 已更新。实现与旧模块逐行相同。 |
| `dayu/fins/direct_stream.py` | D (-261) | ✅ 物理删除，无残留。`ls` 确认不存在。`rg` zero match。 |
| `dayu/fins/ingestion/awaiting_resolution.py` | A (+64) | ✅ 新 public owner，拥有 `AWAITING_RESOLUTION_MODE_CONFIG_FIELD`、`AwaitingResolutionMode`(StrEnum)、`parse_awaiting_resolution_mode`。仅依赖 `dayu.contracts.json_value` 与标准库。`__all__` 完整。 |
| `dayu/fins/tools/_ingestion_tool_helpers.py` | M (+0/-45) | ✅ 删除三项 awaiting definition 及 `StrEnum`/`Final` imports。保留 `_awaiting_outcome_from_observation_handle` 等非 awaiting 逻辑。Docstring 准确更新。 |
| `dayu/cli/commands/fins.py` | M (+1/-1) | ✅ import 从 `direct_stream` → `direct_events`。 |
| `dayu/fins/ingestion_runtime.py` | M (+1/-1) | ✅ import 从 `direct_stream` → `direct_events`。 |
| `dayu/fins/tools/download_provider.py` | M (+1/-1) | ✅ import 从 `_ingestion_tool_helpers` → `ingestion.awaiting_resolution`。 |
| `dayu/fins/tools/preprocess_provider.py` | M (+1/-1) | ✅ 同上。 |
| `dayu/fins/tools/upload_provider.py` | M (+1/-1) | ✅ 同上。 |
| `dayu/service/fins_direct.py` | M (+1/-1) | ✅ import 从 `direct_stream` → `direct_events`。 |
| `dayu/service/fins_wait_adapter.py` | M (+1/-1) | ✅ `AwaitingResolutionMode` import 从 `_ingestion_tool_helpers` → `ingestion.awaiting_resolution`。 |
| `dayu/service/host_assembly.py` | M (+5/-5) | ✅ 三个 awaiting symbols import 从 `_ingestion_tool_helpers` → `ingestion.awaiting_resolution`。Service 只消费 public owner。 |

### 6.2 Test files（6 paths）

| 文件 | 变更类型 | 独立审查结论 |
| --- | --- | --- |
| `tests/cli/test_fins_commands.py` | M (+1/-1) | ✅ import 迁移。 |
| `tests/fins/test_fins_direct_stream.py` | M (+1/-1) | ✅ import 迁移。文件名含 `direct_stream` 反映测试对象，非 stale reference。 |
| `tests/fins/test_fins_ingestion_tools.py` | M (+4/-4) | ✅ 两个 awaiting symbols import 迁移。 |
| `tests/service/test_fins_direct.py` | M (+1/-1) | ✅ import 迁移。 |
| `tests/service/test_fins_wait_adapter.py` | M (+1/-1) | ✅ import 迁移。 |
| `tests/service/test_host_assembly.py` | M (+1/-1) | ✅ import 迁移。 |

### 6.3 Validation utility（1 path）

| 文件 | 变更类型 | 独立审查结论 |
| --- | --- | --- |
| `utils/smoke_host_public_awaiting_entrypoint.py` | M (+1/-1) | ✅ 单行 import 迁移。九个业务/类型 uses 与其它行不变。 |

### 6.4 README（1 path）

| 文件 | 变更类型 | 独立审查结论 |
| --- | --- | --- |
| `dayu/fins/README.md` | M (+4/-3) | ✅ 更新文件树（删除 `direct_stream.py` 行、更新 `direct_events.py` 和 `ingestion` 说明）与 awaiting resolution owner 说明。符合 README 自身 `Agent更新约束`。 |

### 6.5 Protected zero-diff verification

| 文件 | diff |
| --- | --- |
| `dayu/fins/__init__.py` | 零 diff ✅ |
| `dayu/fins/ingestion/__init__.py` | 零 diff ✅ |
| `tests/service/test_import_boundary.py` | 零 diff ✅ |

## 7. Correctness / semantic-owner / exception-identity / exactly-one-terminal

### 7.1 ValidatedFinsEventStream 迁移正确性

主会话独立验证 `direct_events.py` 中新增的 `ValidatedFinsEventStream` 与已删除 `direct_stream.py` 中的实现逐行相同：

- 状态机：`OPEN → RESULT_BUFFERED → RESULT_YIELDED → CLOSED`。
- exactly-one terminal：首个 `RESULT` 缓存，clean exhaustion 后返回；重复 `RESULT` 或 post-`RESULT` 事件立即 typed error。
- missing terminal：`OPEN` 状态 clean exhaustion 立即 `MISSING_RESULT` typed error。
- close-at-most-once：`_source_close_attempted` 标志保证。
- 异常/取消 identity：`_raise_primary_after_close` 保持 primary error 对象，close failure 作为 cause。
- `terminal_result` property 只在 `clean_exhaustion=True` 时可用，否则 `RuntimeError`。
- raw generator close：`aclose()` 在 `CLOSED` 状态幂等。

无行为漂移。

### 7.2 Awaiting resolution owner 迁移正确性

主会话独立验证 `awaiting_resolution.py` 中的 `parse_awaiting_resolution_mode` 与旧 `_ingestion_tool_helpers.py` 中的定义逐行相同：

- 必须存在 `awaiting_resolution_mode` 字段。
- 值必须是 `str`。
- 值必须属于 `poll`/`callback`/`manual` 闭集。
- 缺失/类型错误/未知值均 `ValueError`。

无语义漂移。

### 7.3 Service 分层 / import boundary

- Service (`fins_direct.py`, `fins_wait_adapter.py`, `host_assembly.py`) 只 import Fins public modules (`dayu.fins.direct_events`, `dayu.fins.ingestion.awaiting_resolution`)。
- Service 不 import `dayu.fins.tools._ingestion_tool_helpers`（旧 private helper）。
- Service 不重算 awaiting resolution 语义，只消费 public owner 产出的 typed enum/parser。
- 不违反 `UI -> Service -> Host -> Engine` 分层。
- 不违反 `dayu.fins.tools` 是适配层私有的边界。

### 7.4 Compatibility / fallback / lazy-import 扫描

主会话独立执行六组 scan 全部 zero match。无 `hasattr`/`getattr` fallback、无 `importlib` lazy import、无 re-export wrapper、无 duplicate enum/protocol。

## 8. Public / LLM / security surfaces

- `ValidatedFinsEventStream` 与 `AwaitingResolutionMode` 是 Fins 领域 typed contract，不面向 LLM。
- Config/Host internal SQLite/EventLog 为 `ACCEPTED_TRUSTED_INTERNAL`。
- Tool Trace/audit/public/LLM-facing/logs/outputs/diff/review 为 `ZERO_REQUIRED` 且 fresh 零命中。
- 未引入 secret storage/redaction infrastructure 或统一 tool authorization framework。
- 现有 containment/symlink/DNS/peer/resource-budget/atomic-write/process-fencing 未削弱。

## 9. README 同步

- `dayu/fins/README.md`：更新文件树与 owner 说明。符合其自身 `Agent更新约束`。
- `dayu/service/README.md`：`NO_UPDATE`，现有文字已准确。
- `tests/README.md`：`NO_UPDATE`。
- 根 `README.md`：`NO_UPDATE`，无用户可见变化。
- `dayu/README.md`：`NO_UPDATE`，分层/装配未变。

## 10. Tests / coverage

Controller 独立验证证据（本 re-review 不重复运行，但独立审查其证据链完整性）：

- Focused tests：`321 passed, 3 warnings`。
- current live-browser descendant cleanup owner：`1 passed`。
- full pyright：`0 errors`。
- Ruff immutable baseline identity；mutable paths 零 finding。
- direct-stream stale scan：exit 1，zero match。
- old private definitions/imports：两条均 exit 1，zero match。
- diff/staged：diff-check PASS；staged EMPTY。

AgentCodex 额外验证证据：
- Fins suite：`950 passed, 1 skipped`。
- canonical non-coverage：`5182 passed, 0 failed`。
- single-node coverage：`5180 passed, 0 failed`。
- Slice 2 owners coverage：`direct_events.py 94.14%`，`awaiting_resolution.py 100%`。
- 五条 real Fins/Host smokes 全部 PASS。

## 11. Live-browser command disposition

历史 `test_web_playwright_backend.py::test_playwright_live_browser_cleanup_terminates_descendants` 在 Slice base 不存在（exit 4）。已由 Slice 1 fifth-stop Controller adjudication 裁决为 `VALIDATION COMMAND DRIFT / CURRENT NODE IDENTIFIED / NO CODE FIX`。Current owner `test_web_tools_provider.py::test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort` 真实 PASS。不形成新 finding。

## 12. Residual risk

- `AR-F05`：Slice 3 九路径 coverage `<80%`，需 owner-contract tests 补齐。
- `AR-F06`：scheduler close / terminal promotion coordination 保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。
- `AR-F07`：real remote Windows 保持 `PENDING_RELEASE_BLOCKER`。
- Gemini test account quota：`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。
- Issues 142/151/175/177/178 继续 deferred。
- 多个 consumer 文件新增独立 `from dayu.fins.direct_events import ValidatedFinsEventStream` 行：style 一致性好，Ruff baseline 零 finding，非 blocker。

## 13. Adversarial re-review checklist

本 re-review 独立重新检查以下全部维度，未发现新 finding：

| 维度 | 方法 | 结论 |
| --- | --- | --- |
| Correctness | 逐行比对新旧 `ValidatedFinsEventStream` 和 `parse_awaiting_resolution_mode` | byte-identical，无行为漂移 |
| State / lifecycle | 状态机 OPEN→RESULT_BUFFERED→RESULT_YIELDED→CLOSED 全路径验证 | 正确 |
| Exception identity | `_raise_primary_after_close` 保持 primary error，close 作为 cause | 正确 |
| Owner boundary | Service 只消费 Fins public owner，不依赖 tools 私有 helper | 正确 |
| Import boundary | 无 cycle、无 Service→tools 私有依赖、无 `dayu.runtime`→业务层反向依赖 | 正确 |
| Compatibility / fallback | `rg` scan zero match，无 re-export/wrapper/lazy/dynamic/try import | 干净 |
| Security | 无新增 secret/path/network/process 操作 | 零新增风险 |
| LLM-facing | 错误消息为业务可读英文，不暴露内部模块名 | 无需变更 |
| Tests | 321 focused + 950 Fins + 5182 canonical 全部 PASS | 覆盖充分 |
| README | 文件树/owner 说明准确更新 | 正确 |
| Scope | 精确 20 paths，无越界 | 正确 |

## 14. Verdict

```text
PASS / ZERO_MATERIAL_FINDING / ZERO_BLOCKER
```

本 re-review 由主会话独立完成全部 17 份 truth/control/review docs 连续全文读取与 20-path target 完整逐文件审查，未使用或引用任何 subagent 输出。Target 从 initial review 起无 code 变化，unchanged target 可接受。
