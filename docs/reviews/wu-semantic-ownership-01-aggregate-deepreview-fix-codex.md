# WU-SEMANTIC-OWNERSHIP-01 Aggregate Deepreview Zero-change Finding Disposition — AgentCodex

## Verdict

`ZERO_CHANGE / ACCEPTED_FINDING=0 / READY_FOR_DUAL_COMPLETE_AGGREGATE_REREVIEW`

- Gate：同一 `WU-SEMANTIC-OWNERSHIP-01` umbrella aggregate deepreview fix/disposition gate。
- 执行时间：`2026-07-19 21:32:19 +0800`（本机系统时钟）。
- Branch：`phaseflow/host-issues-control`。
- Review range：`b1a0631f397967e7530b676a90ef7467d83a1817^..85aa7184a694448a5b27da7cca52f753f84d6e20`。
- 唯一写入：本 disposition artifact。
- 产品代码、测试、README、design、control、workflow 与既有 review artifact 均未修改；未 stage、commit、push、创建 PR、触发远端/Windows workflow，也未派生 subagent。
- Controller accepted code/doc/test finding：`0`；needs-evidence：`0`；本轮 fix：`0`。

## Immutable Review Inputs

已完整读取 `AGENTS.md`、Controller adjudication、zero-change authorization、AgentMiMo artifact 与 AgentDS artifact，并读取与三项候选及既有裁决直接相关的代码、owner-level tests 和 Controller validation 真源。

| 项目 | 锁定值 | 核验 |
| --- | --- | --- |
| HEAD | `85aa7184a694448a5b27da7cca52f753f84d6e20` | PASS |
| tree | `0db1c91f92dca594cf77c74bbde8f5b4fc42710d` | PASS |
| AgentMiMo artifact SHA-256 | `9bb5168bfd4eb9bbb8ae5a74ded5d8c6eba0ceb77c948ce45164af0308e66107` | PASS |
| AgentDS artifact SHA-256 | `3afb417dcc8dee839a98d69099615b4fd5091fde6e8b97a1b639244cdbb74ffc` | PASS |
| Controller adjudication SHA-256 | `6f6264ac3079038832f6f565a282e9f00007c3e53223ebe9212152bb93d75607` | PASS |
| Controller zero-change authorization SHA-256 | `1a97049298bc231a68cbb5ab6c2179e445d0fba7237a7907bbd6081d109aa293` | PASS |
| staged | empty | PASS |

## Controller-owned Dirty Path Hash Lock

下表是创建本 artifact 前的完整 dirty baseline；状态与 SHA-256 已锁定。本轮结束时只允许在这些不变路径之外新增本 artifact，且不把任何路径加入 index。

