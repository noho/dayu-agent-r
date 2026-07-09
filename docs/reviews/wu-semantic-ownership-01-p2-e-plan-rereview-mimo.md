# WU-SEMANTIC-OWNERSHIP-01 / P2-E Plan Re-Review — AgentMiMo

## Review Context

- Reviewer: AgentMiMo
- Artifact under re-review: `docs/reviews/wu-semantic-ownership-01-p2-e-plan-codex.md` (fixed version)
- Plan fix artifact: `docs/reviews/wu-semantic-ownership-01-p2-e-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p2-e-plan-review-controller-adjudication.md`
- Original reviews: `docs/reviews/wu-semantic-ownership-01-p2-e-plan-review-mimo.md`, `docs/reviews/wu-semantic-ownership-01-p2-e-plan-review-ds.md`
- Design ground truth: `docs/host/design.md`, `docs/engine/design.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Gate: plan re-review after controller-adjudicated plan fixes

## Re-Review Method

逐一验证 5 个 accepted controller findings 是否在 fixed plan 中被完整关闭。每个 finding 检查：plan 文本是否包含 controller 要求的所有元素、是否引入新的下游掩盖或 fixture cheating 风险、是否足够 code-generation-ready。

## Finding-by-Finding Verification

### P2E-PLAN-F01: stream heartbeat test — positive + negative assertion

**Controller requirement:** test must prove `STREAM_DEBUG_LOG_LEVEL` captures heartbeat AND ordinary `DEBUG` does not.

**Fixed plan evidence:**

- Failure 1 "Required implementation assertion" (line 66-68):
  - 正向断言：使用 `STREAM_DEBUG_LOG_LEVEL` 捕获 heartbeat，且继续确认 response bytes 未丢失。
  - 负向断言：使用普通 `logging.DEBUG` 捕获同类流过程时不得出现 heartbeat 记录；不得通过放宽 logger、提升生产日志级别或改 `runner.py` 让测试通过。
- Slice E1 "Exact allowed changes" (line 186): "同时负向断言普通 `logging.DEBUG` 不捕获 heartbeat。"

**Verdict: CLOSED.** 正向和负向断言均从 "evidence note" 提升为 required implementation assertion。禁止改 `runner.py` 或放宽 logger 的约束也已明确。实施 agent 可直接据此生成测试代码。

---

### P2E-PLAN-F02: wait-resume — fixture diagnosis + tool-call identity closure

**Controller requirement:** (1) first inspect `resume_request.messages`; (2) normal path asserts `UserMessage -> AssistantMessage(tool_call) -> ToolMessage`; (3) `AssistantToolCall.id == original awaiting tool_call_id`; (4) `ToolMessage.tool_call_id == AssistantToolCall.id`; (5) fallback = fix fixture/request atom first; (6) old English = stop and escalate.

**Fixed plan evidence:**

- Failure 6 "Required direct evidence still needed" (line 131-133): "implementation 第一步必须在该 integration path 中诊断 `resume_request.messages`，记录实际 message types、tool call id、tool name、arguments 与 tool result JSON。" — 满足 (1)。
- Failure 6 "Proposed fix location" (line 138-143): "正常路径必须断言 message 顺序和类型为 `UserMessage -> AssistantMessage(tool_call) -> ToolMessage`。" — 满足 (2)。
- 同段: "assistant tool call 的 `id/name/arguments` 与原 awaiting request 一致或为 LLM-safe replay 投影；其中 `AssistantToolCall.id` 必须等于原 awaiting `tool_call_id`。" — 满足 (3)。
- 同段: "`ToolMessage.tool_call_id` 必须等于同一个 `AssistantToolCall.id`，content JSON 包含 `answer: 42`。" — 满足 (4)。
- Failure 6 "Fixture/request-atom policy" (line 144-146): "如果诊断发现只有当前中文 fallback guidance，先修测试 fixture / request atom / accepted evidence envelope，让正常协议闭环路径可被覆盖，再迁移 assertion。" — 满足 (5)。
- 同段: "如果诊断发现旧英文 guidance 仍出现，停止 Slice E2 wait-resume alignment，并升级 production owner（`dayu/host/run_input.py` / awaiting accept path）；不得把旧英文 guidance 当成可接受输出。" — 满足 (6)。
- Slice E2 "Stop condition and split policy" (line 202-205): 重复了相同三层条件（中文 fallback → 修 fixture；旧英文 → 停止升级；触发 production → E2 拆分）。

**Verdict: CLOSED.** 六个子要求全部在 plan 中有明确、可执行的描述。实施 agent 的第一步是诊断 `resume_request.messages` 内容，然后按三条分支分别处理。tool-call identity 闭环（`AssistantToolCall.id` 和 `ToolMessage.tool_call_id` 等于原 `tool_call_id`）已作为 required assertion 写入。

---

### P2E-PLAN-F03: purge fixture — dedicated cancel request event + cancelled coverage

**Controller requirement:** (1) use dedicated cancel request EventLog event id, not arbitrary existing event; (2) check whether `cancelled` is in parametrize set; (3) apply same fix for `cancelled` if covered.

**Fixed plan evidence:**

- Failure 7 "Proposed fix location" (line 162): "在 test fixture 中为 `cancelling` Run 写入 dedicated cancel request EventLog row（使用专用 event id，不能复用任意已有 event），并把 `cancel_request_event_id` 插入 Run row" — 满足 (1)。
- 同段: "若相关 parametrize 包含 `cancelled`，同样应用该 durable invariant fix" — 满足 (2) 和 (3)。
- Failure 7 "Required direct evidence still needed" (line 156): "检查相关 parametrize 是否包含 `cancelled`；若包含，`cancelled` fixture 必须同样补合法 `cancel_request_event_id`。" — 重复确认 (2)(3)。
- Slice E2 "Exact allowed changes" (line 201): "purge fixture 为 `cancelling` Run 补 dedicated cancel request EventLog ref；若 `cancelled` 在相关 parametrize 中，同样补 `cancel_request_event_id`。" — 三处一致。

**Verdict: CLOSED.** 专用 event id（非复用任意已有 event）和 `cancelled` parametrize 覆盖检查均已在 plan 中明确。实施 agent 在修 fixture 前需先检查 parametrize 列表。

---

### P2E-PLAN-F04: E2 split policy if wait-resume triggers production owner

**Controller requirement:** if wait-resume diagnosis requires production work, Slice E2 must split so Host export and purge fixture alignment can proceed independently.

**Fixed plan evidence:**

- Slice E2 "Stop condition and split policy" (line 202-205):
  - "若 `resume_request.messages` 是当前中文 fallback guidance 或缺 request atom / accepted evidence envelope，先修 fixture/request atom，使测试覆盖正常协议闭环路径，再迁移 assertion。"
  - "若 `resume_request.messages` 仍出现旧英文 guidance，停止 wait-resume alignment，并升级 production owner（`dayu/host/run_input.py` / awaiting accept path）。"
  - "如果 wait-resume 诊断触发 production owner，Slice E2 必须拆分：先独立完成 Host export / purge fixture alignment，再把 wait-resume 作为 production-owner follow-up slice 处理；不得让 wait-resume production 风险阻塞已确认的 Host export / purge fixture 测试对齐。"
- Implementation closeout requirement (line 244): "若 wait-resume 诊断触发 production owner，closeout 必须记录 Slice E2 已拆分，以及 Host export / purge fixture alignment 与 wait-resume follow-up 的边界。"

**Verdict: CLOSED.** 拆分策略已明确定义：三层条件分支（修 fixture → 停止升级 → 拆分独立推进），且 closeout 必须记录拆分决策。实施 agent 不需要自行判断拆分方式。

---

### P2E-PLAN-F05: closeout must record export snapshot propagation

**Controller requirement:** implementation closeout must explicitly record that Engine and Host export snapshot alignment is test-only alignment against existing design/README public contracts, with no production/README change required unless diagnosis proves otherwise.

**Fixed plan evidence:**

- Implementation closeout requirement (line 243-244): "必须显式记录 Engine `input_projection` / projection export snapshot alignment 与 Host `HostThinkingView` export snapshot alignment 均是测试对既有 design / README public contract 的对齐；生产代码、生产契约和 README 不需要变更。"
- README / Doc Trigger Analysis (line 237-239): "Slice E1 only changes `tests/engine/*`... `dayu/engine/README.md` should not need update because production Engine contract is already documented." 和 "Slice E2 only changes `tests/host/*`... `dayu/host/README.md` should not need update because `HostThinkingView`, wait-resume replay, cancel request durable invariant, and purge precondition are already documented."

**Verdict: CLOSED.** closeout 要求已明确写出，且 README trigger 分析与 closeout 要求一致。实施 agent 在完成实施后必须显式记录这一 propagation 结论。

---

## Architecture Boundary Review

**Layering:** Plan 只修改 `tests/` 文件，不触及 `dayu/engine/`、`dayu/host/`、`dayu/runtime/` 或 `dayu/service/` 生产代码。分层边界完整。

**Owner boundary:** 每个 failure 的 semantic owner boundary 已明确定义：
- Failures 1-3: Engine test owner，对齐 Engine public/diagnostic contract。
- Failures 4-5: Host test owner，对齐 Host public API export。
- Failure 6: Host integration assertion owner + Host resume projection owner（production owner 升级路径明确）。
- Failure 7: Host durable schema invariant owner + test fixture owner。

**No downstream masking:** Plan 的 stop condition 机制确保如果生产行为与预期不符（failure 6 的旧英文 guidance 场景），plan 会停止并升级，而不是改测试掩盖问题。

**No fixture cheating:** Failure 7 的 purge fixture 修复要求使用专用 cancel request event id，不是复用任意已有 event。Failure 6 的 fixture 诊断要求先确认实际 `resume_request.messages` 内容，再决定修 fixture 还是改 assertion。

---

## Best-Practice Review

**Test alignment vs production fix:** Plan 正确区分了"测试对齐"（改测试断言/fixture 以匹配已接受的生产契约）和"生产修复"（改生产代码以修复回归）。7 个 failure 全部归类为前者，直接证据支撑充分。

**Stop condition design:** 三层 stop condition（中文 fallback → 修 fixture；旧英文 → 停止升级；触发 production → 拆分）是合理的防御性设计。它允许 plan 在不确定性下安全推进，而不是在 plan 阶段就做所有诊断。

**Propagation audit:** Plan 包含完整的 6 步 propagation audit expectation（line 248-255），覆盖了 wait-resume LLM-facing semantics 从 durable truth 到 LLM 可见输出的完整路径。

---

## Overcoupling Review

**Slice E2 heterogeneous risk:** E2 包含三个语义独立的变更（Host exports、wait-resume、purge fixture）。Plan 的 split policy 已明确如果 wait-resume 触发 production owner，E2 必须拆分。这降低了过度耦合风险——即使三个变更在同一个 slice 中，失败隔离仍然存在。

**No cross-layer coupling:** Plan 不引入跨层依赖。Engine 测试（E1）和 Host 测试（E2）完全独立。Failure 6 的 production owner 升级路径也只涉及 Host 内部（`run_input.py` / awaiting accept path）。

---

## Code-Generation-Readiness Assessment

每个 failure 的 plan 描述包含：
- Root-cause hypothesis（为什么失败）
- Required direct evidence（实施前需确认什么）
- Semantic owner boundary（谁负责修）
- Proposed fix location（改哪个文件）
- Required implementation assertion / Exact allowed changes（具体改什么）
- Tests to run（验证命令）
- Stop condition（什么情况下停止）

对于 failure 6，还包含三层 fixture/request-atom policy 和 split policy。

**Verdict: Plan is code-generation-ready.** 实施 agent 可以直接从 plan 文本生成每个 failure 的修复代码，无需重新诊断或设计决策（failure 6 除外，其第一步是诊断 `resume_request.messages`，这是 plan 明确要求的）。

---

## Residual Implementation Risks

1. **wait-resume fixture 可能缺少 request atom:** 如果 `_seed_active_integration_run` fixture 没有创建 `TOOL_CALL_REQUESTED` request atom 和 accepted evidence envelope，`_resume_wait_accepted_arguments` 会返回 `None`，生产代码走 fallback 中文 guidance 路径。此时实施 agent 必须先修 fixture 再改 assertion，而不是把 fallback guidance 当作正常输出。Plan 的 stop condition 已覆盖此风险，但实施 agent 需要严格执行诊断步骤。

2. **purge fixture 修改范围:** `_insert_run_row` 的调用方可能不止 `_SeedClosedSessionMatrixOperation`。如果修改 `_insert_run_row` 签名（添加 `cancel_request_event_id` 参数），需要检查所有调用方。如果只在 `_SeedClosedSessionMatrixOperation` 中单独创建 cancel request event 并直接 INSERT，则不影响其他调用方。Plan 没有指定具体实现方式，实施 agent 需要自行判断最小影响路径。

3. **broad suite 其它 stale snapshot:** 7 个 targeted 失败之外，broad suite 可能有其他测试因同一轮 public contract expansion 而 stale。Regression validation（`pytest tests/engine tests/runtime tests/service/test_host_assembly.py tests/host`）应覆盖此风险，但实施 agent 需要关注额外失败。

4. **E2 拆分协调:** 如果 wait-resume 诊断触发 production owner，E2 需要拆分为独立的 Host export / purge fixture alignment 和 wait-resume production-owner follow-up。Plan 定义了拆分策略，但在同一个 sub WU 内管理两个后续 slices 的边界需要实施 agent 显式记录。

---

## Findings

**无 finding。** 5 个 accepted controller findings 均已在 fixed plan 中完整关闭。Plan 的 owner boundary 分析正确，stop conditions 充分，split policy 明确，code-generation-ready 程度足够。没有发现下游掩盖、fixture cheating 或 production-contract drift 的残余风险。

---

## Conclusion

**Pass.**

Fixed P2-E plan fully closes all 5 accepted controller findings:

| Finding | Status | Verification |
|---|---|---|
| P2E-PLAN-F01 | CLOSED | 正向 + 负向 stream heartbeat 断言均为 required implementation assertion |
| P2E-PLAN-F02 | CLOSED | 六个子要求（诊断、消息顺序、tool_call_id 闭环、fixture 修复、停止升级）全部明确 |
| P2E-PLAN-F03 | CLOSED | 专用 cancel request event id + `cancelled` parametrize 覆盖检查 |
| P2E-PLAN-F04 | CLOSED | 三层 stop condition + E2 拆分策略 + closeout 记录要求 |
| P2E-PLAN-F05 | CLOSED | closeout 必须记录 export snapshot 是 test-only alignment |

Plan is approved for implementation. Residual implementation risks are documented above and do not block entry.
