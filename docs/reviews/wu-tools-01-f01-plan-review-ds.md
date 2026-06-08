# WU-TOOLS-01-F01 Plan Review Artifact

## Gate Metadata

- **Gate**: plan review
- **Work unit**: `WU-TOOLS-01-F01 Shared Fins Ingestion Runtime And Download / Preprocess Awaiting Tools`
- **Reviewed artifact**: `docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md`
- **Review artifact**: `docs/reviews/wu-tools-01-f01-plan-review-ds.md`
- **Reviewer**: planreview skill (deepseek-v4-pro)
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control source**: `docs/host/issues-implementation-control.md`
- **Scope guard**: review only; do not modify plan, code, control doc; do not commit/push/PR

## Validation Run

只读核查命令与结果：

```text
$ git branch --show-current
host-wu-tools-01-f01

$ git status --short
(clean)

$ ls dayu/fins/ingestion* 2>&1
No such file or directory
→ 确认：当前仓库无 ingestion_runtime.py，plan S1-S3 为全新实现。

$ ls dayu/cli 2>&1
ls: dayu/cli: No such file or directory
→ 确认：当前仓库无 dayu/cli 包，plan CLI boundary 决策有效。

$ python -c "import ast; ..."  # 核查 dayu/runtime/__init__.py imports
from __future__ import annotations
→ 确认：dayu.runtime 无任何 dayu.fins import，plan 架构边界承诺可验证。

$ grep -r "class.*Download\|class.*download\|def.*download\|def.*preprocess" dayu/fins/ --include="*.py" -l
dayu/fins/storage/repository_protocols.py
dayu/fins/storage/fs_filing_maintenance_repository.py
dayu/fins/storage/_fs_storage_infra.py
dayu/fins/storage/_fs_maintenance_core.py
→ 确认：dayu.fins 下没有 download/preprocess 业务实现，只有 storage 基础设施。
  plan S3 的 "NEW source-specific downloader 缺失" 判断成立。

$ grep "try_normalize_ticker\|normalize_ticker" dayu/fins/tools/service.py
from dayu.fins.ticker_normalization import try_normalize_ticker
normalized_source = try_normalize_ticker(normalized_ticker)
→ 确认：当前 read path 通过 try_normalize_ticker 调用 ticker normalization 真源。

$ grep "try_normalize_ticker\|normalize_ticker" dayu/fins/storage/_fs_storage_utils.py
from dayu.fins.ticker_normalization import try_normalize_ticker
normalized_source = try_normalize_ticker(ticker)
→ 确认：storage 层也通过 try_normalize_ticker 归一化 ticker。

$ grep "awaiting_accept_port\|wait_adapter_registry" dayu/host/tool_runtime.py -c5
→ 确认：ToolRuntime 在 awaiting_accept_port 或 wait_adapter_registry 为 None 时
  返回 _awaiting_configuration_failure()（reason="awaiting_adapter_not_configured"）。
  plan S5 的 wiring 必要性被代码证据直接支撑。

$ grep "wait_adapter_registry=None" dayu/service/host_assembly.py
        wait_adapter_registry=None,
→ 确认：host_assembly._tooling_options_from_discovery 当前硬编码
  wait_adapter_registry=None。plan S5 的 assembly wiring 变更点准确。
```

## Overall Verdict

**PASS WITH FINDINGS** — plan 可通过，但需要 Controller 对 5 个 finding 做出裁决后才能进入 implementation gate。

Plan 正确识别了根因（缺失 shared Fins ingestion runtime 而非 tool name 缺失），严格对齐 Host/Engine design，切片粒度适合 code generation，每 slice 有明确的 stop condition。发现的问题都是可修复的设计精化，不构成架构级 blocker。

---

## Findings

### Finding F01 — Provider 各自实例化 DefaultFinsRuntime 导致的运行时共享语义不清晰

**Severity**: MEDIUM
**Type**: design-gap
**Verdict needed**: accepted / rejected-with-reason / needs-more-evidence

**Evidence**:

Plan §Implementation Decisions "Shared runtime ownership" 声明：
> Tool providers receive only provider config, construct/get the shared runtime, then adapt runtime operations into `ToolDefinition` callables.

