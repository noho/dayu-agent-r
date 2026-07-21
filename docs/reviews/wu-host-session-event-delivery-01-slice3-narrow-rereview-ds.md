# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Narrow Code Re-Review（AgentDS）

## Verdict

**S3-RR-F01 CLOSED. 0 new material finding.**

## 审查范围

- **Mode**: narrow code re-review（deepreview --base b33bb80b，仅复核 accepted S3-RR-F01 修复 + final diff new material scan）
- **Accepted base**: `b33bb80b`
- **审查 Diff**: 28 files（production 9 + test 19，含 1 new `terminal_post_commit.py` + 1 new `test_terminal_post_commit.py`）
- **已读前置文档**: AGENTS.md、Controller adjudication（`wu-host-session-event-delivery-01-slice3-code-rereview-controller-adjudication.md`）、AgentCodex fix artifact（`wu-host-session-event-delivery-01-slice3-rereview-fix-codex.md`）、AgentDS 上一轮 re-review（`wu-host-session-event-delivery-01-slice3-code-rereview-ds.md`）
- **未读**: 另一 reviewer（AgentMiMo）本轮新产物
- **排除**: `docs/host/issues-implementation-control.md`（Controller-owned dirty change）、所有 review artifacts（排除 product finding）

---

## S3-RR-F01 逐项确认

### 1. Durable owner 唯一性

**约束**: 唯一 owner 为 `project_terminal_notice_from_exact_run_event`，签名 `run: RunRow | None, exact_run_event: EventLogRow | None, *, wake_queue_promotion: bool`；无为此新增 Protocol。

**直接证据**:

- **唯一定义**: `dayu/host/durable/run_transition.py:926` — 仅此一处 `def project_terminal_notice_from_exact_run_event`。
  ```bash
  grep -rn "def project_terminal_notice_from_exact_run_event" dayu/host/
  # dayu/host/durable/run_transition.py:926
  ```
- **签名验证**（AST static test `test_terminal_notice_projection_has_single_durable_owner`）:
  - 位置参数 `("run", "exact_run_event")` 类型 `("RunRow | None", "EventLogRow | None")`
  - keyword-only 参数 `("wake_queue_promotion",)` 类型 `("bool",)`
- **无新增 Protocol**: `grep -rn "Protocol.*[Tt]erminal\|[Tt]erminal.*Protocol" dayu/host/` 仅命中 `terminal_post_commit.py:52`（`TerminalPostCommitPort` — 这是 delivery port Protocol，与 projection 输入无关）和 `dispatch.py:532`（`_TerminalPostCommitPortFactory` — dispatch 内部 factory Protocol）。两项均 pre-existing，非为 S3-RR-F01 新增。
- **`TerminalPostCommitNotice(...)` 生产构造仅 owner 一处**: `run_transition.py:955`，确认：
  ```bash
  grep -rn "TerminalPostCommitNotice(" dayu/host/
  # dayu/host/durable/run_transition.py:955:    return TerminalPostCommitNotice(
  ```
- **旧函数名零命中**: `terminal_notice_from_transition` 与 `_terminal_notice_from_wait_transition` 在 `dayu/host/` 全量源码中零命中。

✅ **通过**。

### 2. 五 consumer direct import/call，无 alias/wrapper/re-export

**约束**: admission / engine_ingest / recovery / dispatch / waiting 五个 consumer 直接 import/call，无 alias、wrapper、re-export、本地 `TerminalPostCommitNotice(...)` 构造。

**直接证据**:

| Module | Import 行 | 调用次数 | 本地定义 | alias | 本地构造 |
|--------|----------|---------|---------|-------|---------|
| `admission.py` | 97 | 11 | 无 | 无 | 无 |
| `engine_ingest.py` | 181 | 9 | 无 | 无 | 无 |
| `recovery.py` | 31 | 2 | 无 | 无 | 无 |
| `dispatch.py` | 74 | 3 | 无 | 无 | 无 |
| `waiting.py` | 75 | 4 | 无 | 无 | 无 |

全部 import 语句均为 `from dayu.host.durable.run_transition import (... project_terminal_notice_from_exact_run_event, ...)`，无 `as` 别名。

