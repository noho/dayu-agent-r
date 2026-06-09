# Code Review — WU-TOOLS-01-F01-03 Slice 1

## Metadata

- Review mode: current changes (deepreview)
- Branch: `phase/wu-tools-01-f01-03`
- Base: `main`
- Artifact path: `docs/reviews/wu-tools-01-f01-03-slice1-code-review-ds.md`
- Date: 2026-06-09T11:10:39+08:00
- Reviewer: deepreview (Claude Opus 4.6)
- Controller verification: 35 passed, pyright 0 errors, git diff --check passed

## Scope

- Included:
  - `dayu/fins/ingestion_runtime.py` (upload contract 与 job foundation)
  - `tests/fins/test_fins_ingestion_runtime.py` (35 tests)
  - `dayu/fins/README.md` (upload 相关更新)
  - `tests/README.md` (upload 测试覆盖更新)
- Excluded:
  - OLD downloader/pipeline 代码 (不在 Slice 1 范围)
  - `docs/host/issues-implementation-control.md` (controller-owned dirty file，本次未修改)
  - Host/Engine contract 文件 (Slice 1 不触碰)
- Reference:
  - `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md` (accepted plan)
  - `docs/reviews/wu-tools-01-f01-03-slice1-implementation-codex.md` (implementation artifact)
  - `dayu/fins/domain/enums.py` (SourceKind 定义)
  - `dayu/contracts/json_value.py` (JsonValue 定义)
- Parallel review coverage: 无 (单文件核心模块 + 测试，无需并行)

## Review Method

审查沿以下真实入口逐行走读：

1. `FinsIngestionRuntime.start_upload(...)` → `_create_queued_record_with_start_lock(...)` → cancel checkpoint → `executor.submit(...)`
2. `_run_upload_job(...)` → `_mark_job_running_or_cancelled(...)` → `upload_runner is None` 分支 → `_save_failed(...)` / `upload_runner.run_upload(...)` → cancel check → `_save_succeeded(...)` / `_save_cancelled(...)`
3. `_upload_request_summary(...)` → 有界字段构建 → `_assert_bounded_summary(...)`
4. `FinsUploadResultSummary.to_json_summary()` → 有界字段输出
5. `_record_to_json(...)` / `_record_from_json(...)` → upload operation shape validation
6. `FsFinsIngestionJobStore.save_succeeded_or_cancelled(...)` / `claim_running_or_cancelled(...)` → atomic terminal guard
7. 测试覆盖每条关键路径的 happy path、cancel path、boundary、unsupported failure、SourceKind discrimination

额外执行 adversarial failure pass，沿取消竞态、终态覆盖、文件路径泄漏、类型越界四条线索逐条件验证。

## Verdict

**pass-with-findings** — 0 blocking findings, 2 low-severity findings.

核心审查结论：

- upload request/result/runner/cancellation checker contract 使用已有 `SourceKind` 区分 filing/material，未新增 `FinsUploadKind`；类型强、有界、可序列化。
- `start_upload` 遵循 durable queued → background runner → terminal record 的长事务建模；create 后 submit 前取消有落盘终态；runner 取消检查器来自 Fins job store (`_RuntimeJobCancellationChecker`)。
- 未装配 production upload runner 时明确写入 failed terminal，不读取本地上传文件、不写 source/blob 仓储、不伪造成功。
- job record 序列化/反序列化正确约束 upload 的 `operation/source/source_kind` 组合；`request_summary` 只保存 `file_count` 不保存本地文件路径。
- 未违反 AGENTS.md 分层、类型、docstring、无 Any/object、无兼容 wrapper、无魔法字符串等约束。
- 测试覆盖 35 条，涵盖核心边界（queued persistence、ticker normalization、create-submit cancellation、unsupported terminal、SourceKind discrimination、bounded summary、serialization validation、record leakage、cancel race、atomic temp file cleanup）；README 更新命中职责且不过度扩写。

以下 2 条 low-severity finding 不阻塞 merge，建议在后续 Slice 中评估修复。

## Findings

### 1-未修复-低-_save_cancelled 绕过原子终态守护