Plan S4 "Functions/classes/types/call paths" 显示：
> `download_provider.discover_tools(spec)` -> parse explicit absolute `workspace_root` -> `DefaultFinsRuntime.create(...)` -> `runtime.get_ingestion_runtime()`

`dayu/fins/service_runtime.py:58-88` 中 `DefaultFinsRuntime.create()` 每次调用都会执行 `build_fs_repository_set(workspace_root=workspace_root)` 并新建全部仓储实例。

**问题**：

如果 read provider、download provider、preprocess provider 三个独立 provider callable 各自调用 `DefaultFinsRuntime.create(...)`，会产生三份独立的：
- storage repository 实例
- processor registry（`build_fins_processor_registry()`）
- `FinsIngestionRuntime`（含 job store）

这可能导致：
1. 三个独立 job store 实例如果使用相同文件路径，会有并发写入冲突。
2. 三份 processor registry 浪费内存。
3. plan 说 "shared runtime" 但 providers 之间没有实际的 runtime 实例共享机制。

**建议修正**：

在 S1 中明确 runtime 共享策略。两个可行方案：
- (A) 在 `dayu.fins` 中提供一个模块级 singleton/memoized factory，让多次 `create()` 返回同一实例。
- (B) 在 S4 中让 download/preprocess provider 接收一个可选的外部 runtime 参数，由 Service assembly 层统一创建并注入。

方案 (B) 更符合当前架构（Service 负责装配），但需要修改 provider 签名约定。

**Why blocks**: 如果三个 provider 各自持有独立 job store 实例操作同一文件路径，会导致 job 状态不一致，poll adapter 可能读到过期数据。这是 correctness 风险。

**Why doesn't block**: 如果 job store 实现使用文件锁（如 fcntl），三个实例可以安全并发。plan 没有明确 job store 的并发语义。

---

### Finding F02 — S3 download runtime 的 "source-specific download adapter" 范围缺失，stop condition 触发条件不够精确

**Severity**: MEDIUM
**Type**: scope-clarity
**Verdict needed**: accepted / rejected-with-reason / deferred-with-owner

**Evidence**:

Plan S3 stop condition：
> Stop and request user decision if completing "download" is interpreted as rebuilding full SEC/CN/HK downloader breadth from scratch inside F01. Current repo evidence does not contain those NEW source-specific download implementations.

Plan §Risks / Open Questions "Requiring user decision"：
> If "download" must mean full real SEC/CN/HK network downloader parity in F01, current repo evidence shows that source-specific NEW implementation is absent. That scope is likely too broad for a single reviewable F01 unless user approves expanding F01 or supplies the OLD ingestion source to wrap. The default plan treats source-specific breadth as adapter implementation within S3 only to the extent it can be implemented without rebuilding an entire CLI/UI download surface.

代码核查确认：当前 `dayu/fins/` 下无任何 download 业务实现（见 Validation Run）。

**问题**：

1. Plan 说 S3 应该实现 `start_download` 并路由到 "source-specific download adapter"，但 adapter 本身不在 scope 内。那 S3 预期产出什么？只有 routing skeleton 和 fake adapter？
2. Stop condition 的语言 ("如果被解释为...") 是被动语态，没有给 S3 一个确定的 completion 定义。实现 agent 无法从 plan 判断何时 S3 算完成。
3. "default plan treats source-specific breadth as adapter implementation within S3 only to the extent it can be implemented" — "to the extent it can be implemented" 是模糊语言。

**建议修正**：

S3 completion signal 应改为具体验收条件，例如：
> S3 completion: `FinsIngestionRuntime.start_download()` 可以接受 typed download request，通过注入的 fake/mock download adapter 写入 source repository，job terminal state 可被 poll adapter 读取。S3 不要求任何真实网络 download adapter；real SEC/CN/HK adapter 作为 future work unit（建议 `WU-TOOLS-01-F01-S3-adapters` 或归入 CI pipeline work units）。

同时在 S3 "Non-goals" 中增加：
> - No real SEC/CN/HK network download adapter implementation.

**Why blocks**: 如果实现 agent 把 S3 理解为"需要实现真实 SEC downloader"，scope 会膨胀到不可控。但如果 agent 只实现 fake adapter，S3 有明确的闭环。

