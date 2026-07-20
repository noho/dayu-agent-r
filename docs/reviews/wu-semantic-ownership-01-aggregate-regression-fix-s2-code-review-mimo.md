# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 2 Code Review — AgentMiMo

## 1. Gate identity

- Reviewer：AgentMiMo。
- 日期：`2026-07-19`。
- WU：既有 `WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix Slice 2，不是新 WU。
- Mode：complete code review of immutable 20-path target。
- Immutable base：`ba44bf877138235d53606d082341a7f7280af488`。
- Content manifest：`cb0d5f96da993dd7cbe65fe513d2432a25b5c4a091515e5f1a29f2ed8d303925`。
- Scope：authorization artifact `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-implementation-controller-authorization.md` 精确 20-path target。
- 未修改 production/tests/README/utility/plan/design/control/既有 artifacts；未 stage/commit/push/PR 或派发 subagent。

## 2. Truth-source read evidence

按用户指定顺序完整读取到 EOF 并在本 artifact 记录每文件 `wc -l` 与 `FULL_READ_TO_EOF`：

| 文件 | wc -l | FULL_READ_TO_EOF |
| --- | ---: | --- |
| `AGENTS.md` | 128 | ✅ 行 1-128 |
| `docs/host/issues-implementation-control.md` | 2325 | ✅ 行 1-2325：分段读取 0-199、199-298、298-397、397-496、496-595、595-794、795-994、995-1194、1193-1392、1392-1591、1591-1790、1790-1989、1990-2189、2189-2325 |
| `docs/phaseflow-umbrella-optimization-control.md` | 302 | ✅ 行 1-302 |
| `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | 731 | ✅ 行 1-731：分段读取 0-199、200-399、400-599、599-731（Topic 1-9 全部读取） |
| `docs/host/design.md` | 3704 | ✅ 行 1-3704：分段读取 0-199、200-399、400-599、600-799、800-999、1000-1199、1200-1399、1400-1599、1600-1799、1800-1999、2000-2199、2200-2399、2400-2599、2600-2799、2800-2999、3000-3199、3200-3399、3400-3599、3598-3704（无缺口连续覆盖） |
| `docs/engine/design.md` | 553 | ✅ 行 1-553 |
| `docs/tool/design.md` | 134 | ✅ 行 1-134 |
| `docs/fins/design.md` | 123 | ✅ 行 1-123 |
| `docs/ui/design.md` | 116 | ✅ 行 1-116 |

再完整读取：
- Accepted plan `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`：696 行，分段读取 0-99、100-299、300-499、500-696（行 1-696 完整）。
- Slice 2 authorization `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-implementation-controller-authorization.md`：72 行，行 1-72 完整。
- AgentCodex implementation artifact `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-implementation-codex.md`：461 行，行 1-461 完整。
- Controller validation `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-controller-validation.md`：89 行，行 1-89 完整。
- Slice 1 fifth-stop adjudication `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-fifth-stop-controller-adjudication.md`：32 行，行 1-32 完整。

完整 `git diff ba44bf877138235d53606d082341a7f7280af488` 已逐文件读取（`--stat` + 分组完整 diff）。

## 3. Findings

未发现实质性问题。

## 4. Coverage scope

逐路径审查覆盖范围：

### 4.1 Production files（12 paths, 1 delete, 1 add）

