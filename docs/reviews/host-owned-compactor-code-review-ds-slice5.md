# Host-owned compactor Slice 5 code review artifact (independent second reviewer)

## Gate / work unit

- Gate: parallel code review for implementation Slice 5
- Work unit: Host-owned LLM context compactor public opener contract
- Review target: current uncommitted diff after accepted slice commit `7c2e7bd`
- Approved plan: `docs/host/host-owned-compactor-plan.md` Slice 5
- Design source of truth: `docs/host/design.md`
- Implementation artifact: `docs/reviews/host-owned-compactor-implementation-slice5-codex.md`
- Role: independent second reviewer; not controller; no file modification/gate advance

## Review methodology

逐一对照 review criteria 逐项检查 diff 与实际文件内容，每条 criteria 给出证据（文件路径 + 行号或 diff 片段）。不信任实现 artifact 的自述结论，所有结论必须有直接文件证据。

---

## Criteria 1: Manual smoke 和 public compact smoke 不得实现或注入 ContextCompactor

**结论：通过。**

证据：

- `utils/smoke_host_public_multiturn.py`：全文搜索 `ContextCompactor`，零命中。原 `DeepSeekContextCompactor(ContextCompactor)` 类（原第 629 行起，约 119 行）已完全删除。
- `tests/host/test_public_compact_smoke.py`：全文搜索 `ContextCompactor`，零命中。原 `_RealLLMContextCompactor(ContextCompactor)` 类（原第 120 行起，约 115 行）已完全删除。
- 两文件均不再 import `dayu.host.compaction` 下的任何 compaction 类型（`ContextCompactor`、`CompactionRequest`、`CompactionCandidate`、`EpisodeSummaryCandidate`、`PinnedStatePatchCandidate`、`PinnedPatchOperation`、`PinnedTextFieldPatch`、`PinnedStringTupleFieldPatch`、`PreservationEvidence`、`CompactInputRange` 等），diff 中 import 块已确认清理干净。

## Criteria 2: 无 DeepSeekContextCompactor / _RealLLMContextCompactor / compactor prompt / candidate mapper / thread wrapper 作为 Service-side compactor pattern 残留

**结论：通过。**

证据：

- `utils/smoke_host_public_multiturn.py`：已删除的所有类与函数：
  - `_NeverCancelledToken`（原约 18 行）
  - `_CompactorRejectingToolExecutor`（原约 22 行）
  - `DeepSeekContextCompactor`（原约 119 行，含 `compact()`、`_run_summary()` 线程包装、`_run_summary_async()` prompt 构造与 `run_agent_and_wait` 调用）
  - `_candidate_from_summary()`（原约 65 行，compaction candidate mapper）
  - `_preservation_evidence()`（原约 16 行）
  - `_range_for_request()`（原约 15 行）
  - `_summarized_ranges()`（原约 12 行）
  - `_confirmed_fact_summaries()`（原约 9 行）
- `tests/host/test_public_compact_smoke.py`：已删除的所有类与函数：
  - `_NeverCancelledToken`（原约 18 行）
  - `_RejectingToolExecutor`（原约 22 行）
  - `_RealLLMContextCompactor`（原约 115 行，与 manual smoke 同等结构）
  - `_candidate_from_summary()`（原约 60 行）
  - `_preservation_evidence()`（原约 16 行）
  - `_range_for_request()`（原约 15 行）
  - `_summarized_ranges()`（原约 12 行）
  - `_confirmed_fact_summaries()`（原约 7 行）
- 两文件中均无 `asyncio.run(` 或 `threading.Thread` 的 compactor 线程包装残留。
- 两文件中均无 compactor system/user prompt 构造残留。

## Criteria 3: Ordinary DeepSeek runner spec/options helpers 保留用于 normal run execution

**结论：通过。**

证据：

- `utils/smoke_host_public_multiturn.py:375-401`：`_deepseek_runner_spec(api_key)` 函数完整保留，用于构造 ordinary runner 和 compactor runner 的 `RunnerSpec`。
  - 第 290 行：`runner_spec = _deepseek_runner_spec(api_key)` 用于 ordinary run baseline。
  - 第 291 行：`compactor_runner_spec = _deepseek_runner_spec(api_key)` 用于 compactor runner baseline。