**Why doesn't block**: plan 的 stop condition 已经提示了这个问题，Controller 可以在 implementation gate 前做出裁决。

---

### Finding F03 — S5 Service assembly wiring 缺少 provider 检测机制的设计约定

**Severity**: LOW
**Type**: design-gap
**Verdict needed**: accepted / rejected-with-reason

**Evidence**:

Plan S5 "Exact allowed changes"：
> Update Service host assembly to pass `wait_adapter_registry` into `HostToolingOptions` when Fins awaiting providers are enabled.

`dayu/service/host_assembly.py:1024-1050` 中 `_tooling_options_from_discovery` 当前接收的是 `tool_bundle`、`source_refs` 和 `duplicate_governance_policy_config`，不感知 provider 身份。

**问题**：

Plan 没有说明 Service 层如何"检测"哪些 provider 是 Fins awaiting providers。`ToolsDiscovery` 返回的是 opaque `ToolBundle` + `provider_reports`，provider identity 存在于 diagnostic report 字符串中，不适合做程序化判断。

可能的方案：
- (A) 在 `ToolDiscoveryProviderConfig.config` 中约定一个 key（如 `"awaiting_enabled": true`），Service 层读取该 key。
- (B) 每个 provider 在 `ToolsDiscoveryProviderOutput` 中声明自己是否产生 awaiting tools。
- (C) Service 层硬编码已知 provider id 列表（如 `"financial-tools-download"`）。

方案 (A) 最小侵入，方案 (B) 更干净但需要改 `ToolsDiscoveryProviderOutput`（plan 说禁止此变更）。方案 (C) 是脆弱的 magic list。

**建议修正**：

在 S5 中明确约定检测机制。推荐：在 provider config JSON 中使用 `"is_awaiting_provider": true` 标记，Service assembly 读取该标记来决定是否构建 wait adapter registry。同时在 plan §Contract / Schema / Public-interface Changes 中说明此约定。

**Why blocks**: 不阻塞。即使没有约定，实现 agent 在 S5 可以自然发现这个问题并选择合理方案，只要不改变 public contract。

**Why doesn't block**: 这是 implementation detail，不是架构级决策。

---

### Finding F04 — Fins job store 文件路径未在 plan 中指定，可能导致 provider 间 job store 路径冲突

**Severity**: LOW
**Type**: missing-detail
**Verdict needed**: accepted / rejected-with-reason

**Evidence**:

Plan S1 "Exact allowed changes"：
> Add Fins job store interface and filesystem implementation for job records only.

Plan §Implementation Decisions "Storage boundary"：
> The Fins job store may use runtime-owned files because job governance state is not financial document content; it must not store source document payloads or processed payloads.

**问题**：

Plan 没有指定 job store 文件路径。如果默认放在 `workspace_root` 下（如 `workspace_root/.fins_jobs/`），那三个 provider 用同一个 `workspace_root` 没有问题。但如果放在某个相对于模块的位置，可能产生冲突。

这个缺失不会阻塞实现——实现 agent 自然会选一个合理路径——但 plan 应该有这个约定以便 review 时验证。

**建议修正**：

在 S1 "Data flow/state transitions/error handling/invariants" 中增加：
> Job store 文件路径由 `DefaultFinsRuntime` 通过 `workspace_root` 派生（如 `workspace_root / ".fins" / "jobs"`），保证同一 workspace 下所有 provider 共享同一 job store。

**Why blocks**: 不阻塞，实现 agent 可以自行决定路径。

---

### Finding F05 — S6 中 `include_ingestion_tools` 移除后，read provider 的 config shape 变更缺少 fail-safe 迁移说明

**Severity**: LOW
**Type**: compatibility
**Verdict needed**: accepted / rejected-with-reason

**Evidence**:

Plan S4 "Exact allowed changes"：
> Remove target reliance on `include_ingestion_tools`; after implementation, the old fail-closed test must be replaced with independent provider discovery tests.

Plan S6：
> Update tests that currently assert `include_ingestion_tools` is false.

`dayu/fins/tools/provider.py:34` 中 `_CONFIG_INCLUDE_INGESTION_TOOLS_FIELD = "include_ingestion_tools"`，当前行为是 `include_ingestion_tools=true` 时抛 `ValueError`（fail-closed）。

