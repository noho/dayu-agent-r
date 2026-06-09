# Code Review — WU-TOOLS-01-F01-02 Slice 1

## Scope

- Mode: current changes
- Branch: `work/wu-tools-01-f01-02-cancellation`
- Base: `af3ac6b8` (accepted plan commit)
- Output file: `docs/reviews/wu-tools-01-f01-02-slice1-code-review-mimo.md`
- Included scope:
  - `dayu/fins/ingestion_runtime.py`
  - `dayu/fins/tools/download_tools.py`
  - `dayu/fins/tools/preprocess_tools.py`
  - `tests/fins/test_fins_ingestion_tools.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
  - `dayu/fins/README.md`
  - `tests/README.md`
  - `docs/host/issues-implementation-control.md` (controller bookkeeping, checked for consistency only)
  - `docs/reviews/wu-tools-01-f01-02-slice1-implementation-codex.md`
- Excluded scope: 未修改的生产模块、Host/Engine contract、Fins job store schema
- Parallel review coverage: 无

## Findings

### 001-未修复-低-`_create_queued_job` 重构后成为死代码

- **入口/函数**: `FinsIngestionRuntime._create_queued_job`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:1160-1193`
- **输入场景**: 任何调用路径
- **实际分支**: 无调用方；`start_download` 和 `start_preprocess` 已改为直接调用 `_create_queued_job_record`
- **预期行为**: 重构后旧 wrapper 应被删除或标记为保留理由
- **实际行为**: `_create_queued_job` 方法体仍然存在，持有 `_start_lock` 并调用 `_create_queued_job_record`，但全仓无调用方
- **直接证据**: `grep -n '_create_queued_job\b' dayu/fins/` 仅命中定义行 1160；`start_download` (1050-1068) 和 `start_preprocess` (1107-1124) 直接在自己的 `_start_lock` 块内调用 `_create_queued_job_record`
- **影响**: 死代码增加维护负担；后续开发者可能误以为 `_create_queued_job` 是正确入口
- **建议改法和验证点**: 删除 `_create_queued_job` 方法；运行 `pyright` 和全量 `pytest tests/fins/` 确认无引用
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 002-未修复-低中-`request_cancel` OSError 导致已创建 job 停在 QUEUED 且未提交

