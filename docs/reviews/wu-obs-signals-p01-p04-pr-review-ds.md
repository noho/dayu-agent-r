# WU-OBS-SIGNALS-01 Draft PR Review Gate — AgentDS

## Scope

- PR: [#137](https://github.com/noho/dayu-agent-r/pull/137)
- Branch: `phaseflow/wu-obs-signals-p01-p04`
- Base: `main`
- Work unit: `WU-OBS-SIGNALS-01` (combined P01/P02/P03/P04 signal contracts)
- Review mode: read-only, no code changes, no commits, no pushes, no GitHub comments
- Output: `docs/reviews/wu-obs-signals-p01-p04-pr-review-ds.md`

## Gate Checklist

### 1. PR diff 与本地分支一致性

**证据**:

- `gh pr diff 137 --name-only` → 56 files
- `git diff --name-only main..HEAD` → 56 files
- `diff /tmp/pr_files.txt /tmp/local_files.txt` → 无输出（完全一致）
- PR head commit `5c452c67` 与本地 HEAD `5c452c67` 一致
- PR commits 列表包含 `f3dbf81d`（aggregate deepreview acceptance）和 `5c452c67`（phaseflow bookkeeping）

**结论**: **PASS**。PR diff 与本地分支完全一致，head 包含所需两个关键 commit。

---

### 2. PR body 描述准确性

**证据**:

PR body Summary:
> - Adds Tool Trace prerequisite structured signals for WU-OBS-P01/P02/P03/P04: context pressure, tool timing, failure metadata, and provider protocol partial tool-call summaries.
> - Keeps signals additive/read-only and preserves Host-owned governance boundaries.
> - Adds query helper integration coverage and aggregate deepreview fix that centralizes shared signal contract constants/bounded text rules in dayu.host.tool_trace_signals.

逐项对照实现：
- **P01 context_pressure**: `_usage_context_pressure_signal`（`engine_ingest.py:4114-4173`）从 Host `BudgetEstimate` + `decide_context_budget` 构造，`_context_compaction_failed_pressure` 与 `_context_compaction_attempt_rejected_pressure`（`tool_trace.py:1228-1297`）从现有 compact payload 派生 → 与描述一致
- **P02 tool_timing**: `_tool_timing_from_meta`（`tool_runtime.py:6083-6110`）从 `ToolResultMeta` 的 `started_at`/`finished_at` 计算 duration_ms → 与描述一致
- **P03 failure_metadata**: `_failure_metadata_from_outcome`（`tool_runtime.py:6120-6172`）构造 3 种 tool-level kind + `engine_ingest.py:5950-5973` 构造 provider_protocol_error + `tool_trace.py:1299-1351` 派生 2 种 compaction kind → 完整 6 变体闭集 → 与描述一致
- **P04 partial_tool_call_signal**: `_provider_protocol_partial_tool_call_signal`（`engine_ingest.py:5978-6007`）序列化 Engine `PartialToolCallSummary` bounded 摘要，无 raw args 字段 → 与描述一致

PR body Residual Risk:
> WU-OBS-00 analyzer remains the downstream consumer and is tracked as pending-prerequisite under GitHub Issue #70. No new active residual risk from this PR.

在 `docs/host/issues-implementation-control.md` 中确认：
- `WU-OBS-00` status = `pending-prerequisite`
- `WU-OBS-00` owner = GitHub Issue #70

**结论**: **PASS**。PR body 准确描述 P01/P02/P03/P04 信号范围与 residual risk 归属。

---

### 3. PR 元数据

**证据**:

```
gh pr view 137 --json state,isDraft,baseRefName,headRefName,mergeable
→ state: OPEN, isDraft: true, baseRefName: main, headRefName: phaseflow/wu-obs-signals-p01-p04, mergeable: MERGEABLE
```

**结论**: **PASS**。PR 保持 draft/open，base 为 main，head 为正确分支。

---

### 4. PR-only 问题检查

#### 4a. 漏推文件

`diff /tmp/pr_files.txt /tmp/local_files.txt` → 无差异。所有本地改动均已推送至 PR。

**结论**: **PASS**。无漏推文件。

#### 4b. Artifact 缺失

PR diff 包含以下预期 artifact：

| Artifact | 状态 |
|---|---|
| `docs/host/wu-obs-signals-p01-p04-plan.md` | ✅ |
| `docs/reviews/wu-obs-signals-p01-p04-plan-review-*.md` | ✅（mimo/ds/controller-adjudication + fix + rereview） |
| `docs/reviews/wu-obs-signals-p01-p04-obs-sig-00-*.md` | ✅（implementation + code-review mimo/ds） |
| `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-*.md` | ✅（implementation + review mimo/ds + controller + fix + rereview mimo/ds + controller） |
| `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-*.md` | ✅（同上完整链） |
| `docs/reviews/wu-obs-signals-p01-p04-obs-sig-03-*.md` | ✅（implementation + review mimo/ds + controller） |
| `docs/reviews/wu-obs-signals-p01-p04-obs-sig-04-*.md` | ✅（implementation + review mimo/ds + controller） |
| `docs/reviews/wu-obs-signals-p01-p04-obs-sig-05-*.md` | ✅（integration + controller） |
| `docs/reviews/wu-obs-signals-p01-p04-aggregate-deepreview-*.md` | ✅（mimo/ds + controller + fix + rereview mimo/ds + controller） |

所有 slice（OBS-SIG-00 至 OBS-SIG-05）的 implementation → review → controller adjudication → (fix → rereview) 链完整，aggregate deepreview 链完整。无缺失。

**结论**: **PASS**。Artifact 完整。

#### 4c. 总控状态与 PR 状态一致性

`docs/host/issues-implementation-control.md`:
- gate: `ready-to-open-draft-PR` → 与 PR 当前 draft 状态一致
- active work unit: `WU-OBS-SIGNALS-01`
- WU-OBS-SIGNALS-01 行包含完整 slice commit 列表与 artifact 追溯
- WU-PROJ-01 status 已从 `draft-PR-pass` 更新为 `completed`，记录了 PR #136 merge closeout
- WU-OBS-P01/P02/P03/P04 已标记为 `merged-into` WU-OBS-SIGNALS-01

**结论**: **PASS**。总控状态与 PR 状态一致。

#### 4d. 验证记录可信度

PR body claims:
> `python -m pytest ...` → 160 passed
> `pyright` → 0 errors, 0 warnings, 0 informations
> `git diff --check` → OK

独立复验结果：
```text
source .venv/bin/activate && python -m pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_phase6_toolruntime_integration.py -q
→ 160 passed in 1.19s

source .venv/bin/activate && pyright
→ 0 errors, 0 warnings, 0 informations
```

与 PR body 声称完全一致。

**结论**: **PASS**。验证记录可信。

#### 4e. README 触发遗漏

CLAUDE.md 触发规则：
- `dayu/host/` 修改 → 检查 `dayu/host/README.md`

实际: `dayu/host/README.md:353` 已更新 tool trace 描述，增加"并投影 context pressure、tool timing、failure metadata 等只读结构化 signal"。准确反映变更范围。

- `tests/` 修改 → 检查 `tests/README.md`

实际: `tests/README.md:164` 已更新 Tool Trace 测试覆盖描述，增加"context pressure / tool timing / failure metadata 结构化 signal"。

未触发 `dayu/engine/`、`dayu/fins/`、`dayu/config/` README 更新。

**结论**: **PASS**。README 更新触发合规，无遗漏。

---

### 5. Correctness / Architecture / LLM-Facing Semantic / Layering / Pyright-Test 风险

#### 5a. Architecture (架构硬约束)

- **分层**: `dayu/host/tool_trace_signals.py` 位于 `dayu/host/` 包下，属于 Host 层内部模块。不进入 `dayu/runtime`。✅
- **依赖方向**: `dayu/host/tool_trace_signals` 只 import 标准库（`hashlib`, `dataclasses`）。所有消费者（`tool_runtime.py`, `tool_trace.py`, `engine_ingest.py`）均为 Host 层模块。无 Host→Engine 反向依赖。✅
- **工具层验证**: `grep -rn 'tool_trace_signals' dayu/runtime/` → 无结果。`dayu.runtime` 不引用此模块。✅
- **Signal 治理**: 四类 signal 均为 additive payload 字段，不修改 Run/Attempt 状态机、ToolRuntime accept/governance/execution 语义、memory projection 或 recovery 路径。已通过现有测试（33 + 33 + 33 + 61 + 30 + 3 = 各文件独立分布）验证向后兼容。✅
- **Schema**: SQLite `host_tool_trace_hot` 表 schema 未变，signal 全部存储在现有 `trace_summary_json` TEXT 列。✅

**结论**: **PASS**。

#### 5b. LLM-Facing Semantic (Agent 语义约束)

审查对象：四类 signal 的字段名、含义与 bounded text 规则。

- **字段命名**: `context_pressure`、`tool_timing`、`failure_metadata`、`partial_tool_call_signal` 均为业务可读名称，不包含内部模块名、代码类型名或 Host 实现术语。
- **Self-describing schema**: 每个 signal 包含 `schema_version`（整数）和 `signal_source`（事件类型字符串），使下游 analyzer 无需依赖外部上下文即可判断信号来源与版本。
- **Bounded text**: `failure_metadata` 中的 `repair_hint`、`cancel_message`、`cancel_hint` 使用 `value` + `sha256_digest` + `truncated` 三字段组合，既提供 LLM 可直接消费的有界文本，又保留完整原文的校验能力。bounded 上限（512 chars）由 `TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS` 集中定义。
- **Diagnostic refs**: `diagnostic_refs` 为文本数组，不裸穿 `event_id` 或 `payload_ref` 给模型。
- **Partial tool-call**: 只暴露 `tool_call_index`、`tool_call_id`、`name_fragment`、`arguments_byte_size`、`arguments_sha256`、`arguments_present` — 无 raw arguments 字段、无 raw payload 字段、无 stream 字段。

**潜在风险**: 无。所有 signal 字段均为自解释业务语义，满足 Agent 语义约束。

**结论**: **PASS**。

#### 5c. Layering (层级依赖)

- `engine_ingest.py:52`: `from dayu.engine.contracts.partial_tool_call import PartialToolCallSummary` — Host→Engine 单向消费，符合分层。
- `engine_ingest.py:95-104`: 消费 `BudgetEstimate`、`decide_context_budget` 等 Host 层 context_budget 类型 — 同层引用，正确。
- `tool_runtime.py:119`: 消费 `dayu.host.tool_trace_signals` — 同层引用。
- `tool_trace.py:46`: 消费 `dayu.host.tool_trace_signals` — 同层引用。
- 无 Engine→Host、runtime→Host 反向 import。
- `_usage_observation_diagnostic` 签名变更（移除未使用的 `transaction` 参数）为内部私有方法重构，唯一调用点 `engine_ingest.py:2676` 已相应更新。

**结论**: **PASS**。

#### 5d. Correctness

- **P01 context_pressure 来源**: 只来自 Host `BudgetEstimate`（`input_budget_tokens`, `soft_threshold_tokens`, `hard_threshold_tokens`）+ `decide_context_budget` + Engine `UsageReportedData`。`estimate is None` 时所有 budget 字段为 `None`，`budget_decision` 为 `"unknown"`。阈值比较使用 `>=`（at-threshold 算 exceeded）。✅
- **P02 tool_timing 来源**: 只来自 `ToolResultMeta.started_at` / `.finished_at`。`meta is None` 时返回 `status="missing_tool_result_meta"`，所有时间字段为 null。duration 使用 `// _ONE_MILLISECOND` 整数除法。✅
- **P03 failure_metadata**: 完整 6 变体闭集（tool_failed, tool_cancelled, policy_blocked, provider_protocol_error, context_compaction_attempt_rejected, context_compaction_failed）。completed 结果正确互斥（`failure_metadata=None`）。bounded text 规则：null → (None, None, False)；non-null → (bounded[0:512], `sha256:...`, truncated=len>512)。✅
- **P04 partial_tool_call_signal**: 只序列化 `PartialToolCallSummary` 的 6 个 bounded 字段，无 raw args。`arguments_sha256` 为 Engine 预计算的 bare 64-char hex（不带 `sha256:` 前缀），由 `_is_bare_sha256_hex` 校验。投影层校验 `partial_tool_call_count`、`summary_status` 与 `partial_tool_calls` 数组长度的一致性。✅
- **hot/cold 等价**: `_trace_summary` 统一构造 hot summary JSON，`_write_cold_trace` 写入同一 summary 到 cold JSONL。测试 `test_tool_trace_copies_optional_summary_signal_objects` 等断言 `_cold_trace_summary(cold_lines, i) == row.trace_summary`。✅
- **Fail-closed**: malformed timing signal → `HostDurableError`；malformed failure metadata → `HostDurableError`；malformed partial tool-call signal → `HostDurableError`。测试覆盖 malformed rejection 路径。✅

**结论**: **PASS**。

#### 5e. Pyright / Test

- **pyright**: 0 errors, 0 warnings, 0 informations ✅
- **Tests**: 6 文件 160 passed, 0 failed ✅
- **测试覆盖**: 
  - `test_tool_trace_projection.py` (33 tests): signal 复制、timing signal、failure metadata 6 变体 + malformed rejection、partial tool-call signal 状态 + malformed rejection、context compaction pressure 派生、bounded text malformed 校验
  - `test_tool_trace_queries.py` (33 tests): query helper 四路径 signal 保持 + provider_request_id diagnostic query
  - `test_toolruntime_executor.py` (33 tests): failed/cancelled/policy_blocked failure metadata 生产 + bounded text parametrize (null / 512 / 513)
  - `test_engine_ingest_mapping.py` (61 tests): engine_ingest context_pressure signal 映射
  - `test_toolruntime_accept_barrier.py` (30 tests): accept barrier 中 ToolAcceptResult signal 字段
  - `test_phase6_toolruntime_integration.py` (3 tests): 集成

**结论**: **PASS**。

---

## Findings

**None.**

经过对 PR diff 的 full-scope 审查（56 files, +8103/-36 lines），未发现新的 correctness、architecture、LLM-facing semantic、layering 或 pyright-test 风险。

Aggregate deepreview 中的两个已知低严重度 finding（常量重复定义 → 已修复；跨 event read → 已知低风险）均已在 PR 中妥善处理或记录为 residual risk，不构成 gate blocker。

---

## Coverage Notes

### 审查路径

| 检查项 | 方法 | 结果 |
|---|---|---|
| PR diff vs 本地分支一致性 | `gh pr diff --name-only` vs `git diff --name-only main..HEAD` + `diff` | 一致 |
| PR head commit | `gh pr view --json commits` vs `git rev-parse HEAD` | 一致 (`5c452c67`) |
| PR metadata | `gh pr view --json state,isDraft,baseRefName,headRefName,mergeable` | draft/open/main/correct head/mergeable |
| PR body 信号描述 vs 实现 | diff 对照 P01/P02/P03/P04 生产路径 | 准确 |
| Residual risk 归属 | control doc + PR body | WU-OBS-00/Issue #70 |
| 漏推文件 | diff PR vs local | 无 |
| Artifact 完整性 | PR file list vs expected slice chain | OBS-SIG-00 至 OBS-SIG-05 + aggregate deepreview 链完整 |
| 总控状态一致性 | `issues-implementation-control.md` | gate ready-to-open-draft-PR 与 PR draft 一致 |
| 验证记录可信度 | 独立复验 pytest + pyright | 160 passed / 0 errors 与 PR body 一致 |
| README 触发 | CLAUDE.md 规则 + 实际 diff | dayu/host/README.md + tests/README.md 已更新 |
| 架构分层 | 文件路径 + import 审查 | tool_trace_signals 在 Host 层，无反向依赖 |
| LLM-facing 语义 | signal 字段名 + bounded text 规则审查 | 自解释，无内部术语泄漏 |
| 层级依赖 | import graph 审查 | Host→Engine 单向，同层引用正确 |
| P01-P04 来源正确性 | 逐函数审查生产路径 | 来源受控，降级正确，闭集完备 |
| hot/cold 等价 | trace_summary 构造 + 测试断言 | 统一构造，测试覆盖 |
| fail-closed | 校验函数 + malformed rejection 测试 | 全部 fail-closed |
| pyright | 全项目 | 0 errors |
| tests | 6 文件 160 tests | 全部通过 |
| GH checks | `gh pr checks 137` | 无 CI 配置（项目使用本地验证） |

---

## Validation

### 独立运行验证

```text
pyright (full project):
  0 errors, 0 warnings, 0 informations

pytest (6 affected files):
  tests/host/test_tool_trace_projection.py ......... 33 passed
  tests/host/test_tool_trace_queries.py ............ 33 passed
  tests/host/test_toolruntime_executor.py .......... 33 passed
  tests/host/test_engine_ingest_mapping.py ......... 61 passed
  tests/host/test_toolruntime_accept_barrier.py ... 30 passed
  tests/host/test_phase6_toolruntime_integration.py  3 passed
  Total: 160 passed, 0 failed

git diff main..HEAD --check:
  OK (no whitespace errors)
```

### 采信验证

- PR body 验证声明经独立复验全部确认
- Aggregate deepreview 链（mimo + ds → controller adjudication → fix → rereview mimo + ds → controller adjudication）完整，最终 verdict PASS
- 控制文档状态与 PR 状态一致
- 所有 review artifact 均在 `docs/reviews/` 下可追溯

---

## Residual Risks

| Risk | Severity | Owner | Notes |
|---|---|---|---|
| WU-OBS-00 analyzer 未落地 | Medium | WU-OBS-00 (#70) | 明确 non-goal；signal 的唯一消费方缺失则 signal 无法产生可观测价值；已在 control document 登记为 `pending-prerequisite` |
| `_context_compaction_request_payload` 跨 event read 在大规模 catch-up 时的性能 | Low | WU-OBS-SIGNALS-01 maintainer | 已知 DS finding 2；当前 batch size 下不构成实际问题；每次 compaction failed 最多一次 SQLite primary-key read |
| 无 CI checks 配置 | Note | 项目级 | `gh pr checks 137` 返回 "no checks reported"；项目依赖本地 pyright + pytest 验证，未配置 GitHub Actions/CI。不构成 gate blocker，但建议后续考虑添加 |

---

## Verdict

**PASS**

PR #137 满足 draft PR gate 的所有检查条件：
- PR diff 与本地分支一致，head 包含 aggregate deepreview acceptance commit
- PR body 准确描述 P01 context_pressure、P02 tool_timing、P03 failure_metadata、P04 partial_tool_call_signal 信号范围
- Residual risk 正确归属 WU-OBS-00 / Issue #70
- PR 保持 draft/open、base main、head 正确分支
- 无漏推文件、artifact 缺失、总控状态不一致或验证记录不可信问题
- 无新增 correctness、architecture、LLM-facing semantic、layering 或 pyright-test 风险
- 已知 residual risks 均为低严重度且已在 control document 登记