**问题**：

如果 workspace overlay 中已有用户配置了 `include_ingestion_tools: true`（虽然目前 fail-closed），移除该字段后：
- 如果直接删除字段解析，旧 config 中的该字段会被忽略（silent ignore），不报错。这取决于是否认为 silent ignore 是可接受的。
- 如果保留字段解析但改为 no-op warning，需要决定 warning 级别。

Plan 没有说明移除方式：是删除字段解析代码，还是保留为 no-op。

**建议修正**：

在 S4 或 S6 中明确：`include_ingestion_tools` 字段解析代码完全删除（因为 download/preprocess 由独立 provider 承载，不再需要该开关）。用户无需迁移 workspace overlay，旧字段被 ConfigLoader 忽略不会导致错误。

**Why blocks**: 不阻塞，这是 minor 实现细节。

---

## Residual Risks

### Fixed in current slices (S1-S6)

| Risk | Resolution |
|------|-----------|
| `WU-TOOLS-01-S4-R1` | S1-S6 完成后关闭 |
| `include_ingestion_tools` fail-closed transition | S4/S6 完成 |
| Host awaiting adapter missing for Fins tools | S5 完成 |
| Read provider stability | S1 保持 `get_tool_service()` 行为不变 |

### Covered by later approved slice

| Risk | Slice | Notes |
|------|-------|-------|
| README/config synchronization | S6 | 已规划 |
| Deterministic no-network runtime/tool tests | S1-S5 | 已规划 |
| Provider 间 runtime 共享策略 | S1/S4 | Finding F01 — 需 Controller 裁决 |

### Assigned to later work unit

| Risk | Owner | Notes |
|------|-------|-------|
| Upload migration | `WU-TOOLS-01-F09` | plan 已明确 |
| SEC/Fins CI pipeline | `WU-TOOLS-01-F04/F05` | plan 已明确 |
| CN/HK Docling CI pipeline | `WU-TOOLS-01-F06/F07` | plan 已明确 |
| Real SEC/CN/HK network download adapter | Future work unit | Finding F02 — 需 Controller 裁决是否为 F01 的一部分 |
| Future CLI download/process | Future CLI/package work unit | plan 已明确 |
| `WU-TOOLS-01-S1-R1` | F04-F07 owners | plan 已明确 |
| `WU-TOOLS-01-S1-R2` | F08 owner | plan 已明确 |

### Tracked by existing issue

| Risk | Issue | Notes |
|------|-------|-------|
| CI coverage | Issues #121, #122 | plan 已明确 |

### Requiring user decision

| Risk | Decision needed | Related Finding |
|------|----------------|-----------------|
| S3 download adapter scope | S3 是否需要实现真实 SEC/CN/HK download adapter，还是只实现 fake adapter + routing skeleton | F02 |
| Provider runtime 共享机制 | 三个 provider 各自 `create()` 还是共享单例 | F01 |

---

## Architecture Boundary Verification

### Positive confirmations (plan 对齐设计真源)

1. **Fins runtime 不进入 dayu.runtime**: plan 明确 "Fins ingestion service/runtime lives under `dayu.fins`, not `dayu.runtime`"。代码核查确认 `dayu.runtime` 无任何 `dayu.fins` import。

2. **不改变 Host/Engine awaiting contracts**: plan "Non-goals" 明确列出不改变 `ToolAwaitSpec`、`ToolAwaitingOutcome`、`ResolveWaitRequest`、Host wait record schema、Engine suspend/resume semantics。

3. **财报存取只走 dayu.fins.storage**: plan "Storage boundary" 明确 "Source documents, blob files, processed documents... must use `dayu.fins.storage` repository protocols/implementations" 且 "No direct Path(...) glob or raw JSON writes"。

4. **Ticker normalization 唯一真源**: plan 明确 "All ticker / market normalization calls go through `dayu.fins.ticker_normalization` public API"。代码核查确认 current read path 和 storage 层都已经通过 `try_normalize_ticker` 调用真源。

5. **Service assembly 不改变 Host/Engine 契约**: plan S5 明确 "Keep `ToolsDiscovery` layer-neutral; do not add Fins imports to `dayu.runtime`"。

