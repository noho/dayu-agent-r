# WU-TOOLS-01-F01 Slice S5 Fix Re-Review

## Gate Metadata

- Gate: fix re-review.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S5 - Fins Wait Adapter And Service Assembly Wiring`.
- Branch: `host-wu-tools-01-f01`.
- Artifact path: `docs/reviews/wu-tools-01-f01-s5-rereview-mimo.md`.
- Reviewer: mimo (claude code review agent).
- Scope guard: no commit, no code modification.

## 结论

**pass**

Controller accepted 的 5 个 test coverage findings 全部修复。Fix 只修改测试文件，未引入新 correctness / architecture / test regression。Host/Engine public contracts、Fins production mapping、Service provider detection semantics、README 均未变更。

---

## Accepted Findings 修复状态

### F01-S5-001 [medium] RUNNING 与 CANCELLING job 状态 poll_wait 测试

**状态：已修复。**

**证据：**
- `tests/fins/test_fins_ingestion_tools.py:439` — `running = _persist_job(runtime, "...0005", FinsIngestionJobStatus.RUNNING)`
- `tests/fins/test_fins_ingestion_tools.py:440` — `cancelling = _persist_job(runtime, "...0006", FinsIngestionJobStatus.CANCELLING)`
- `tests/fins/test_fins_ingestion_tools.py:446-447` — `running_poll` 和 `cancelling_poll` 调用 `adapter.poll_wait(...)`
- `tests/fins/test_fins_ingestion_tools.py:459-460` — 断言 `isinstance(running_poll, WaitPollNotReady)` 和 `isinstance(cancelling_poll, WaitPollNotReady)`

**验证：** `RUNNING` 和 `CANCELLING` 两个 active 状态均有直接 `poll_wait` 测试，断言返回 `WaitPollNotReady`。

---

### F01-S5-002 [medium] Service assembly 无 Fins awaiting provider 时显式测试

**状态：已修复。**

**证据：**
- `tests/service/test_host_assembly.py:549-570` — 新增 `test_tooling_options_without_fins_awaiting_providers_has_no_wait_adapter_registry`
- 使用普通非 Fins provider config（`provider_id="ordinary-provider"`, `import_path="dayu.tools.doc_provider:discover_tools"`）
- `tests/service/test_host_assembly.py:568-570` — 断言工具正常保留且 `tooling_options.wait_adapter_registry is None`

**验证：** 普通非 Fins 工具仍 assemble，`wait_adapter_registry is None`。

---

### F01-S5-003 [low] corrupt job evidence 测试

**状态：已修复。**

**证据：**
- `tests/fins/test_fins_ingestion_tools.py:464-478` — 新增 `test_fins_wait_poll_adapter_maps_corrupt_job_evidence_to_lost`
- `tests/fins/test_fins_ingestion_tools.py:473` — `_write_corrupt_job_evidence(workspace_root, job_id)` 写入 `"{not-json"` 损坏内容
- `tests/fins/test_fins_ingestion_tools.py:475` — `adapter.poll_wait(_wait_record(job_id, DOWNLOAD_TOOL_NAME))`
- `tests/fins/test_fins_ingestion_tools.py:477-478` — 断言 `isinstance(poll, WaitPollLost)` 和 `isinstance(poll.outcome, ResolveWaitLostOutcome)`

**验证：** corrupt evidence 映射为 `WaitPollLost` / `ResolveWaitLostOutcome`，不是 adapter error。

---

### F01-S5-004 [low] abandon_wait defensive tests

**状态：已修复。**

**证据（三个测试）：**

1. `tests/fins/test_fins_ingestion_tools.py:502-526` — `test_fins_wait_poll_adapter_abandon_without_external_job_ref_is_noop`
   - `include_external_job_ref=False` 构造 `WaitRecordRow`
   - 断言 `unchanged.cancellation_requested is False` 和 `unchanged.status is FinsIngestionJobStatus.RUNNING`

2. `tests/fins/test_fins_ingestion_tools.py:529-539` — `test_fins_wait_poll_adapter_abandon_missing_job_evidence_is_noop`
   - 使用不存在的 `job_id="finsjob_...9998"`
   - 断言不抛异常

3. `tests/fins/test_fins_ingestion_tools.py:543-556` — `test_fins_wait_poll_adapter_abandon_corrupt_job_evidence_is_noop`
   - 写入损坏 evidence 文件后调用 `abandon_wait`
   - 断言 `corrupt_path.exists()`（evidence 文件未被删除）

**验证：** `external_job_ref=None`、missing job evidence、corrupt job evidence 三种场景均不抛异常，不删除业务数据或 Host wait records。

---

### F01-S5-005 [low] workspace_root 缺失与相对路径 fail fast 测试

**状态：已修复。**

**证据（两个测试）：**

1. `tests/service/test_host_assembly.py:652-668` — `test_fins_awaiting_provider_missing_workspace_root_fails_before_open_host`
   - 使用 `config={}`（无 `workspace_root` 字段）
   - `pytest.raises(ValueError, match="non-empty absolute path")`

2. `tests/service/test_host_assembly.py:671-687` — `test_fins_awaiting_provider_relative_workspace_root_fails_before_open_host`
   - 使用 `config={"workspace_root": "relative/fins-workspace"}`
   - `pytest.raises(ValueError, match="must be absolute")`

**验证：** 两条 fail-fast 路径均通过 `_tooling_options_from_discovery(...)` 触发，发生在 `open_host` 前，错误有边界。

---

## Fix 引入检查

### Host/Engine contracts 是否变更

**结论：未变更。**

`git diff -- dayu/host/api.py dayu/host/wait_adapter.py dayu/host/tooling.py dayu/host/durable/state.py dayu/contracts/tool_await.py dayu/contracts/tool_outcome.py` 无输出。

### Fins production mapping 是否变更

**结论：未变更。**

`git diff -- dayu/fins/ingestion/wait_adapter.py` 无输出。`poll_wait` 和 `abandon_wait` 逻辑未修改。

### Service provider detection semantics 是否变更

**结论：未变更。**

`_fins_awaiting_tool_name_from_provider_config`（`host_assembly.py:1116-1138`）的 OR 逻辑未修改。

### README 是否变更

**结论：S5 implementation gate 已同步，fix 不需要再更新。**

Fix 只补 review 要求的测试覆盖，没有改变生产行为、公共接口、配置入口、用户命令、架构边界或测试分层说明。

---

## 验证命令结果

### 1. S5 核心测试

```bash
source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/fins/test_fins_ingestion_tools.py tests/host/test_phase7_waiting_integration.py tests/host/test_public_resolve_wait_resume.py -q
```

结果：`56 passed, 3 warnings`。warnings 为第三方 `edgar` deprecation。

### 2. Service 全量测试

```bash
source .venv/bin/activate && pytest tests/service -q
```

结果：`37 passed, 3 warnings`。

### 3. pyright 类型检查

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。

### 4. whitespace 检查

```bash
git diff --check
```

结果：通过。

---

## 新增 Findings

无。

---

## Residual / Blocker

- Residual risk: none introduced by this fix.
- Blocker: none.