| 状态 | 路径 | SHA-256 |
| --- | --- | --- |
| `M` | `docs/host/issues-implementation-control.md` | `78d5f8d5f3e07025913a68000b185544643fba9473aa887eec69451d54034a29` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-controller-adjudication.md` | `6f6264ac3079038832f6f565a282e9f00007c3e53223ebe9212152bb93d75607` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-controller-authorization.md` | `4d6953b26fe81abf32c66cb9b62e4dee47f159e23ae8a3826b5479d8cf9fe48e` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-ds.md` | `3afb417dcc8dee839a98d69099615b4fd5091fde6e8b97a1b639244cdbb74ffc` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-fix-controller-authorization.md` | `1a97049298bc231a68cbb5ab6c2179e445d0fba7237a7907bbd6081d109aa293` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-mimo.md` | `9bb5168bfd4eb9bbb8ae5a74ded5d8c6eba0ceb77c948ce45164af0308e66107` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-codex.md` | `b06cf2831655db530303a20e1edb45ebf1709d3f6d7673bfffe2e33897720710` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-controller-authorization.md` | `c6d368b6274605ceb86cde8393f2bab5f94a01c1f775b9cc52ed3c5b5dfb7c58` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-controller-validation.md` | `6d2b76b42515a7eccb14d0546196ed475e8c7cd758b29e0f824523b653abbc34` |
| `??` | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-accepted-commit-controller-validation.md` | `2b1704bead5baf7e03a13be8d48655d46225df9f390704f496c72d2e58c796fc` |

## Finding Disposition

### DS-01 — typed evidence exact-match

`REJECTED_NOT_A_DEFECT / NO_FIX`

- 正确 owner 是 `dayu.host.evidence.render_accepted_tool_evidence_for_llm()`：`dayu/host/evidence.py:158-177` 明确声明并实现唯一 LLM-facing renderer。
- `dayu/host/compact_material.py:292-297` 的 dataclass exact-match 校验不是第二文本真源，而是阻止 `text` 与 `AcceptedToolEvidenceLLMMaterial` 分叉的 fail-closed invariant。
- 真实 producer `dayu/host/compact_material.py:2576-2588` 直接以同一 renderer 的返回值构造 `text`；fallback projection `dayu/host/run_input.py:2924-2934` 也从 typed material 调用同一 renderer，不从 raw/internal fields 重建语义。
- renderer 变更时，生产构造链会在同一运行时函数中同步产生与校验文本，不存在需要调用方复制固定四行格式的第二真源。删除或弱化校验反而会允许 typed material 与 LLM-facing 文本漂移。
- 未实施证明：上述 source/test paths 相对 HEAD 零 diff；没有修改 renderer、dataclass、helper、fallback 或测试。

### DS-02 — `mark_ready()` / `report_fatal()`

`REJECTED_NOT_A_DEFECT / NO_FIX`

- lifecycle owner 已明确：`dayu/host/_execution_health.py:1-5` 声明该 gate 由 opener event loop 单一拥有，`HostExecutionHealthGate` 是 execution health 与 new-work admission 的唯一 lifecycle owner。
- READY contract 已明确：`mark_ready()` 的现有 docstring（`dayu/host/_execution_health.py:120-126`）声明只在全部 startup critical component 成功后从 STARTING 进入 READY。
- DS 提出的 TOCTOU 不成立。`mark_ready()` 在 `dayu/host/_execution_health.py:120-132` 是同步、无 `await` 的状态检查/写入；在同一 opener event loop 内，`report_fatal()` task 不可能在其 read/check/write 临界段中间抢占。
- 若 critical task 在此前获得调度并报告 fatal，`report_fatal()` 会在 `dayu/host/_execution_health.py:153-179` 把状态置为 UNAVAILABLE；随后 `mark_ready()` 的第一分支会抛出 typed unavailable error，不能错误覆盖为 READY。
- `dayu/host/open_host.py:1316-1395` 创建并共享 gate，在 scheduler 打开、startup recovery 与其它 startup critical component 完成后才调用 `mark_ready()`；`dayu/host/dispatch.py:2634-2695` 把 critical task 异常/意外退出统一提交到同一 gate。现有 startup recovery/READY 和 health owner tests固定该 handoff 与 fail-closed contract。
- “不可从异步上下文调用”并不是正确约束：同步方法可以在 async opener 中调用，关键约束是同一 owner event loop 与方法内无 await。不得用不准确且重复的局部 docstring替代已存在的 owner contract。
- 未实施证明：`dayu/host/_execution_health.py` 中不存在建议文本“不可从异步上下文调用”；相关 source/test paths 相对 HEAD 零 diff；没有添加 docstring、锁、状态分支或测试。

### DS-03 — compact / memory event ref consistency

`REJECTED_NOT_A_DEFECT / NO_FIX`

- 正确 owner 是 `dayu/host/run_input.py:3055-3087` 的 `_require_compact_memory_event_ref_consistency()`，它在 Run input 构造消费两个 durable view 前统一校验同一 compaction fact。
- 双方均为 `None` 时在 `3073-3074` 正常放行；双方持有同一 ref 时在 `3075-3076` 正常放行。
- 一方有 ref、另一方无 ref，或双方 ref 不同，均表示 compact artifact 与 memory snapshot 对同一 durable fact 不一致；现有分支正确要求 `MemoryProjectionRepairRequired`，不能放宽为下游容错。
- `tests/host/test_run_input_builder.py:3849-3927` 已分别覆盖双 `None`、同 ref、compact-only、memory-only 与不同 ref 五种 owner-level contract 场景。
- 未实施证明：相关 source/test paths 相对 HEAD 零 diff；没有放宽校验、添加 fallback、兼容分支或测试修改。

## Findings

未发现实质性问题。Controller accepted finding 保持 `0`。

## Preserved User / Controller Adjudications

| 项目 | 本轮保持状态 |
| --- | --- |
| Config 与 Host internal SQLite/EventLog | `ACCEPTED_TRUSTED_INTERNAL` / trusted-local；不引入 secret infrastructure |
| Tool Trace、audit、public、LLM-facing、operator logs/outputs/diff/reviews | configured API key/header plaintext-zero，既有 zero-required 边界不变 |
| Gemini quota/provider adherence | `EXPECTED_TEST_ACCOUNT_QUOTA / PROVIDER_ADHERENCE_RESIDUAL / NO_CODE_ACTION / NON_BLOCKING`；不发 provider 请求，不改 config/model/key/retry/quota/budget |
| AR-F06 | `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`；future Host scheduler/lifecycle owner不变 |
| AR-F07 | `PENDING_RELEASE_BLOCKER`；未触发 Windows，Darwin skip 不作为 Windows success |
| Issues 142/151/175/177/178 与 Web/WeChat/render trackers | 既有 owner/destination 不变，未实施、未新建 WU |
| Topic 8 | 240-character Engine error projection维持 accepted-as-is / no-code |
| Topic 9 | design clarification only；保留现有 defensive safety，未实现统一 tool authorization framework |

## Read-only Verification

| 检查 | 结果 |
| --- | --- |
| `git rev-parse HEAD` / `git rev-parse HEAD^{tree}` | 与锁定 HEAD/tree 完全一致 |
| AgentMiMo / AgentDS `shasum -a 256` | 与锁定 SHA-256 完全一致 |
| 创建前完整 dirty path `shasum -a 256` | 与上表逐项一致 |
| `git diff --cached` | empty |
| `git diff --check` | PASS |
| protected product/test/design/README source diff | empty |
| DS-01 renderer owner、exact-match 与真实 producer source assertions | PASS |
| DS-02 opener-loop owner、READY guard、fatal→UNAVAILABLE source assertions | PASS；建议 docstring exact search为预期零命中 |
| DS-03 双空/同 ref/不一致 repair 分支及五个 owner-level test source assertions | PASS |

本轮没有产品或测试代码变更，因此未重跑 pytest/pyright；既有 accepted aggregate validation 证据保持不变，本 disposition 不把历史验证包装为 fresh 执行。

## Open Questions

无。

## Residual Risk

- 本轮未创建新 residual；AR-F06、AR-F07、Gemini/provider 与既有 deferred issue ledger按上表原样保留。
- 后续 gate 必须由 AgentMiMo 与 AgentDS 对完整不变 aggregate tree执行双路 re-review；不得用本 disposition 替代完整组合审查。

## Final Gate State

`ZERO_CHANGE / ACCEPTED_FINDING=0 / READY_FOR_DUAL_COMPLETE_AGGREGATE_REREVIEW`

本 artifact 的最终 SHA-256由写入后的外部封口命令计算并在交接中报告；artifact不自嵌自身 SHA，避免自引用。