6. **Provider split 不引入兼容性 facade**: plan "Provider public interface target" 明确 "do not keep a mixed provider facade for compatibility"。

7. **不做通用 job 平台**: plan "Why This Is Not Over-designed" 明确 "It does not introduce a generic job platform; job state, executor and poll adapter are Fins-specific"。

8. **CLI boundary 正确**: plan 明确 "Current repo has no `dayu/cli` package. F01 must not restore CLI commands." 代码核查确认无 `dayu/cli` 目录。

### Concerns checked and cleared

1. **Plan 是否会让 Fins business runtime 泄漏到 Host/Engine**: 不会。Plan 通过 Fins wait adapter 作为 bridge，adapter 在 Fins 侧实现 `WaitPollAdapter` protocol（Host-owned contract），不改变 Host 内部逻辑。

2. **Plan 是否需要修改 `HostToolingOptions`**: 不需要。`HostToolingOptions.wait_adapter_registry` 已经是可选字段（`WaitAdapterRegistry | None = None`），plan 只需传入非 None 值即可。

3. **Plan 是否需要修改 `WaitAdapterBinding`**: 不需要。当前 `WaitAdapterBinding` 字段（tool_name, await_kind, adapter_key, resume_policy, external_job_ref_source）完全满足 Fins 需求。

4. **Plan 是否会创建 God runtime**: 不会。Plan 明确分离了 `FinsIngestionRuntime`（job 生命周期）、`DefaultFinsRuntime`（装配根）、tool providers（适配器）、poll adapter（Host bridge），职责清晰。

---

## Test Coverage Assessment

Plan 规划的测试文件：
- `tests/fins/test_fins_ingestion_runtime.py` — S1/S2/S3 runtime 测试
- `tests/fins/test_fins_ingestion_tools.py` — S4/S5 tool provider + awaiting 测试
- `tests/fins/test_fins_storage_provider.py` — 已有，S4/S6 需更新
- `tests/service/test_host_assembly.py` — S5 assembly wiring 测试
- `tests/host/test_phase7_waiting_integration.py` — S5 已有 Host 等待集成测试
- `tests/host/test_public_resolve_wait_resume.py` — S5 已有 Host resolve 测试

潜在测试缺口：
1. Plan 没有规划 Fins job store 并发测试（多个 provider 同时创建 job 时的一致性）。
2. Plan 没有规划 poll adapter 在 job store 文件损坏时的行为测试（虽然 plan 提到了 "corrupt job record maps to lost"）。
3. S3 如果只实现 fake adapter，download runtime 的测试覆盖只能是 happy path；真实网络错误路径需要在 real adapter work unit 中测试。

这些缺口不阻塞 plan，因为 plan 已经为每个 slice 指定了 expected assertions，覆盖了核心行为。

---

## Docs Decision Verification

Plan §Docs Decision 与计划修改一致：
- `dayu/fins/README.md`：应更新 ✓（implementation 改变 Fins provider/runtime 行为）
- `tests/README.md`：条件更新 ✓（如有新 fixture 约定）
- `dayu/config/README.md`：条件更新 ✓（如 config shape 变化）
- 根 `README.md`：不更新 ✓（plan 不实现 CLI）
- `dayu/README.md`：不更新 ✓（plan 不改变包/层边界）

---

## Completion Report

- **Artifact path**: `docs/reviews/wu-tools-01-f01-plan-review-ds.md`
- **Overall verdict**: PASS WITH FINDINGS
- **Findings summary**:
  - F01 (MEDIUM): Provider 各自实例化 DefaultFinsRuntime 的共享语义不清晰
  - F02 (MEDIUM): S3 download adapter scope 的 stop condition 不够精确
  - F03 (LOW): S5 Service assembly 缺少 provider 检测机制约定
  - F04 (LOW): Job store 文件路径未指定
  - F05 (LOW): `include_ingestion_tools` 移除方式未说明
- **Blockers**: 无（所有 finding 为 design-gap/missing-detail/scope-clarity，非架构级 blocker）
- **Residual risks**: 2 项需用户决策（S3 download adapter scope、provider runtime 共享机制），其余已分配 owner
- **Validation run**: 6 条只读核查命令全部通过，证据记录在上方