- **入口/函数**: `FinsIngestionRuntime._save_cancelled` → `FsFinsIngestionJobStore.save_job`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:2183-2205`, `dayu/fins/ingestion_runtime.py:957-978`
- **输入场景**: 后台 runner 在 `read_job` 到 `_save_cancelled` 之间，另一进程或线程已通过 `save_succeeded_or_cancelled` 写入终态。
- **实际分支**: `_save_cancelled` 调用 `self.job_store.save_job(record)` → `FsFinsIngestionJobStore.save_job` 直接执行 `_write_record_locked(record)`，不检查 record 是否已是终态（line 973-977）。
- **预期行为**: 对已是终态的 job，`_save_cancelled` 应幂等吸收或拒绝覆盖，保持与 `_save_succeeded` 一致的原子终态守护语义。`_save_succeeded` 调用 `save_succeeded_or_cancelled`（line 2177），该路径在 `FsFinsIngestionJobStore` 中会先读取当前状态，若已是终态则原样返回（line 1006-1008）。
- **实际行为**: 若 `_save_cancelled` 被传入已是 SUCCEEDED/FAILED 终态的 record（例如 TOCTOU 窗口中另一进程写入），`save_job` 会直接覆盖为 CANCELLED，造成终态被改写。
- **直接证据**: line 2183-2205 的 `_save_cancelled` 方法体调用 `self.job_store.save_job(...)`；line 973-977 的 `FsFinsIngestionJobStore.save_job` 无条件写入。对比 line 1006-1008 的 `save_succeeded_or_cancelled` 先检查 `record.status in _TERMINAL_STATUSES` 再写入。
- **影响**: 在单进程 daemon thread 模型下风险极低（所有 call site 均先读取确认非终态再调用，且 runner 是单线程）。但在未来多进程 job store 场景下，存在终态被覆盖的理论可能。
- **建议改法和验证点**: 将 `_save_cancelled` 改为调用 `save_succeeded_or_cancelled`（终态判定后写入 CANCELLED），或新增强制 cancelled 写入的 store 方法并在其中加入终态幂等检查。验证点：构造已终态 record 传入 `_save_cancelled`，断言终态不被覆盖。
- **修复风险（低）**: 仅涉及私有方法内部 save 路径替换，所有 call site 行为不变。
- **严重程度（低）**:

### 2-未修复-低-_validate_upload_source_kind 对联合类型新增成员无防御

- **入口/函数**: `_validate_upload_source_kind`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:2654-2672`
- **输入场景**: 未来向 `FinsUploadRequest` 联合类型中新增第三种请求类型（例如 `FinsUploadBulkRequest`），且该类型默认 `source_kind=SourceKind.MATERIAL`。
- **实际分支**: 当前函数先 `isinstance(request, FinsUploadFilingRequest)` 判断 filing，else 分支（line 2671-2672）默认按 material 校验。任何非 filing 类型都会落入 material 校验，不会报"未知上传请求类型"错误。
- **预期行为**: 对 `FinsUploadRequest` 联合成员做穷尽检查，非 filing 非 material 类型应 fail-fast。
- **实际行为**: 非 filing 类型只要 `source_kind` 是 `SourceKind.MATERIAL` 即通过校验。
- **直接证据**: line 2667-2672，else 分支无条件进入 `if request.source_kind is not SourceKind.MATERIAL` 检查，缺乏对 `FinsUploadMaterialRequest` 的显式 isinstance 守卫。
- **影响**: 当前联合只有两个成员，不影响正确性。若后续 Slice 新增第三种上传请求类型，可能静默通过校验。
- **建议改法和验证点**: 将 else 分支改为 `elif isinstance(request, FinsUploadMaterialRequest):`，末尾加 `else: raise TypeError(...)`。验证点：构造未知类型传入，断言 TypeError。
- **修复风险（低）**: 当前联合只有两个成员，改动不影响现有行为。
- **严重程度（低）**:

## Open Questions

无。

## Residual Risk

1. **Production upload workflow 未接入**：当前 Slice 1 只建立 runner boundary 与 job lifecycle，默认 runner absent 会失败终态。这是计划内的 Slice 4 负责范围，不阻塞当前 Slice。

2. **Upload awaiting tool/provider/wait adapter 未接入**：`start_upload` 目前只有 direct runtime API，没有 tool provider 或 Host wait adapter 绑定。这是计划内的 Slice 5 负责范围。

3. **Daemon-thread job crash recovery**：当前 Slice 未引入 crash recovery，非终态 job 在进程崩溃后可能停留。此风险已由 Issue 129 / WU-WAIT-02 / Issue 90 追踪，不属于 Slice 1 scope。

4. **External job physical cancel/revoke**：当前只有 cooperative cancellation checker，不保证物理取消。此风险已由 WU-WAIT-03 / Issue 92 追踪。

5. **`_save_cancelled` 与 `_save_succeeded` 的 save path 不一致**：见 Finding 1。在单进程 daemon thread 模型下风险极低，后续 Slice 如引入多进程 job store 访问应优先修复。
