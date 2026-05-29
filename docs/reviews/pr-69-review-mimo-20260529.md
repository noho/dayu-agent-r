# Code Review

## Scope

- Mode: PR
- PR: #69 — Host Phase 13 audit trace outbox projections
- Author: noho
- Branch: `feat/phase-13-audit-trace-outbox` → `main`
- URL: https://github.com/noho/dayu-agent-r/pull/69
- Output file: `docs/reviews/pr-69-review-mimo-20260529.md`
- Included scope: PR diff (53 files, ~13k lines), design docs, implementation-control.md, phase13 plan
- Excluded scope: dayu/engine, dayu/service, dayu/ui, dayu/fins (per plan non-goals)
- Parallel review coverage: 4 subagents — (1) schema + durable layer, (2) API + public contract, (3) sink implementations, (4) tests + PR description

## Findings

### F001-未修复-高-冷 JSONL 复制完整 raw payload

- **入口/函数**: `_build_cold_line()` in `dayu/host/tool_trace.py:694`
- **文件(行号)**: `dayu/host/tool_trace.py:694`
- **输入场景**: 任何 `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` 等 tool trace 事件被 cold JSONL writer 消费时
- **实际分支**: `_build_cold_line()` 无条件将 `event.payload`（完整 EventLog raw payload）写入 cold JSONL line
- **预期行为**: plan 规定 cold JSONL 为 "hot fields 的 superset + long args/result summaries, truncation metadata, duplicate governance context, wait/cancel/timeout detail, provider / tool raw diagnostic refs"；design.md §14.1 明确 "不复制大 payload"；line 已包含 `source_payload_ref` + `source_payload_digest` 提供检索间接引用
- **实际行为**: `_FIELD_PAYLOAD: event.payload` 将完整 raw payload 原样写入 append-only JSONL，包括 `TOOL_RESULT_ACCEPTED` 等事件可能携带的大工具输出
- **直接证据**: `tool_trace.py:694` — `_FIELD_PAYLOAD: event.payload,`；对比 `audit.py` 同类场景只写 `payload_ref` + `payload_digest`
- **影响**: 磁盘空间膨胀、违背 ref-based indirection 设计、大 payload 事件导致 JSONL 文件快速增长；不影响 correctness，但违反 plan scope boundary
- **建议改法和验证点**: 将 `_FIELD_PAYLOAD: event.payload` 改为只写提取后的 typed fields（如 `extracted.*`），与 hot row 对齐；或若确需完整 payload 做离线分析，需在 plan review 中显式标注并获得确认
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### F002-未修复-低-模块私有 helper 跨文件重复

- **入口/函数**: `_operation_context_refs`, `_optional_mapping`, `_append_text`, `_require_path`, `_utc_now_text`
- **文件(行号)**: `audit.py:388/402/505/542/558` vs `tool_trace.py:832/856/943/957/973`；`_utc_now_text` 还出现在 `projection.py:703`, `outbox.py:509`
- **输入场景**: 无（静态代码结构问题）
- **实际分支**: N/A
- **预期行为**: CLAUDE.md 要求 "重复逻辑必须抽取"
- **实际行为**: 5 个函数在 audit.py 和 tool_trace.py 间完全复制
- **直接证据**: 逐行对比确认 identical
- **影响**: 维护成本；若任一函数需修改，必须同步多处
- **建议改法和验证点**: 抽取到 `dayu/host/durable/codec.py` 或新建 `dayu/host/_sink_helpers.py`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F003-未修复-低-OutboxProjectionStatus.FAILED 路径无测试

- **入口/函数**: `read_outbox_terminal_items()` / `drain_outbox_terminal_items()` in `dayu/host/read_api.py`
- **文件(行号)**: `tests/host/test_public_outbox_api.py`
- **输入场景**: catch_up_outbox_terminal_projection 抛异常时
- **实际分支**: 未测试
- **预期行为**: plan 要求 "projection lag / failure status 返回"；`OutboxProjectionStatus.FAILED` 是 public enum，调用方必须处理
- **实际行为**: `FAILED` enum 值从未在任何测试断言中出现；`LAGGED` 有测试（monkeypatch catch-up 为 no-op），`FAILED` 无
- **直接证据**: `OutboxProjectionStatus` 有三个成员 `CAUGHT_UP / LAGGED / FAILED`；grep 所有测试文件未找到 `FAILED` 断言
- **影响**: 公开 API 的 failure status 转换契约未被验证
- **建议改法和验证点**: 新增测试：monkeypatch catch-up 抛异常 → read 返回 `projection_status=FAILED` + error_code/message
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F004-未修复-低-read_api.__all__ 不完整

