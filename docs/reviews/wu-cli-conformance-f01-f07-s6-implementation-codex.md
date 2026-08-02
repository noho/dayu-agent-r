# WU-CLI-CONFORMANCE-F01-F07 S6 Implementation

## 0. Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- PR：`190`
- Slice：`S6 / F06 — typed trigger 无 alias 重命名`
- Gate：`implementation`
- Entry HEAD：`64c581f1f03f51e2651f822a1b2dcfb775f16c94`
- Accepted plan：`docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md` §8
- Plan-fix：`docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md` §3.3
- Frozen finding：`F06-context-governance-trigger-name`
- Artifact path：`docs/reviews/wu-cli-conformance-f01-f07-s6-implementation-codex.md`
- 状态：`IMPLEMENTATION COMPLETE — next entry point: independent code review`

本轮按用户明确授权只完成 implementation、验证与本 artifact。未执行 code review、fix/re-review、stage、commit、push 或 PR 操作。

## 1. 动机与语义 owner 裁决

动机成立，且严重性评估准确。直接代码证明旧 runner-call trigger 同时由 accepted compact 和 failed compaction 后的 deterministic fallback dispatch 使用，因此把它命名为“compaction completed”会错误暗示 compact 成功。Frozen oracle 已明确要求 trigger 只表达 context governance 已收口并允许下一次 dispatch。

语义 owner 保持如下：

| 语义 | 唯一 owner | S6 处理 |
|---|---|---|
| runner-call trigger closed contract | `dayu/host/_runner_call_manifest.py` | closed allowlist 只接受 `context_governance_resolved`；旧值与未知值 fail closed。 |
| ordinary post-governance dispatch trigger 生产 | `dayu/host/run_input.py` | prepared candidate 与 durable record 两条 producer 都使用新 symbol。 |
| compact success / failure 精确 outcome | canonical `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` 与其 artifact / fallback refs | 不修改、不复制到 trigger，不从 trigger 反推。 |
| Engine ingest / Tool Trace 消费 | strict manifest/hot reader 与现有 generic projection | 生产代码无旧值分支，不修改；owner tests 证明只透传新值。 |

这是 fresh contract rename，不是兼容迁移。实现没有 alias、re-export、loose parser、migration、fallback 或下游补偿，也没有引入第二套 outcome owner。

## 2. Scope 与实际改动

实际修改严格限于 accepted S6 allowlist：

- `dayu/host/run_input.py`
  - 删除旧 trigger symbol，定义 `_RUNNER_CALL_TRIGGER_CONTEXT_GOVERNANCE_RESOLVED`。
  - `_prepared_candidate_kind_and_trigger(...)` 的 accepted compact / fallback candidate 分支使用新 symbol。
  - `_runner_call_kind_and_trigger(...)` 的 recovery / fallback manifest 分支使用新 symbol。
- `dayu/host/_runner_call_manifest.py`
  - strict `_RUNNER_CALL_TRIGGER_REASONS` 删除旧 literal，只加入 `context_governance_resolved`。
- `tests/host/test_engine_ingest_mapping.py`
  - success compact 与 failed fallback recovery manifest 均断言 hot/durable round-trip 新值。
  - generic Engine iteration link 使用新值。
  - strict hot/manifest reader 对旧值与未知值均 fail closed。
- `tests/host/test_run_input_builder.py`
  - accepted compact 与 active fallback 两个 producer 路径均断言 hot/durable manifest 新值。
- `tests/host/test_tool_trace_projection.py`
  - public Tool Trace 断言透传新值，并断言不生成 compaction outcome、artifact ref 或 fallback action。
- `docs/host/design.md`
  - active closed trigger 表改为新 literal，并明确 canonical terminal 与 artifact/fallback refs 继续拥有精确 outcome。

唯一新增文件是本 implementation artifact。未修改 Engine 生产代码、归档/frozen evidence、两个 frozen registry 或 README。

## 3. Contract 与不变量验证

### 3.1 Producer 与 round-trip

- successful compact 后的 recovery dispatch：hot payload 与 strict durable manifest 都是 `context_governance_resolved`。
- failed compaction 且 deterministic fallback 允许 dispatch：hot payload 与 strict durable manifest 都是 `context_governance_resolved`。
- prepared candidate producer 与 durable record producer 复用同一个新 module-level symbol。

