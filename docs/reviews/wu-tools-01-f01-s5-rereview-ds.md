# WU-TOOLS-01-F01 Slice S5 Fix Re-Review

## Gate Metadata

- Gate: deepreview.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S5 - Fins Wait Adapter And Service Assembly Wiring`.
- Artifact path: `docs/reviews/wu-tools-01-f01-s5-rereview-ds.md`.
- Scope: 定向复审，只验证 5 个 Controller accepted findings 的修复状态及 fix 是否引入新 regression。
- Scope guard: no commit, no code modification.

## 结论

**pass**

全部 5 个 Controller accepted findings 均已正确修复。修复严格限定于测试文件，未修改 Host/Engine contract、Fins production mapping、Service detection semantics 或 README。未引入新的 correctness / architecture / test regression。所有验证命令通过。

## 验证命令结果

### 1. S5 核心测试

```bash
source .venv/bin/activate && pytest tests/service/test_host_assembly.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/host/test_phase7_waiting_integration.py \
  tests/host/test_public_resolve_wait_resume.py
```

结果: `56 passed, 3 warnings`。warnings 来自第三方 edgar deprecation。

### 2. Service 全量测试

```bash
source .venv/bin/activate && pytest tests/service -q
```

结果: `37 passed, 3 warnings`。

### 3. pyright 类型检查

```bash
source .venv/bin/activate && pyright
```

结果: `0 errors, 0 warnings, 0 informations`。

### 4. 合约边界确认

```bash
git diff HEAD --name-only
```

修改文件为: `dayu/README.md`, `dayu/fins/README.md`, `dayu/service/host_assembly.py`, `docs/host/issues-implementation-control.md`, `tests/README.md`, `tests/fins/test_fins_ingestion_tools.py`, `tests/service/test_host_assembly.py`, `tests/service/test_import_boundary.py`。

其中 Host/Engine contract 文件零修改 (`dayu/host/`, `dayu/engine/`, `dayu/contracts/` 均无 diff)，READM… 变更来自 S5 implementation gate。

Fix 本身只触及测试文件与 fix artifact，符合 Controller fix scope 要求。

## 逐项复审

### F01-S5-001 — RUNNING 与 CANCELLING job 状态 poll_wait 测试

**状态: 已修复，通过。**

`tests/fins/test_fins_ingestion_tools.py:427-461`

- L439 新增 `running` job (FinsIngestionJobStatus.RUNNING)，通过 `_persist_job` 持久化
- L440 新增 `cancelling` job (FinsIngestionJobStatus.CANCELLING)
- L446 `adapter.poll_wait(_wait_record(running.job_id, DOWNLOAD_TOOL_NAME))`，正确使用 job_id 与 tool_name
- L447 cancelling poll 同理
- L459 `assert isinstance(running_poll, WaitPollNotReady)` — 断言 RUNNING 映射为 WaitPollNotReady
- L460 `assert isinstance(cancelling_poll, WaitPollNotReady)` — 断言 CANCELLING 映射为 WaitPollNotReady

新增 2 个活跃状态断言，与 `_ACTIVE_STATUSES` frozenset（`wait_adapter.py:64-70`）中 QUEUED/RUNNING/CANCELLING 三个活跃状态一致。测试中的 job record 持久化与 adapter 使用同一 runtime 实例，隔离正确。若后续误删 `_ACTIVE_STATUSES` 中 RUNNING 或 CANCELLING，该测试会捕获回归。

### F01-S5-002 — 无 Fins awaiting provider 时 wait_adapter_registry is None

**状态: 已修复，通过。**

`tests/service/test_host_assembly.py:549-570`

- L549-565 `test_tooling_options_without_fins_awaiting_providers_has_no_wait_adapter_registry`
- 使用 `_provider_config(provider_id="ordinary-provider", import_path="dayu.tools.doc_provider:discover_tools", source_id="dayu.tools.doc_provider")` — 三个字段均不匹配 Fins 标识
- 传入普通非 Fins 工具 `lookup_fact`
- L568 断言普通工具仍正常装配 (`definitions[0].name == "lookup_fact"`)
- L570 断言 `tooling_options.wait_adapter_registry is None`

覆盖 S5 预期行为: 只有启用的 Fins awaiting provider config 才触发 wait adapter registry 绑定；普通非 Fins 工具不受影响。

### F01-S5-003 — corrupt job evidence poll_wait 映射为 WaitPollLost

**状态: 已修复，通过。**

`tests/fins/test_fins_ingestion_tools.py:464-478`

- L464-478 `test_fins_wait_poll_adapter_maps_corrupt_job_evidence_to_lost`
- L472-473 `_write_corrupt_job_evidence(workspace_root, job_id)` 写入 `{not-json` 损坏文件
- L475 `adapter.poll_wait(_wait_record(job_id, DOWNLOAD_TOOL_NAME))`
- L477 `assert isinstance(poll, WaitPollLost)` — corrupt evidence → lost，不是 adapter error
- L478 `assert isinstance(poll.outcome, ResolveWaitLostOutcome)` — outcome 类型正确

helper `_write_corrupt_job_evidence`（L699-716）写入不可解析的 JSON 内容，路径与 FsFinsIngestionJobStore 一致。验证了 `poll_wait` 的 `except (FileNotFoundError, ValueError)` 分支将 corrupt evidence 映射为 WaitPollLost，不会作为 adapter error 向上抛出。

### F01-S5-004 — abandon_wait defensive tests

**状态: 已修复，通过。**

三个测试覆盖 abandon_wait 的三个防御路径:

1. `test_fins_wait_poll_adapter_abandon_without_external_job_ref_is_noop` (L502-526):
   - 使用 `_wait_record(..., include_external_job_ref=False)` 构造无 external_job_ref 的 record
   - 断言不抛异常（L516-522）
   - L524-526 断言 job 未被修改 (`cancellation_requested is False`, status 仍为 RUNNING)

2. `test_fins_wait_poll_adapter_abandon_missing_job_evidence_is_noop` (L529-540):
   - 使用不存在 job_id `finsjob_00000000000000000000000000009998`
   - 断言不抛异常

3. `test_fins_wait_poll_adapter_abandon_corrupt_job_evidence_is_noop` (L543-556):
   - 写入 corrupt evidence 后调用 abandon_wait
   - 断言不抛异常
   - L556 `assert corrupt_path.exists()` — 损坏 evidence 文件未被删除

三条均对应 `abandon_wait` 的防御路径: `job_id is None` early return (L137-138) 和 `except (FileNotFoundError, ValueError)` 分支 (L141-142)。验证 abandon 只请求取消，不删除业务数据或 Host wait records。

### F01-S5-005 — workspace_root 缺失 / 相对路径 fail fast

**状态: 已修复，通过。**

两个测试覆盖 `_fins_workspace_root_from_provider_config` 的 fail fast 路径:

1. `test_fins_awaiting_provider_missing_workspace_root_fails_before_open_host` (L652-668):
   - 使用 `_provider_config_with_config(config={})` — 无 workspace_root 字段
   - L655 `pytest.raises(ValueError, match="non-empty absolute path")`
   - 触发路径: `_fins_workspace_root_from_provider_config` → `config.get(_FINS_WORKSPACE_ROOT_CONFIG_FIELD)` 返回 None → ValueError

2. `test_fins_awaiting_provider_relative_workspace_root_fails_before_open_host` (L671-687):
   - 使用 `config={"workspace_root": "relative/fins-workspace"}` — 相对路径
   - L674 `pytest.raises(ValueError, match="must be absolute")`
   - 触发路径: `_fins_workspace_root_from_provider_config` → `workspace_root.is_absolute()` 为 False → ValueError

两条路径均通过 `_tooling_options_from_discovery(...)` 触发，发生在 open_host 前，错误消息有边界（"non-empty absolute path" / "must be absolute"）。

## Fix 范围合规检查

| 检查项 | 状态 | 说明 |
|--------|------|------|
| Host/Engine contract 未修改 | 通过 | `dayu/host/`, `dayu/engine/`, `dayu/contracts/` 零 diff |
| Fins production mapping 未修改 | 通过 | `wait_adapter.py` 未被 fix 触及 |
| Service detection semantics 未修改 | 通过 | `host_assembly.py` diff 来自 S5 implementation，fix 未追加变更 |
| README 未修改 | 通过 | 无 fix 触发的 README 变更 |
| 默认 config 未修改 | 通过 | 无 config 文件变更 |
| 只改测试文件 | 通过 | Fix 仅新增测试函数与两个测试 helper |

## 测试 Helper 审查

- `_write_corrupt_job_evidence` (L699-716): 写入损坏 JSON 到正确路径，有完整 docstring。使用 `{not-json` 确保 JSON 解析失败。
- `_provider_config_with_config` (L1585-1611): 允许测试直接传入 raw config dict，用于 missing/relative workspace_root 场景。
- `_wait_record` 的 `include_external_job_ref` 参数 (L633): 默认 True 保持向后兼容，仅 `abandon_without_external_job_ref` 测试使用 False。

三个 helper 均为测试内部函数，无生产影响。

## 未发现新增 Finding

复审未发现 fix 引入的 correctness、architecture、test regression、contract leakage 或 scope violation。

## Residual Risk

- 现有 3 个 edgar deprecation warnings 是第三方库问题，非本 slice 引入。
- `ValueError` 捕获在 poll_wait 的 except 分支无法区分 corrupt evidence 与 adapter internal invariant error，但该风险在 S5 original review（DS F1）中已记录，不属 fix 引入。
