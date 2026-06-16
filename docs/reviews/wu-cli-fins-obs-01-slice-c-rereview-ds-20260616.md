# WU-CLI-FINS-OBS-01 Slice C Re-Review (AgentDS)

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `Slice C: Fins ingestion runtime core API convergence`
- Gate: re-review (review fix)
- Reviewer: AgentDS
- Date: 2026-06-16
- Review artifact: `docs/reviews/wu-cli-fins-obs-01-slice-c-review-ds-20260616.md`
- Fix artifact: `docs/reviews/wu-cli-fins-obs-01-slice-c-review-fix-codex.md`
- Plan 真源: `docs/host/wu-cli-fins-obs-01-replacement-plan.md`

## Scope

仅审查 review fix 补丁中相对于原始 implementation 的增量变更：

1. `dayu/fins/ingestion_runtime.py`：missing RESULT 兜底 + `_put_direct_queue` 取消注释
2. `tests/fins/test_fins_ingestion_runtime.py`：新增 missing-result 测试

## 修复项核对

### DS-C01: Runtime `_run_direct_stream` missing RESULT 兜底

**Fix**：在 `_run_direct_stream` 的 consumer loop 结束后增加 `if not result_seen: yield _direct_missing_result_event(context)`（`ingestion_runtime.py:2092-2093`）。

**核对**：

- `_direct_missing_result_event`（line 3911-3941）构造 `FinsEvent(RESULT, status=FAILURE, exit_code=1)`，字段仅来自 `context.direct_operation_kind`、`context.normalized_ticker`、`_direct_filing_kind(context.source_kind)` 和固定常量 `_DIRECT_FAILURE_TITLE`（"操作失败"）、`_DIRECT_ERROR_TEXT_FALLBACK`（"执行失败"）。
- 不含 `job_id`、`cursor`、`sequence`、sidecar path、absolute path、raw provider payload、document body。✅
- `error_kind=FinsErrorKind.EXECUTION`，表达 runtime 自身未能产出业务终态。✅
- 不依赖 job store、sidecar、durable record。✅

**验证**：新增测试 `test_direct_stream_missing_result_returns_failure_result`（test line 977-1014）使用不 emit 任何事件的 `quiet_producer`，断言 runtime 产出唯一 `RESULT(status=FAILURE, exit_code=1)`。60/60 tests pass。

### DS-C02: `_put_direct_queue` 取消注释

**Fix**：在 `_put_direct_queue` 的 `cancellation_state.is_cancelled()` 返回 `False` 分支前增加中文注释（line 3902）："consumer 已结束时丢弃后续事件，避免同步 producer 卡在无人读取的队列上。"

**核对**：注释准确描述了设计意图——best-effort cooperative cancellation 下 producer 在 consumer 退出后丢弃后续 queue put。✅

### MiMo F1: 不处理

Fix artifact 裁决该项（极端反压轮询开销）为已知 sync adapter 桥接实现限制，不外露为公共契约，不扩大设计。符合 plan 的 async 裁决。本 re-review 认可该裁决。

## 验证

### 测试

```
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q
60 passed, 3 warnings in 2.74s
```

新增 `test_direct_stream_missing_result_returns_failure_result` 通过。所有已有测试保持通过，无回归。

交叉验证：

```
source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py ... -q
98 passed, 3 warnings in 2.23s
```

Slice A/B 测试全部保持通过。

### Pyright

```
source .venv/bin/activate && pyright dayu/fins/ingestion_runtime.py dayu/fins/service_runtime.py tests/fins/test_fins_ingestion_runtime.py
0 errors, 0 warnings, 0 informations

source .venv/bin/activate && pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

### git diff --check

通过。

## 逐项核对（re-review scope）

| 核对项 | 结论 |
|---|---|
| 1. runtime direct stream 仍返回 AsyncIterator[FinsEvent] | ✅ 未改变 `_run_direct_stream` 返回类型 |
| 2. producer 静默结束 → 唯一 FAILURE RESULT，不静默结束 | ✅ line 2092-2093 补齐兜底，测试覆盖 |
| 3. failure RESULT 不泄漏 job id/cursor/sidecar/path/raw payload | ✅ `_direct_missing_result_event` 仅用 context 业务字段 |
| 4. 没有引入 job/durable/sidecar 依赖 | ✅ 纯内存 `FinsEvent` 构造，无 I/O |
| 5. asyncio.to_thread/thread/queue bridge 仍是 internal bounded detail | ✅ 未改动 bridge 结构，无新增 public API |

## Findings

无新增 findings。DS-C01 和 DS-C02 已修复，MiMo F1 按 fix artifact 裁决不扩大设计。

## 结论

**PASS**

DS-C01（missing RESULT 兜底）和 DS-C02（取消注释）均已正确修复。修复未引入新的 job/durable/sidecar 依赖，未放宽 leakage guard，未改动 bridge 架构。测试 60/60 通过，pyright 0 errors，跨 slice 无回归。无 blocking findings。