AST static test (`test_terminal_notice_projection_has_single_durable_owner` lines 372–419) 对每个 consumer 逐一断言:
- `local_definitions == ()` — 零本地函数定义
- `len(direct_imports) == 1` 且 `asname is None` — 恰好一次直接 import 且无别名
- `helper_name in called_names` — 调用存在
- `local_notice_constructions == ()` — 零本地 `TerminalPostCommitNotice(...)` 构造
- `local_helper_aliases == ()` — 零赋值别名

✅ **通过**。

### 3. waiting 旧 pure projection 删除；terminal snapshot helper 只做 confirmation

**约束**: `_terminal_notice_from_wait_transition` 已删除；`_terminal_notice_from_terminal_wait_snapshot` 保留 terminal confirmation + replay 职责但只把确认结果交给 shared owner helper。

**直接证据**:

- `_terminal_notice_from_wait_transition` — `dayu/host/waiting.py` 全量源码零命中 ✅
- `_terminal_notice_from_terminal_wait_snapshot`（`waiting.py:2142-2172`）:
  - 先确认 `wait_record.status in (FAILED, LOST)` — 只处理 terminal wait
  - 再校验 `is_terminal_run_status(run.status)` — 确保 Run 状态一致
  - 调用 `confirm_terminal_run_in_transaction(...)` 获取 confirmation
  - **仅**把 `confirmation.run`、`confirmation.run_event` 传给 `project_terminal_notice_from_exact_run_event(..., wake_queue_promotion=False)`
  - 不再复制校验逻辑，不再构造临时 transition ✅

✅ **通过**。

### 4. failed/lost/expiry/replay flags 与时点不漂移

**约束**: waiting 首次 failed/lost/expiry 为 `True`，terminal confirmation/replay 为 `False`；其它调用点 bool 值未改变。

**直接证据**（`waiting.py`）:

| 路径 | 行号 | flag 值 | 语义 |
|------|------|--------|------|
| `_resolve_failed` | 1264 | `True` | 首次 FAILED，释放 active slot |
| `_resolve_lost` | 1337 | `True` | 首次 LOST，释放 active slot |
| `_expire_wait_in_transaction` | 1538 | `True` | 首次 expiry，释放 active slot |
| `_terminal_notice_from_terminal_wait_snapshot` | 2168 | `False` | confirmation/replay，不重复释放 |
| → 调用自 expiry replay | 1390 | `False` | 同上 |
| → 调用自 idempotent replay | 1443 | `False` | 同上 |
| → 调用自 resolve wait replay | 2133 | `False` | 同上 |

其它 consumer（admission、engine_ingest、recovery、dispatch）的 `wake_queue_promotion` 值均与 pre-fix 保持一致（Codex fix artifact 已确认）。dispatch.py `_closeout_worker_startup_timeout._operation`（line 3964-3967）的 flag 表达式为 pre-existing 行为，非 S3-RR-F01 引入。

✅ **通过**。

### 5. Owner 行为/static tests 真实覆盖

**约束**: 覆盖 missing（Run row 或 exact event row 缺失）与四类 identity mismatch（terminal event id、sequence、Session id、Run id），以及五 consumer 闭集。

**直接证据**:

`test_run_attempt_transitions.py::test_terminal_closeout_appends_concrete_terminal_events`（line 360）:
- **真实 terminal transaction** → 同事务 exact event → `project_terminal_notice_from_exact_run_event(transition.run, transition.run_event, wake_queue_promotion=True)` → 断言 notice.session_id / terminal_event_sequence / flag 与 source rows 一致 ✅
- **Run row 缺失**: `project_terminal_notice_from_exact_run_event(None, transition.run_event, ...)` → `HostDurableError("exact Run/Event projection is missing a row")` ✅
- **exact event 缺失**: `project_terminal_notice_from_exact_run_event(transition.run, None, ...)` → `HostDurableError(...)` ✅
- **四类 identity mismatch**（lines 437-467）:
  1. `terminal_event_id` 不一致 → `HostDurableError("...rows are inconsistent")` ✅
  2. `terminal_event_sequence` 不一致 → `HostDurableError(...)` ✅
  3. `session_id` 不一致 → `HostDurableError(...)` ✅
  4. `run_id` 不一致 → `HostDurableError(...)` ✅

`test_terminal_post_commit.py::test_terminal_notice_projection_has_single_durable_owner`（line 337）:
- 五 consumer 闭集 = `("dayu/host/admission.py", "dayu/host/engine_ingest.py", "dayu/host/recovery.py", "dayu/host/dispatch.py", "dayu/host/waiting.py")` ✅
- 对每个 consumer 断言: 零本地定义、直接 import 无 alias、helper 在 called names、零本地构造、零赋值别名 ✅

