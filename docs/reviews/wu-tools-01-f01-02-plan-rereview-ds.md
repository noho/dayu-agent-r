# WU-TOOLS-01-F01-02 Plan Re-Review — AgentDS

## 1. Re-Review Context

| 项目 | 值 |
|---|---|
| work unit | WU-TOOLS-01-F01-02 |
| gate | re-review after plan fix |
| plan artifact | `docs/host/wu-tools-01-f01-02-cancellation-plan.md` |
| fix report | `docs/reviews/wu-tools-01-f01-02-plan-fix-codex.md` |
| original review | `docs/reviews/wu-tools-01-f01-02-plan-review-ds.md` |
| controller adjudication | `docs/reviews/wu-tools-01-f01-02-plan-review-controller-adjudication.md` |
| re-review artifact | `docs/reviews/wu-tools-01-f01-02-plan-rereview-ds.md` |
| reviewer | AgentDS |
| date | 2026-06-08 |

## 2. Review Scope

严格限定为 controller adjudication 中标记为 accepted 且要求写入 plan 的四项 required plan fix。不重新扩大 review 范围，除非发现新 blocking 问题。

## 3. Required Fix Verification

### Fix 1: Slice 1 — ToolExecutionOutcome 合法包含 ToolCancelledOutcome

**Adjudication 要求**: "Slice 1 明确：direct Fins awaiting callable 的返回类型 `ToolExecutionOutcome` 已合法包含 `ToolCancelledOutcome`，不需要修改 callable 协议或 Host / Engine contract。"

**Plan 中的落点**:

1. Section 6 Contract Changes (line 96):
   > direct Fins awaiting callable 的返回类型 `ToolExecutionOutcome` 已合法包含 `ToolCancelledOutcome`。因此 download / preprocess callable 在观察到 Host token 已取消时可以直接返回 cancelled outcome；这不是 callable 协议变更，也不需要修改 Host / Engine contract。

2. Section 7 Implementation Decisions (line 136):
   > direct Fins awaiting callable 可以直接返回 `ToolCancelledOutcome`，因为它不经过 legacy exception projection；该返回值已经属于 `ToolExecutionOutcome` 联合类型，不需要修改 callable 协议、Host contract 或 Engine contract。

**验证**: 合同层（Section 6）与决策层（Section 7）两处独立声明，覆盖契约边界与实现指导两层语义。implementation agent 不可能在 type legality 上产生误解。

**状态**: 已修复

---

### Fix 2: Slice 1 — create/checkpoint/submit 时序 invariant

**Adjudication 要求**: "Slice 1 明确 create/checkpoint/submit 时序：在 durable job create 后、后台 submit 前必须做同步 token checkpoint；若 checkpoint 命中 cancel，调用 `runtime.request_cancel(job_id)` 并不得 submit 后台 job。实现可以扩展 `_start_lock` 范围覆盖 create/checkpoint/submit 决策，或在锁释放后、submit 前做二次同步 checkpoint；无论方案如何，都必须满足 invariant。"

**Plan 中的落点**:

1. Slice 1 Exact changes (line 163–164):
   > durable job create 后、后台 `executor.submit` 前必须做同步 token checkpoint；若 checkpoint 命中 cancel，必须调用 `runtime.request_cancel(job_id)` 并不得 submit 后台 job。
   > create / checkpoint / submit 决策必须满足同一个不可破坏时序：实现可以扩展 `_start_lock` 范围覆盖 durable create、同步 checkpoint 与 submit 决策，也可以在锁释放后、submit 前做二次同步 checkpoint；无论采用哪种方案，都不得留下"checkpoint 已看到取消但仍 submit 后台 job"的窗口。

2. Slice 1 Invariants (line 182):
   > durable job create 后、后台 submit 前的取消检查必须是同步 checkpoint；命中取消后必须先桥接到 `runtime.request_cancel(job_id)`，再返回 cancelled outcome 或可收口的 cancelled job 事实。

3. Section 6 mitigation (lines 127–129):
   > Fins tool start 前观察 token，若已取消则不创建 job。Fins tool start 后、返回 awaiting outcome 前再次观察 token；若已取消，立即 `runtime.request_cancel(job_id)` 并返回 `ToolCancelledOutcome` 或保证 job record 进入 cancelling/cancelled 可由 wait adapter 收口。

**验证**: 
- 时序约束覆盖三处：Exact changes（实现细节）、Invariants（不可违反）、Mitigation（风险收口）。
- 两种实现方案（扩展 `_start_lock` 或锁释放后二次同步 checkpoint）均被明确允许，且明确无论何种方案 invariant 必须成立。
- "不得 submit 后台 job" 用否定句式直接禁止错误路径。
- 二次 checkpoint 方案覆盖原 AgentDS Finding 2 指出的锁释放后至 submit 前竞争窗口。

**状态**: 已修复

---

### Fix 3: Slice 4 — Fins read checkpoint 密度裁决