- **入口/函数**: `FinsIngestionRuntime.start_download` / `start_preprocess` 的 create 后取消路径
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:1058-1059` (download), `dayu/fins/ingestion_runtime.py:1115-1116` (preprocess)
- **输入场景**: token 在 create 后、submit 前已取消；`request_cancel` 内部 `file_lock` 获取失败抛出 `OSError`（含 `RuntimeFileLockError`）
- **实际分支**: `_is_start_cancelled` 返回 `True` → 调用 `self.request_cancel(start.job_id)` → `file_lock` 超时抛出 `OSError` → 异常传播到工具 callable → 被 `except OSError` 捕获 → 返回 `ToolFailedOutcome(error="fins_download_start_failed")`
- **预期行为**: plan 要求 "cancel checkpoint 不吞掉 OSError；若 start 后 request_cancel 因 OSError 失败，返回 failed outcome，hint 指向 Fins workspace 存储权限"；当前实现满足此要求
- **实际行为**: 工具返回 failed outcome 符合 plan；但 durable job record 已以 `QUEUED` 状态持久化，executor 未收到 submit，job 成为无后台 runner 的 orphan
- **直接证据**: `dayu/fins/ingestion_runtime.py:1050-1068`：`_create_queued_job_record` 在 1051 行写入 job；1058 行 `_is_start_cancelled` 返回 `True`；1059 行 `self.request_cancel` 若抛 `OSError` 则 1060-1067 行的 `executor.submit` 不执行
- **影响**: orphan QUEUED job 存在于 job store，无后台 runner 将其推进到终态。概率极低（需 file_lock 超时），且原代码在 `executor.submit` 失败时也有类似 orphan 窗口
- **建议改法和验证点**: 当前行为符合 plan 且与原代码失败模式一致，可接受为 residual limitation。若需加固，可在 `_start_lock` 块内用 try/except 包裹 `request_cancel`，失败时尝试将 job 标记为 `FAILED`；但会增加复杂度，建议 deferred
- **修复风险（低/中/高）**: 中（需额外 error recovery 逻辑）
- **严重程度（低/中/高/严重）**: 低

### 003-未修复-低-runtime 测试 checkpoint 断言依赖 check_count 计数

- **入口/函数**: `test_download_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit` / `test_preprocess_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit`
- **文件(行号)**: `tests/fins/test_fins_ingestion_runtime.py:571`, `tests/fins/test_fins_ingestion_runtime.py:781`
- **输入场景**: `_CancelOnSecondCheckToken` 计数驱动
- **实际分支**: `assert token.check_count == 2`
- **预期行为**: 测试应验证 observable behavior（job 状态、executor 未提交）而非内部 checkpoint 次数
- **实际行为**: `check_count == 2` 断言绑定到当前实现恰好 2 次 checkpoint 的事实；若未来实现增加 checkpoint 密度（如 plan Slice 4 所述），测试会因计数不匹配而失败
- **直接证据**: `tests/fins/test_fins_ingestion_runtime.py:571`：`assert token.check_count == 2`
- **影响**: 测试与实现细节耦合；不影响当前 correctness，但增加未来重构的维护成本
- **建议改法和验证点**: 可改为 `assert token.check_count >= 2` 或移除计数断言，只保留 behavior 断言（`start.status is CANCELLING`、`executor.operations == []`）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Residual Risk

| ID | Risk / uncovered area | Classification | Disposition |
|---|---|---|---|
| R1 | Awaiting accept 前 orphan job 窗口：job 可能已 submit 但 awaiting outcome 尚未被 Host durable accept。 | deferred to later WU | Plan 已将两阶段启动 deferred 到 WU-WAIT-03 或独立 follow-up。 |
| R2 | submit 后无法用 Host token 抢占已进入后台的同步 I/O。 | accepted residual limitation | 当前设计以 Fins job store durable cancel 为后台真源。 |
| R3 | create 后 cancel 返回 `ToolCancelledOutcome` 与 job record 停在 `CANCELLING`：无后台 runner 将其收口为 `CANCELLED`。 | accepted by plan | 这是 plan 允许的 durable cancel fact；后续 wait adapter / cleanup 可处理。 |
| R4 | `request_cancel` OSError 后 orphan QUEUED job（Finding 002）。 | accepted residual limitation | 概率极低，与原代码失败模式一致。 |
| R5 | `_create_queued_job` 死代码（Finding 001）。 | needs cleanup | 删除即可，无行为风险。 |

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q` → **48 passed, 3 warnings** (edgar deprecation warnings only)
- `source .venv/bin/activate && pyright dayu/fins tests/fins` → **0 errors, 0 warnings, 0 informations**
- README 更新：`dayu/fins/README.md` 已读取 `Agent更新约束【必须遵守】`，更新内容属于当前已实现的 awaiting tool capability、runtime 接口和 durable cancel 关键机制；`tests/README.md` 更新属于 `tests/fins/` 当前测试分层职责

## Conclusion

**未发现 blocking 问题。** Slice 1 实现符合 plan 的所有 invariant：

- start 前 token cancel 不创建 durable job ✅
- durable job create 后、executor.submit 前同步 checkpoint 无 "看到取消仍 submit" 窗口 ✅
- holding `_start_lock` 时调用 `request_cancel` 无死锁（file_lock 顺序获取/释放，不嵌套） ✅
- create 后 cancel 返回 `ToolCancelledOutcome` 与 job record 停在 `CANCELLING` 符合 plan ✅
- submit 后不再使用 Host token ✅
- `ToolCancelledOutcome` meta/message/hint LLM-facing 自解释 ✅
- OSError / ValueError / terminal job handling 保持旧行为 ✅
- tests 覆盖 plan 要求的 4 个 required behavior ✅
- README 更新符合 Agent更新约束 ✅

**Slice 1 可进入 accepted slice commit。**