- `RunnerCallOptions` 构造（第 292-297 行）保留并同时用于 ordinary run 和 compactor runner。
- 删除的 import 不含 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy` —— 这些仍被 ordinary run baseline 使用。

## Criteria 4: OpenHostOptions 使用 compactor_runner_baseline=CompactorRunnerBaseline(...) 仅含 runner spec/options/artifact root/create-parent-dir

**结论：通过。**

证据：

- `utils/smoke_host_public_multiturn.py:339-344`：
  ```python
  compactor_runner_baseline=CompactorRunnerBaseline(
      compactor_runner_spec=compactor_runner_spec,
      compactor_runner_options=runner_options,
      compact_artifact_root=work_dir / "compact-artifacts",
      compact_artifact_create_parent_dirs=True,
  ),
  ```
- `tests/host/test_public_compact_smoke.py:91-96`：
  ```python
  compactor_runner_baseline=CompactorRunnerBaseline(
      compactor_runner_spec=compactor_runner_spec,
      compactor_runner_options=runner_options,
      compact_artifact_root=compact_artifact_root,
      compact_artifact_create_parent_dirs=True,
  ),
  ```
- `CompactorRunnerBaseline` 定义于 `dayu/host/api.py:921`，四个字段均为：`compactor_runner_spec: RunnerSpec`、`compactor_runner_options: RunnerCallOptions`、`compact_artifact_root: pathlib.Path`、`compact_artifact_create_parent_dirs: bool`。不存在 `context_compactor`、`compactor_policy_ref`、`prompt`、`candidate_mapper` 等泄漏字段。
- 两文件均不再 import `CompactorExecutionBaseline`（已从 `dayu/host/__init__.py` 包根导出中移除）。

## Criteria 5: Smoke stdout 不输出 compactor call_count/last_summary 及敏感 API key/header/full prompt/provider payload

**结论：通过。**

证据：

- `utils/smoke_host_public_multiturn.py` 的 `_print_compact_summary()` (第 661-676 行)：
  - 删除了 `SMOKE COMPACT_CALL_COUNT` 和 `SMOKE COMPACT_LAST_SUMMARY` 打印行。
  - 函数签名从 `(work_dir, compactor)` 改为 `(work_dir)`，不再接收 compactor 实例。
  - 仅输出：`SMOKE COMPACT_ARTIFACT_ROOT`、`SMOKE COMPACT_ARTIFACT_FILE_COUNT`、`SMOKE COMPACT_ARTIFACT`（有界，最多 `_COMPACT_ARTIFACT_PRINT_LIMIT=10` 条）。
- stdout 中不打印 `RunnerSpec` 对象、`headers`、`Authorization` header 或 API key 明文。
- 需注意的风险（非阻塞）：`_deepseek_runner_spec(api_key)` 将 API key 明文写入 `RunnerSpec.headers["Authorization"]`。虽然 smoke 脚本自身 stdout 不打印该字段，但如果 Host/Engine 层日志或异常消息意外序列化 `RunnerSpec`，则存在泄漏风险。这是**已存在于 Slice 5 之前**的模式（ordinary runner 同样使用此模式），且不属于本 Slice 引入的回归。建议在 Slice 6 或后续 slice 中将 API key 管理收口到 Engine/env 层，RunnerSpec 只保留 `api_key_ref` 环境变量名。

## Criteria 6: Public compact smoke 使用 public/observable 证据；internal event check 不作为 primary correctness signal

**结论：通过。**

证据——`tests/host/test_public_compact_smoke.py` 的断言顺序与性质：

1. **终端成功**（public）：
   - 第 131 行：`assert first_terminal.kind is HostEventKind.SUCCEEDED`
   - 第 132 行：`assert second_terminal.kind is HostEventKind.SUCCEEDED`
   - 通过 `next_terminal_for_run()` 从 public `watch_session_events()` iterator 读取。

2. **session/run 对齐**（public）：
   - 第 133-136 行：`session_id` 与 `run_id` 对齐验证，全部来自 public `HostEvent` 字段和 `host.submit_followup()` 返回值。

3. **continuity 非空**（public）：
   - 第 137-138 行：`second_terminal.final_answer` 非 None 且内容非空。

4. **compact artifact root 新增 artifact**（public/observable）：
   - 第 139-143 行：通过文件系统对比 `artifact_files_before` 与 `artifact_files_after`，验证 run window 内产生了新文件。

5. **artifact 内容与 run 匹配**（public/observable）：
   - 第 144 行：`_compact_artifact_for_run(new_artifacts, compacted.accepted_run_id)` 按 `llm-compact:{run_id}` candidate ID 定位 artifact。
   - 第 145-151 行：验证 artifact 的 `input_snapshot_refs` 包含非空 `current_user_input_ref`。

测试中不存在 `compactor.call_count`、`compactor.last_summary`、`CONTEXT_COMPACTED` event 计数或任何 internal event check 作为 primary correctness signal。所有主断言走 public `watch_session_events()`、`HostEvent`、`host.submit_followup()` 返回值或文件系统 observable artifact。

## Criteria 7: Provider skip 保持 env-gated；默认无网络 pytest

**结论：通过。**

证据：

- `tests/host/test_public_compact_smoke.py:55`：`api_key = api_key_or_skip(case)` —— 若 provider 对应环境变量缺失，`pytest.skip`。
- 第 114 行：`skip_if_provider_terminal_failed(case, first_terminal)` —— provider 不可用/quota/rate-limit 时精确 skip。
- 第 126-128 行：`except RuntimeError as exc: skip_if_provider_exception(case, exc); raise` —— 异常也走精确 skip。
- 所有 skip helper 来自 `tests/host/public_smoke_support.py`，实现精确匹配：network failure markers、503/unavailable markers、429/rate-limit markers。
- 默认无 `DEEPSEEK_API_KEY` 时，pytest 直接 skip，不发起网络请求。

## Criteria 8: 无 Host core/README overstep

**结论：通过。**

证据：

- 实现 artifact 第 49-51 行声明"README files were not edited"。
- diff 仅含两个文件：`utils/smoke_host_public_multiturn.py` 和 `tests/host/test_public_compact_smoke.py`。
- `tests/host/public_smoke_support.py` 仅被检查，未修改。
- 无 `dayu/host/` 下任何 `.py` 文件修改。
- 无 `README.md` 或 `dayu/host/README.md` 修改。

---

## 额外发现（非阻塞）

### F1: `_COMPACT_ARTIFACT_KIND` 与 Host 内部定义重复

`tests/host/test_public_compact_smoke.py:35-36` 定义：
```python
_COMPACT_ARTIFACT_KIND_FIELD = "artifact_kind"
_COMPACT_ARTIFACT_KIND = "context_compaction"
```

这复制了 Host 内部的 artifact kind 常量。若 Host 端修改 `artifact_kind` 值，测试会静默失败（找不到 artifact）。这是一个已知的知识耦合风险，不属于 Slice 5 引入的问题——Slice 5 之前测试直接实现 `_RealLLMContextCompactor` 同样依赖 Host internal 结构。

### F2: `llm-compact:{run_id}` candidate ID 格式依赖

`tests/host/test_public_compact_smoke.py:178` 硬编码 `expected_candidate_id = f"llm-compact:{run_id}"`。这是 Host-owned `LLMContextCompactor` 内部 candidate ID 命名约定的知识依赖。若 Host 修改命名规则，测试需要同步更新。

### F3: `public_smoke_support.py` 残留 "slice6" 引用

`tests/host/public_smoke_support.py` 中仍有 `"slice6-public-smoke"` (lane name, 第 859 行)、`"slice6-mock-tool"` (source_id, 第 1193 行)、`"Slice 6"` (module docstring 第 1 行) 等旧 slice 编号。该文件不在本 Slice 修改范围内，但与其他 smoke 文件产生 slice 编号不一致。

### F4: API key 在 RunnerSpec.headers 中的生命周期

`utils/smoke_host_public_multiturn.py:375-401` 的 `_deepseek_runner_spec(api_key)` 和 `tests/host/public_smoke_support.py:800-817` 的 `runner_spec_for_case(case, api_key)` 都将 API key 明文写入 `RunnerSpec.headers["Authorization"]`。当前 smoke stdout 不打印这些信息，但若 Engine/Host 层日志意外序列化 RunnerSpec，存在泄漏风险。这是跨 slice 的已知模式（非本 Slice 引入），建议在后续 work unit 中收口。

---

## 结论

**判定：PASS**

所有 8 条 review criteria 均通过，无阻塞性发现。Slice 5 smoke 迁移完整移除了 Service-side compactor 实现模式，正确迁移到 `CompactorRunnerBaseline` public contract，smoke stdout 不再泄漏 compactor 内部状态，public compact smoke 使用 public/observable 证据作为 correctness signal。

### 残余风险

| 风险 | 严重性 | Owner |
|------|--------|-------|
| `_COMPACT_ARTIFACT_KIND` 与 Host 内部常量重复 | 低 | Slice 6 或后续 smoke 维护 |
| `llm-compact:{run_id}` candidate ID 格式硬编码 | 低 | Host candidate ID contract 变更时需同步 |
| `public_smoke_support.py` slice 编号残留 "slice6" | 低 | Slice 6 或独立清理 PR |
| API key 在 RunnerSpec.headers 中的生命周期 | 中 | 跨 slice 的 API key 管理收口 |

### 未覆盖项

- 真实 provider 行为仍依赖外部 API key 环境变量；无 API key 时测试被 skip。
- Slice 6 的 README 同步尚未执行，文档仍可能描述旧 compactor 注入模式。
- 未对 Host core compaction operation 做回归验证——该范围属于 Slice 4，非本 smoke-only slice 范围。