**Adjudication 要求**: "Slice 4 明确 checkpoint 密度裁决：瞬时读方法入口 checkpoint 足够；含搜索、XBRL、processor、目录/文件循环或大结果组装的方法需要循环内或高风险边界 checkpoint。"

**Plan 中的落点**:

Slice 4 Exact changes (lines 312–314):
> Checkpoint density decision:
> - Instant read methods whose work is bounded to one repository metadata/blob access or one direct processor read only need an entry checkpoint plus a checkpoint before the single high-risk call when applicable.
> - Methods involving search, XBRL facts, processor traversal, directory/file loops, table/fact filtering loops, or large result assembly need checkpoints inside the loop or immediately before and after the high-risk boundary.

**验证**:
- 两层裁决明确区分瞬时方法与涉及搜索/迭代的方法，消除原 Finding 4 指出的密度歧义。
- "Instant read methods" 精确对应 `list_documents`/`get_document_sections`/`get_page_content` 等方法，"search, XBRL facts, processor traversal, directory/file loops" 精确对应 `search_document`/`query_xbrl_facts`/`get_financial_statement` 等方法。
- implementation agent 不需要自行重新裁定密度标准。

**状态**: 已修复

---

### Fix 4: Slice 2 — provider fallback loop 每次 attempt 前 token 检查

**Adjudication 要求**: "Slice 2 明确 `search_public_web` provider fallback loop 在每次 provider attempt 前检查 token，取消后不得尝试后续 fallback provider。"

**Plan 中的落点**:

1. Slice 2 Exact changes (lines 210–212, 224):
   > at the start of each provider fallback loop iteration, before each candidate provider attempt;
   > If token cancellation is observed before a provider attempt, `search_public_web` must not try that provider or any later fallback provider.

2. Slice 2 Invariants (line 230):
   > Provider fallback loop checks token before every attempt; cancellation after one provider failure must prevent subsequent fallback attempts.

3. Slice 2 Tests (line 237):
   > `test_search_web_cancelled_between_provider_attempts_stops_fallback`

4. Section 9 Expected assertions (line 400):
   > Web search receives execution context token and stops provider fallback on cancel.

**验证**:
- Exact changes 指定 checkpoint 位置："at the start of each provider fallback loop iteration, before each candidate provider attempt"。
- Error handling 使用否定句式明确禁止：不存在"当前 provider 跳过但尝试下一个"的歧义。
- Invariant 覆盖跨 provider failure 场景：cancellation after one failure prevents subsequent。
- 测试用例命名精确对应该场景：`test_search_web_cancelled_between_provider_attempts_stops_fallback`。

**状态**: 已修复

## 4. Finding Status Summary

| Finding ID | 来源 | 类型 | 最终状态 | 验证证据 |
|---|---|---|---|---|
| F-DS-1 | AgentDS F1 | callable type contract | **已修复** | plan:96, plan:136 |
| F-DS-2 | AgentDS F2 | lock/checkpoint timing | **已修复** | plan:163–164, plan:182, plan:127–129 |
| F-DS-4 | AgentDS F4 | checkpoint density | **已修复** | plan:312–314 |
| F-DS-5 | AgentDS F5 | provider fallback loop | **已修复** | plan:211, plan:224, plan:230, plan:237 |

> 注：AgentMiMo 的 F-MIMO-04/F-MIMO-05 分别与 F-DS-1/F-DS-2 同源，已通过上述 F-DS-1/F-DS-2 的修复一并处理。

## 5. Scope Boundary Check

确认 fix gate 未扩散修改范围：

- Plan artifact 的 Section 2 (Non-Goals) 未变。
- Section 5 (Affected Files) 未变。
- Section 6 (Contract/State Machine) 未变，仍显式声明不修改 Host/Engine contract、Fins job 状态机。
- 未新增 allowed files / modules。
- 未新增或移除 implementation slices。
- 两阶段启动仍为 deferred (R1)，owner/destination 明确。

## 6. New Blocking Issues

**无新 blocking issue。**

四项 accepted finding 均完整落入 plan artifact，修正全部精确到位，未发现过度修正或自相矛盾。Plan 中的 Section 6 合同声明、Section 7 实现决策项、Slice 1/2/4 的 Exact changes、Invariants、Error handling 和 Tests 均保持自洽。

原 AgentDS Finding 3 (Doc `list_files` 非递归 checkpoint 粒度) 在 adjudication 中被标记为 deferred-with-owner → implementation agent，属于实现粒度裁决，不阻塞 plan。

## 7. Verdict

**Plan 可进入 accepted plan commit / implementation gate。**

- 四项 required plan fix 全部已修复，无未修复、部分修复或证据失效项。
- 无新 blocking issue。
- Plan 达到 code-generation-ready 标准，可移交给 implementation agent 执行 Slice 1–5。

## 8. Artifact Metadata

- **输出路径**: `docs/reviews/wu-tools-01-f01-02-plan-rereview-ds.md`
- **Reviewer**: AgentDS
- **Review 类型**: plan re-review gate
- **Blocking**: 否
- **审查文件**: 仅本 artifact；未修改任何生产代码、测试、README、控制文档或 plan artifact。