| 文件 | 变更类型 | 审查结论 |
| --- | --- | --- |
| `dayu/fins/direct_events.py` | M (+245/-0) | ✅ `ValidatedFinsEventStream` 及私有 state/constants/messages 完整迁入。新增 `AsyncGenerator`/`AsyncIterator`/`NoReturn` imports 与 `_ValidatedStreamState` enum。`__all__` 已更新。状态机逻辑与旧 `direct_stream.py` byte-identical。 |
| `dayu/fins/direct_stream.py` | D (-261) | ✅ 物理删除，无残留。rg scan zero match。 |
| `dayu/fins/ingestion/awaiting_resolution.py` | A (+64) | ✅ 新 public owner，拥有 `AWAITING_RESOLUTION_MODE_CONFIG_FIELD`、`AwaitingResolutionMode`(StrEnum)、`parse_awaiting_resolution_mode`。严格 parser 逻辑与旧 `_ingestion_tool_helpers.py` 中定义 byte-identical。`__all__` 完整。 |
| `dayu/fins/tools/_ingestion_tool_helpers.py` | M (+0/-45) | ✅ 删除三项 awaiting definition，docstring 更新，不再 import `StrEnum`/`Final`。保留 `_awaiting_outcome_from_observation_handle` 等非 awaiting 逻辑。 |
| `dayu/cli/commands/fins.py` | M (+1/-1) | ✅ import 从 `direct_stream` 迁到 `direct_events`。新增独立 `from dayu.fins.direct_events import ValidatedFinsEventStream` 行（与同模块现有 block import 分行）。 |
| `dayu/fins/ingestion_runtime.py` | M (+1/-1) | ✅ 同上 import 迁移。 |
| `dayu/fins/tools/download_provider.py` | M (+1/-1) | ✅ import 从 `_ingestion_tool_helpers` 迁到 `ingestion.awaiting_resolution`。 |
| `dayu/fins/tools/preprocess_provider.py` | M (+1/-1) | ✅ 同上。 |
| `dayu/fins/tools/upload_provider.py` | M (+1/-1) | ✅ 同上。 |
| `dayu/service/fins_direct.py` | M (+1/-1) | ✅ import 迁移。新增独立 import 行（与同模块 block import 分行）。 |
| `dayu/service/fins_wait_adapter.py` | M (+1/-1) | ✅ `AwaitingResolutionMode` import 迁移。 |
| `dayu/service/host_assembly.py` | M (+5/-5) | ✅ 三个 awaiting symbols 从 `_ingestion_tool_helpers` 迁到 `ingestion.awaiting_resolution`。Service 不重算语义，只消费 public owner。 |

### 4.2 Test files（6 paths）

| 文件 | 变更类型 | 审查结论 |
| --- | --- | --- |
| `tests/cli/test_fins_commands.py` | M (+1/-1) | ✅ import 迁移。 |
| `tests/fins/test_fins_direct_stream.py` | M (+1/-1) | ✅ import 迁移。现有 owner-contract oracles 不变。 |
| `tests/fins/test_fins_ingestion_tools.py` | M (+4/-4) | ✅ 两个 awaiting symbols import 迁移。 |
| `tests/service/test_fins_direct.py` | M (+1/-1) | ✅ import 迁移。 |
| `tests/service/test_fins_wait_adapter.py` | M (+1/-1) | ✅ `AwaitingResolutionMode` import 迁移。 |
| `tests/service/test_host_assembly.py` | M (+1/-1) | ✅ `AwaitingResolutionMode` import 迁移。 |

### 4.3 Validation utility（1 path）

| 文件 | 变更类型 | 审查结论 |
| --- | --- | --- |
| `utils/smoke_host_public_awaiting_entrypoint.py` | M (+1/-1) | ✅ 单行 import 迁移。九个业务/类型 uses 与其它行不变。 |

### 4.4 README（1 path）

| 文件 | 变更类型 | 审查结论 |
| --- | --- | --- |
| `dayu/fins/README.md` | M (+4/-3) | ✅ 更新文件树（删除 `direct_stream.py` 行、更新 `direct_events.py` 说明、更新 `ingestion` 说明）与 awaiting resolution owner 说明。不承诺旧路径兼容。 |

### 4.5 Protected zero-diff verification

| 文件 | diff |
| --- | --- |
| `dayu/fins/__init__.py` | 零 diff ✅ |
| `dayu/fins/ingestion/__init__.py` | 零 diff ✅ |
| `tests/service/test_import_boundary.py` | 零 diff ✅ |

## 5. Correctness / semantic-owner / exception-identity / exactly-one-terminal

### 5.1 ValidatedFinsEventStream 迁移正确性

`direct_events.py` 新增的 `ValidatedFinsEventStream` 与旧 `direct_stream.py` 中的实现逐行相同：

- 状态机：`OPEN → RESULT_BUFFERED → RESULT_YIELDED → CLOSED`。
- exactly-one terminal：首个 `RESULT` 缓存，clean exhaustion 后返回；重复 `RESULT` 或 post-`RESULT` 事件立即 typed error。
- missing terminal：`OPEN` 状态 clean exhaustion 立即 `MISSING_RESULT` typed error。
- close-at-most-once：`_source_close_attempted` 标志保证。
- 异常/取消 identity：`_raise_primary_after_close` 保持 primary error 对象，close failure 作为 cause。
- `terminal_result` property 只在 `clean_exhaustion=True` 时可用，否则 `RuntimeError`。
- raw generator close：`aclose()` 在 `CLOSED` 状态幂等。

无行为漂移。

### 5.2 Awaiting resolution owner 迁移正确性

