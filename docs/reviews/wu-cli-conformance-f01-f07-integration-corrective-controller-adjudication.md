# WU CLI Conformance F01-F07 — Integration Corrective Controller Adjudication

## Gate

- Gate: corrective implementation slice code review
- Entry HEAD: `df99f858`
- MiMo artifact: `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-code-review-mimo.md`
- DeepSeek artifact: `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-code-review-ds.md`
- Controller verdict: `FIX-LOOP-REQUIRED`

MiMo 未报告实质 finding，并逐项验证 publication digest、v2 compact consumer、Phase5 durable
exact-once、无 production delta 与验证记录。总控不以该结论替代证据，仍逐项裁决 DeepSeek 的
11 项记录以及 MiMo 的 residual risk。

## Finding adjudication

| ID | Review claim | Controller disposition | Direct evidence / required action |
|---|---|---|---|
| DS-01 | SQL result 的位置索引脆弱 | `REJECT-NON-ACTIONABLE` | helper 内 SELECT 与读取相邻且四个字段均与 EventLog/typed enum 交叉断言；没有静默误通过反例。改 row factory 会扩大纯测试 seam，不是本 corrective root cause。 |
| DS-02 | dispatch count 只按 `run_id`，没有绑定 `attempt_id` | `ACCEPT-LOW` | helper 已持有 `refs.attempt_id`，而语义名称是目标 Attempt 的 exactly-once。即使当前 policy 固定单 attempt，直接按 `(run_id, attempt_id)` 查询能让 owner assertion 自足，避免未来 continuation 复用时统计整个 Run。要求最小修正并跑 Phase5 focused。 |
| DS-03 | terminal/cancel promotion 共处一个测试 | `REJECT-OUT-OF-SLICE` | 该双场景测试结构在 corrective 前已存在；本 slice 只替换 stale drain/polling 证据。两个场景各自独立创建/关闭 Host、store、scheduler，资源不会跨场景泄漏。拆分不关闭当前 conformance finding。 |
| DS-04 | 双 worker factory 计数是累计值 | `REJECT-ALREADY-EXPLICIT` | helper docstring 已明确 `expected_factory_creations` 是“场景累计应创建的 worker 数”；两条 Run 各自还有独立 dispatch-record/EventLog/Attempt 断言。累计值为 2 可检测第三次 factory create，不会误过。 |
| DS-05 | event-started 后 RUNNING 的时序 | `CLOSED-BY-DIRECT-EVIDENCE` | reviewer 已追踪 `dispatch.py`：Host 先提交 ATTEMPT_RUNNING，再启动 consumer 并读取 events；无需修改。 |
| DS-06 | raw SQLite 绕过 public read path | `REJECT-BY-DESIGN` | helper 同时断言 public `get_run` 与 durable SQLite，目的是双 owner 交叉验证，不是用 raw state 替代 public contract。 |
| DS-07 | 两个 fake compactor 的 summary labels 不同 | `REJECT-FALSE-CONTRACT-INFERENCE` | `conversation_compaction_user.md` 对 `session_summary.source_labels` 没有 source-kind 限制；`docs/host/design.md` §24.3 只要求 boundary label 恰好 represented 或 dropped；`context_governance._represented_sections` 明确允许一个 label 被多个 semantic section represented。utils fake 只用 trace label、host fake 用全部 boundary label，都是不同但合法的 accepted candidate，并不构成 typed contract 漂移。禁止把 reviewer 偏好的生成策略重新裁决成 frozen oracle。 |
| DS-08 | full-suite flake 记录缺精确 revision/fingerprint | `ACCEPT-DOCS` | 首轮失败、focused stress 与第二轮 full-suite 的 disposition 诚实，不能伪造 root cause；但 validation 发生在 unstaged working tree，单写 entry HEAD 不足以证明 exact input。要求 artifact 增补被验证的五个 corrective data/test 文件 SHA-256（或等价 working-tree fingerprint），并说明 artifact 自身在验证后创建。 |
| DS-09 | Ruff 97 disposition | `CLOSED-CORRECT` | accepted plan 没有 full-repository Ruff gate；changed Python Ruff 通过，既有全仓 debt 不得冒充本 slice blocker。 |
| DS-10 | publication manifest 三个 digest | `CLOSED-CORRECT` | reviewer 与 MiMo 独立重算 package SHA 和 manifest SHA，均一致。 |
| DS-11 | system/user compactor prompt assertion | `CLOSED-CORRECT` | stable task rule 属 system prompt；request placeholder、自足 v2 input/output schema 与 coverage rule 属 user prompt，符合 LLM-output/input boundary。 |
| MiMo-R1 | scheduler 若未来改成 accept-then-commit，event barrier 可能需调整 | `RESIDUAL-OWNER-ASSIGNED` | 当前 scheduler 的直接时序已证明安全；未来若 Host dispatch owner 改 barrier，则由该 owner 同步测试。非当前 blocker。 |

## Fix-loop scope

只允许以下改动：

1. `tests/host/test_phase5_local_execution_integration.py`：dispatch record 查询同时绑定
   `run_id` 与 `attempt_id`；
2. `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-implementation-codex.md`：
   记录五个被验证 corrective 文件的 working-tree SHA-256，并澄清验证与 artifact 创建顺序；
3. Codex fix artifact 与两路 re-review/controller artifacts。

不得修改 production、frozen registry、S8 README baseline、fake compactor 生成策略或拆分既有测试场景。
Fix 后至少运行 Phase5 focused、四类 corrective focused、changed Ruff、full pyright、JSON/diff/hash 审计；
两路 reviewer 必须复核 DS-02/DS-08 closure，并确认其余 disposition 没有被实现绕开。