### 3.2 Strict reader matrix

| 输入 | hot reader | manifest reader |
|---|---|---|
| `context_governance_resolved` | PASS | PASS |
| 旧 trigger literal（测试中由两个静态片段组成，避免 active 零残留扫描误命中） | `HostDurableError` | `HostDurableError` |
| `unknown_context_governance_trigger` | `HostDurableError` | `HostDurableError` |

没有 normalization、alias 或兼容接受路径。

### 3.3 Outcome ownership

- success 测试仍分别断言 `CONTEXT_COMPACTED` payload、accepted candidate 与 compact artifact identity。
- failure 测试仍分别断言 `CONTEXT_COMPACTION_FAILED` payload、`fallback_action=dispatch`、fallback policy/window/budget；并断言没有 `CONTEXT_COMPACTED`。
- Tool Trace 只复制 strict owner 校验后的 `runner_call_kind` 与 `runner_call_trigger_reason`，不从 trigger 生成 compaction outcome、artifact ref 或 fallback action。

因此 trigger 只回答“为何现在允许组装下一次 call”，没有夺取“compact 最终发生了什么”的精确事实所有权。

## 4. 验证结果

### 4.1 Focused pytest

计划命令：

```text
source .venv/bin/activate
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py -q
```

- 首轮：`2 failed, 273 passed`。失败原因是新增 strict-reader test 插入点位于原 Engine ingest test 最后两条断言之前，导致两条原断言被错误归入新 test 并引用未定义局部变量；生产 contract 没有失败。
- 修正测试边界后完整复跑：`275 passed in 2.90s`。
- coverage 模式下再次完整复跑：`275 passed in 3.87s`。

### 4.2 Pyright

Focused：

```text
python -m pyright dayu/host/run_input.py dayu/host/_runner_call_manifest.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py
```

结果：`0 errors, 0 warnings, 0 informations`。

Full：

```text
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

### 4.3 Production 单文件 coverage

```text
coverage erase
coverage run -m pytest tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py -q
coverage report --include='dayu/host/run_input.py,dayu/host/_runner_call_manifest.py' --show-missing --fail-under=80
```

| production file | coverage | threshold |
|---|---:|---:|
| `dayu/host/run_input.py` | `84%` | `>=80%` PASS |
| `dayu/host/_runner_call_manifest.py` | `88%` | `>=80%` PASS |

### 4.4 扫描、diff 与 frozen registry

- active old symbol/literal scan：`dayu/host`、`tests/host`、`docs/host/design.md` 零命中。
- new symbol/literal scan：覆盖两个 producer、strict allowlist、success/fallback/strict ingest tests、RunInput owner tests、Tool Trace public projection test 与 Host design。
- `git diff --check`：PASS，无诊断。
- 最终 unstaged changed-path allowlist：仅六个 approved existing files 加本 artifact；无其它路径。
- `git diff --cached --name-only`：空；未 stage。
- Frozen registry SHA-256 保持：
  - `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4  docs/cli_ci_oracles.json`
  - `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef  docs/cli_ci_scenarios.json`

## 5. Docs / README 决策

`docs/host/design.md` 是本 slice 的 active design owner，已同步新标识及 outcome owner 不变量。README 更新按 accepted plan 冻结到 S8，本轮没有修改任何 README。

## 6. Residual risks 与未覆盖项

- Frozen real-provider CLI evidence refresh：`covered by later approved slice S8`。本 slice 只完成 owner-level contract 与 repository validation，不伪报真实 provider scenario 已刷新。
- S7 fresh compaction schema / accept barrier：`covered by later approved slice S7`，本 slice 未修改其 schema、repair、Memory 或 terminal semantics。
- S6 当前 residual：无未分类 residual。旧 active identifier 漏改风险已由 strict reader matrix 与 active zero-hit scan 收口。

## 7. Completion signal

S6 implementation completion signal 已满足：active producer、strict persistence/reader、generic ingest、public projection、owner tests 与 design 只使用 `context_governance_resolved`；success/fallback manifest 均使用新 trigger；canonical terminal 与 artifact/fallback refs 的精确 outcome ownership 未改变；未出现 frozen oracle/design 冲突。

下一合法入口是独立 code review gate。本轮按用户要求在 implementation 完成后停止，不进入 review 或任何 Git/PR 写操作。