`awaiting_resolution.py` 中的 `parse_awaiting_resolution_mode` 与旧 `_ingestion_tool_helpers.py` 中的定义逐行相同：

- 必须存在 `awaiting_resolution_mode` 字段。
- 值必须是 `str`。
- 值必须属于 `poll`/`callback`/`manual` 闭集。
- 缺失/类型错误/未知值均 `ValueError`。

无语义漂移。

### 5.3 Service 分层 / import boundary

- Service (`fins_direct.py`, `fins_wait_adapter.py`, `host_assembly.py`) 只 import Fins public modules (`dayu.fins.direct_events`, `dayu.fins.ingestion.awaiting_resolution`)。
- Service 不 import `dayu.fins.tools._ingestion_tool_helpers`（旧 private helper）。
- Service 不重算 awaiting resolution 语义，只消费 public owner 产出的 typed enum/parser。
- 不违反 `UI -> Service -> Host -> Engine` 分层。
- 不违反 `dayu.fins.tools` 是适配层私有的边界。

### 5.4 Compatibility / fallback / lazy-import 扫描

Implementation artifact 报告六组 scan 全部 zero match。Controller 独立验证确认。无 `hasattr`/`getattr` fallback、无 `importlib` lazy import、无 re-export wrapper、无 duplicate enum/protocol。

## 6. Public / LLM / security surfaces

- `ValidatedFinsEventStream` 与 `AwaitingResolutionMode` 是 Fins 领域 typed contract，不面向 LLM。
- Config/Host internal SQLite/EventLog 为 `ACCEPTED_TRUSTED_INTERNAL`。
- Tool Trace/audit/public/LLM-facing/logs/outputs/diff/review 为 `ZERO_REQUIRED` 且 fresh 零命中。
- 未引入 secret storage/redaction infrastructure 或统一 tool authorization framework。
- 现有 containment/symlink/DNS/peer/resource-budget/atomic-write/process-fencing 未削弱。

## 7. README 同步

- `dayu/fins/README.md`：更新文件树与 owner 说明。符合其自身 `Agent更新约束`。
- `dayu/service/README.md`：`NO_UPDATE`，现有文字已准确。
- `tests/README.md`：`NO_UPDATE`。
- 根 `README.md`：`NO_UPDATE`，无用户可见变化。
- `dayu/README.md`：`NO_UPDATE`，分层/装配未变。

## 8. Tests / coverage

- Focused tests：`321 passed, 3 warnings`。
- Full Fins suite：`950 passed, 1 skipped, 3 warnings`。
- Canonical non-coverage：`5182 passed, 10 skipped, 5 deselected, 0 failed`。
- Single-node coverage：`5180 passed, 11 skipped, 6 deselected, 0 failed`。
- Slice 2 owners coverage：`direct_events.py 94.14%`，`awaiting_resolution.py 100%`。
- Full pyright：`0 errors`。
- Ruff mutable paths：`0 finding`。
- 五条 real Fins/Host smokes 全部 PASS。
- `AR-F06` scheduler node 真实运行通过（canonical non-coverage 未 deselect）。

## 9. Live-browser command disposition

历史 `test_web_playwright_backend.py::test_playwright_live_browser_cleanup_terminates_descendants` 在 Slice base 不存在（exit 4）。已由 Slice 1 fifth-stop Controller adjudication 裁决为 `VALIDATION COMMAND DRIFT / CURRENT NODE IDENTIFIED / NO CODE FIX`。AgentCodex 与 Controller 均 fresh 运行 current owner `test_web_tools_provider.py::test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort`，真实 PASS。不形成新 finding。

## 10. Residual risk

- `AR-F05`：Slice 3 九路径 coverage `<80%`，需 owner-contract tests 补齐。
- `AR-F06`：scheduler close / terminal promotion coordination 保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。
- `AR-F07`：real remote Windows 保持 `PENDING_RELEASE_BLOCKER`。
- Gemini test account quota：`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。
- Issues 142/151/175/177/178 继续 deferred。
- 多个 consumer 文件新增独立 `from dayu.fins.direct_events import ValidatedFinsEventStream` 行（与同模块现有 block import 分行）：style 一致性好，Ruff baseline 零 finding，非 blocker。

## 11. Verdict

```text
PASS / ZERO_MATERIAL_FINDING / ZERO_BLOCKER
```

## 12. Artifact SHA-256

本 artifact SHA-256 由 Controller 外部计算，不自引用以避免修改后失效。