- **入口/函数**: `dayu/host/read_api.py:1035`
- **文件(行号)**: `dayu/host/read_api.py:1035`
- **输入场景**: 直接 `from dayu.host.read_api import *` 或模块文档查阅
- **实际分支**: `__all__ = ["get_run", "get_session"]`，但 `__init__.py` 实际从此模块导入 7 个符号
- **预期行为**: `__all__` 应反映模块实际导出
- **实际行为**: 5 个既有函数 + 2 个新 outbox 函数缺失
- **直接证据**: `read_api.__all__` vs `__init__.py` import block
- **影响**: 不影响 public package API（由 `__init__.py` 管辖）；直接读模块时 `__all__` 误导
- **建议改法和验证点**: 补齐 `__all__`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Verification Summary

### PR Description Accuracy — PASS

- "Add Phase 13 audit JSONL sink, tool trace hot/cold projections, and outbox terminal projection" — 确认
- "Add public Outbox terminal read/drain API as the only additive public Host extension" — 确认；`OpenHostOptions` 无新字段
- "Outbox drain is not channel delivery success" — 确认；drain 只更新 item_state
- "no command path or watch_session_events replay change" — 确认
- 不声称 payload reader / timeline replay — 确认

### Phase 13 Completeness — PASS

| Slice | Status | Notes |
|-------|--------|-------|
| Slice 1: LogAuditSink JSONL | ✅ | audit.py, durable/audit.py, schema bump |
| Slice 2: Tool Trace Hot/Cold | ✅ | tool_trace.py, durable/tool_trace.py, query helpers |
| Slice 3: OutboxSink | ✅ | outbox.py, durable/outbox.py, idempotency |
| Slice 4: Public API + Smoke | ✅ | api.py, read_api.py, open_host.py, __init__.py, README |

### Import Boundary — PASS

- `read_api.py`: 无 `dayu.engine` / `dayu.service` / `dayu.ui` / `dayu.fins` import
- `durable/*`: 无反向依赖
- F001 aggregate fix（read_api import boundary）确认通过

### Schema — PASS

- `HOST_SCHEMA_VERSION` 从 10 升至 13（4 slices 各 bump 1 次，最终状态为 13）
- 4 张新表 DDL / indexes / CHECK constraints 完整
- checkpoint 只在成功写入后推进

### CI / Local Validation

- PR description 声称：aggregate suite 96 passed、aggregate fix suite 108 passed、pyright 0 errors、git diff --check passed
- `gh pr checks` 返回 exit code 1（CI checks 未配置或未运行），但 PR description 已记录本地验证结果

## Open Questions

- **F001 cold payload 是否 intentional**: `_FIELD_PAYLOAD: event.payload` 是为离线分析工具刻意保留完整 payload，还是遗漏？若 intentional，需在 plan 中显式标注 scope deviation。

## Residual Risk

| Risk | Owner | Status |
|------|-------|--------|
| JSONL / SQLite cross-media exactly-once | Phase 15 | PR description 已声明，implementation-control.md Phase 15 tracking 已覆盖 |
| Outbox drain ≠ channel delivery success | Phase 13 (acknowledged) / Phase 15 (hardening) | PR description 已声明 |
| purge / retention / cleanup | Phase 15 | implementation-control.md Phase 15 tracking 已覆盖 |
| 外部 audit 系统 / 长期归档 | Phase 15+ | implementation-control.md 已覆盖 |

所有 residual risks 均在 `docs/host/implementation-control.md` 中有 owner。

## Verdict

**PASS** — 无 blocking findings。PR 完整实现 Phase 13 全部 4 slices，public API shape 与 plan 一致，import boundary 通过，PR description 准确。F001（cold payload 复制）为 high severity 但 non-blocking（不影响 correctness，可作为 follow-up fix）；其余 findings 均为 low severity。