✅ **通过**。

### 6. Producer manifest / direct promotion / local-only / Engine boundary / pyright / coverage

**约束**: 以上全部保持。

**直接证据**:

- `test_static_terminal_producer_manifest_is_exact`: 21 个 producer 闭集精确通过（含 `_fail_recovering_run`） ✅
- `test_direct_queue_promotion_allowlist_is_exact`: 5 处 ordinary direct promotion 精确通过 ✅
- `test_terminal_contract_module_has_no_upper_layer_dependency`: `terminal_post_commit.py` AST import roots = `{"__future__", "dataclasses", "typing"}` ✅
- `test_source_has_no_run_ref_notice_or_optional_production_port`: 禁止不安全的 fallback 模式 ✅
- Engine boundary: `dayu/engine/` 对 `TerminalPostCommit` / `terminal_post_commit` / `session_event_delivery` 零命中 ✅
- `dayu.runtime/` reverse dependency: 零命中 ✅
- **Pyright**: `dayu/host/` — **0 errors, 0 warnings, 0 informations** ✅
- **Coverage**: 全部 modified production 文件 ≥ 80%（Codex fix artifact 已逐文件报告）

✅ **通过**。

---

## New Material Finding Scan

对 b33bb80b 至今的完整 workspace diff 逐项扫描：

1. **旧函数名残留** — `terminal_notice_from_transition` / `_terminal_notice_from_wait_transition` 在 diff 与全量源码中均零命中。
2. **TerminalPostCommitNotice 构造扩散** — diff 中仅 owner `run_transition.py:955` 一处 `return TerminalPostCommitNotice(...)`。
3. **Protocol 新增** — 无；仅有的两处 Terminal 相关 Protocol（`terminal_post_commit.py:52`、`dispatch.py:532`）均为 pre-existing delivery/factory protocol，非为 projection 输入新增。
4. **alias / re-export / wrapper** — AST static test 断言零命中；`grep "project_terminal_notice_from_exact_run_event as "` 零命中；`grep "= project_terminal_notice_from_exact_run_event"` 零命中。
5. **consumer 闭集漂移** — `_TERMINAL_NOTICE_PROJECTION_CONSUMERS` 精确为 5 个；AST test 逐项验证。
6. **waiting flag 漂移** — 首次 failed/lost/expiry 均为 `True`，replay 均为 `False`。
7. **admission idempotent replay**（`_record_terminal_cancel_ack` line 4305）— 使用 `confirm_terminal_run_in_transaction` + `wake_queue_promotion=False`，正确。
8. **dispatch `_closeout_worker_startup_failed`** — notice 在 `run_write` 返回后立即消费；`wake_queue_promotion` flag 为 pre-existing 表达式，非本次修复引入。
9. **engine_ingest `_fail_recovering_run` CAS_LOST/INVALID_STATE** — 仍返回 `terminal_notice=None`，正确。
10. **open_host.py close order** — coordinator 在 scheduler drain 后、delivery hub 前关闭，顺序正确。
11. **Tests**: `test_terminal_post_commit.py`（7 passed）、`test_run_attempt_transitions.py`（61 passed）、`test_wait_callback.py` + `test_wait_expiry_closeout.py` + `test_wait_cancel_late_result.py`（21 passed）。

**结果: 0 new material finding.**

---

## Open Questions

无。

## Residual Risk

无。S3-RR-F01 修复已验证完成：durable owner 唯一、五 consumer 全部 direct import/call、waiting 旧投影已删除、flags 与时点无漂移、tests 真实覆盖 missing 与四类 identity mismatch 以及五 consumer 闭集、所有边界扫描（Engine boundary、runtime、pyright、coverage、manifest、promotion allowlist）通过。

---

## 审查统计

- Production files re-reviewed: 9（+1 new `terminal_post_commit.py`）
- Test files re-reviewed: 2（`test_terminal_post_commit.py`、`test_run_attempt_transitions.py`）
- S3-RR-F01: **CLOSED**
- New material findings: **0**
- Pyright: 0 errors, 0 warnings, 0 informations
- Owner/static tests: 7 passed
- Owner behavior tests: 61 passed (in `test_run_attempt_transitions.py`)
- Waiting focused tests: 21 passed
