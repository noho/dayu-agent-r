# WU-CLI-CONFORMANCE-F01-F07 — PR Review Controller Adjudication

## Scope

- Gate: PR review / fix / re-review
- PR: 190 (`codex/interactive-oracle` -> `main`)
- Reviewed remote head: `c69445c2d22febf056bf54e331912f62b3d5ddcb`
- MiMo artifact: `docs/reviews/wu-cli-conformance-f01-f07-pr-review-mimo.md`
- DeepSeek artifact: `docs/reviews/wu-cli-conformance-f01-f07-pr-review-ds.md`
- Fix artifact: `docs/reviews/wu-cli-conformance-f01-f07-pr-review-fix-codex.md`
- MiMo re-review: `docs/reviews/wu-cli-conformance-f01-f07-pr-rereview-mimo.md`
- DeepSeek re-review: `docs/reviews/wu-cli-conformance-f01-f07-pr-rereview-ds.md`

Controller 逐项读取两路 review，并以代码、事务、测试、设计和 frozen oracle 直接证据裁决；两路是否一致不构成裁决依据。

## Accepted findings

| ID | Decision | Direct evidence and required closure |
|---|---|---|
| MiMo-01 canonical drop order | `accepted` | `accept_compact_candidate_v2` 按 root boundary 构造 `explicitly_dropped_coverage`，但 `_canonical_candidate` 原样保留 LLM drop 顺序；`compact_payload._validate_committed_coverage` 要求 coverage drops 与 candidate drops tuple 精确相等。逆序 drop 会让已接受 truth 在 `CONTEXT_COMPACTED` payload strict validation 处失败。修复必须留在 Context Governance canonicalization owner，并覆盖逆序多 drop round-trip。 |
| MiMo-02 attachment cleanup | `accepted` | `_close_managed_attachment` 原实现先 join delayed recovery，再调用底层 `attachment.aclose()`；join 的非 cancellation 异常会跳过 native attachment 释放。修复必须由 attachment lifecycle owner 用 finally 保证 close，并验证原失败仍传播。 |
| DS-D-001 compact input 双 projector | `accepted` | `CompactionRequest.compact_input` 与 `compact_material.conversation_compact_input_vnext_from_material_pack/_source_boundary_v2` 重复投影同一个 v2 input，且 evidence readable text/source-kind mapping 各维护一份。以 `CompactionRequest.compact_input` 为唯一 owner，生产调用迁移后删除另一套实现和 export；不保留 wrapper/re-export。 |

## Accepted findings final status

| ID | Final status | Controller evidence |
|---|---|---|
| MiMo-01 canonical drop order | `已修复` | `_canonical_candidate` 只在 Context Governance accept owner 内按 immutable root `boundary_order` 排序 drops；新增逆序 multi-drop 测试贯穿 accept、`CONTEXT_COMPACTED` strict payload 与 parse round-trip。Controller 复跑两个定向节点为 `2 passed`；MiMo 与 DeepSeek re-review 均验证通过。 |
| MiMo-02 attachment cleanup | `已修复` | `_close_managed_attachment` 用 `try/finally` 保证 delayed recovery join 失败时仍调用底层 `attachment.aclose()`；回归测试断言 close 恰好一次且 close 成功时原 join `RuntimeError` 传播。Controller 复跑通过；双路 re-review 均验证通过。 |
| DS-D-001 compact input 双 projector | `已修复` | 所有 active Python production/test/smoke consumer 改读 `CompactionRequest.compact_input`；`compact_material` 的重复 projector、两个 private helper 与 export 已删除，未留 wrapper/re-export；Controller `rg` inventory 为零命中，定向 pyright 为 0。双路 re-review 均验证通过。 |

Controller 对 DeepSeek re-review 中“若 join 与 `aclose()` 同时失败则原 join 异常优先传播”的说明作证据校正：Python `finally` 内的新异常会成为实际传播异常，原 join 异常保留在 exception context。当前 accepted contract 与回归只要求底层 close 成功时原 join 失败继续传播，生产代码和测试满足该要求；MiMo re-review 对此表述准确。该 artifact 文本误述不改变 finding closure，也不扩张为未经 frozen oracle 定义的双失败优先级语义。

## MiMo findings adjudication

| ID | Decision | Reason |
|---|---|---|
| MiMo-01 | `accepted` | 见 accepted findings。 |
| MiMo-02 | `accepted` | 见 accepted findings。 |
| MiMo-03 `CompactorProposalManifestReference` 位置 | `rejected-with-reason` | 该类型是 `CONTEXT_COMPACTED` canonical payload 的 typed manifest-binding contract；`context_events` 同时负责 binding validator，recorder 是唯一 producer 但不是 contract owner。移回 operation 会让 event contract 反向依赖 producer。 |
| MiMo-04 delayed fatal 原异常 | `rejected-with-reason` | delayed task 的 contract 是把原失败按低基数写入 health gate后收口，不承诺向 caller 重抛原异常；logger 已记录原类型。`report_fatal` 自身失败应作为 health owner failure 传播。所谓 double shield 只有一次 cancellation continuation，没有无界循环；资源释放问题由 MiMo-02 单独修复。 |
| MiMo-05 `intent_type/reason` 恢复 enum | `rejected-with-reason` | frozen v2 design 与 LLM-facing schema明确两字段是非空 `str`；闭集只属于 status/source kind/drop reason。恢复旧 vNext enum 会重新裁决 frozen contract。 |
| MiMo-06 `context_governance.py` 过大 | `rejected-with-reason` | 模块只拥有 deterministic accept/reject、canonicalization 与 bounded repair feedback，写入/retry/Memory 均在外部；没有第二业务职责或失败数据。当前拆分会增加跨模块耦合。 |

## DeepSeek findings adjudication

### Main findings F-001—F-007

| ID | Decision | Reason |
|---|---|---|
| DS-F-001 response identity 未进 Memory | `rejected-with-reason` | design 把 provider/model lineage 定义为 `CONTEXT_COMPACTED` canonical fact 与 manifest binding；Conversation Memory 只承载 accepted business semantics。`docs/host/design.md` 还明确 endpoint/credential/provider raw material 不进入 memory。不同 read model 不需要复制全部 canonical fields。 |
| DS-F-002 parser 用内部错误文本分类 | `rejected-with-reason` | strict parser 的 duplicate/unknown/missing/type/enum raise sites 都是同模块封闭 helper，exact-key 检查先于 required reads；现有 malformed matrix逐码断言。review 未给出任一可达输入被误分类的反例；引入异常层级是无当前失败支撑的重构。 |
| DS-F-003 `--config` cleanup | `pass/no-fix` | reviewer 自身证据确认 parser、typed args、Service request 与引用全部删除；F01 inventory/真实 CLI evidence 已通过。 |
| DS-F-004 manifest reference owner | `rejected-with-reason` | 与 MiMo-03 同一事实，event contract owner 与 recorder producer 没有双真源。 |
| DS-F-005 `memory_policy` breaking signature | `pass/no-fix` | fresh contract 不做兼容；所有仓内 caller 已显式提供同一 typed policy，任务也禁止旧接口兼容。 |
| DS-F-006 prompt 不自足 | `rejected-with-reason` | `conversation_compaction_user.md` 逐字段列出输入/输出字段、类型、必填性、闭集、coverage rules 和最小 JSON 示例；同一 DS artifact 的 A-006 也逐项确认 PASS。 |
| DS-F-007 identity 跨层测试不足 | `rejected-with-reason` | Engine contract、Host event binding/parse、ingest、public compact smoke 均有 owner/integration tests；S8 full-real successful compact 还验证真实 provider/model identity、manifest、artifact 与 terminal 同源。要求单个测试重复全部层不是缺失 contract。 |

### Addendum A

| ID | Decision | Reason |
|---|---|---|
| DS-A-001 effective model 来源 | `rejected-with-reason` | 当前所有 adapter 原样使用 `RunnerSpec.model`，design 明确 Agent 在成功 done boundary 与实际 `RunnerSpec.provider/model` 组合 identity；用户还明确 provider/model selection 是 non-goal。假设未来 adapter 隐式改写不构成当前缺陷。 |
| DS-A-002 builder 应移到 contract | `rejected-with-reason` | Agent success boundary 同时拥有 done fact、request identity 与实际 spec，是唯一有足够输入的 producer；contract class负责字段不变量。把 production mapping 放进被动 contract 会倒置 owner。 |
| DS-A-003—A-006 | `pass/no-fix` | Service cleanup、exports、分层和 prompt 自足均由 reviewer确认通过。 |

### Addendum B

| ID | Decision | Reason |
|---|---|---|
| DS-B-001 precondition failed 无 request | `rejected-with-reason` | 这是既有且已正式裁决的 operation-outside governance diagnostic，不是 request-backed compaction terminal。`tests/host/test_compaction_terminal.py::test_compaction_terminal_writer_inventory_uses_only_shared_owner` 明确固定该边界；历史 controller artifact `wu-ctx-02-03-pr-review-controller-adjudication-20260601.md` 已裁决 synthetic operation id/attempt 0 无需伪造 request。production 只在当前 nonterminal Run 进入 projector，随后同 transaction fail Run，不会把该 diagnostic 当 request-backed operation 恢复。 |
| DS-B-002 terminal TOCTOU | `rejected-with-reason` | `HostTransactionRunner.run_write` 在 operation 前执行 SQLite `BEGIN IMMEDIATE`，两个 writer 不能同时进入 permit read/write critical section；真实双 connection barrier test `test_two_competing_terminal_writers_commit_exactly_one_canonical_terminal` 已证明 loser 在 winner commit 后读取 closed truth。 |
| DS-B-003 随机 failure event id | `rejected-with-reason` | request-backed writer在同一 `BEGIN IMMEDIATE` transaction 先取 permit；precondition diagnostic 与 Run fail transition也原子提交。CAS/operation 异常会 rollback，成功后 Run/terminal guard阻止第二次语义提交；review 没有可达重复路径。 |
| DS-B-004 unused helper | `rejected-with-reason` | 私有未调用 helper 不影响本 work unit correctness/schema；为低价值 cleanup扩大已验证 PR fix surface 不符合最小化原则，分配给 Host compaction maintenance owner。 |

### Addendum C

| ID | Decision | Reason |
|---|---|---|
| DS-C-001 pending running action/editor cleanup | `rejected-with-reason` | queued running action 只会在前一 PromptToolkit application 已退出后被下一次 `read_event` 消费；前一调用的 finally 已取消并 join editor tasks，因此 review 假设的同时非空状态不可达。 |
| DS-C-002 `updated_text` 未初始化 | `rejected-with-reason` | 非零 editor 分支立即 return，后续读取只存在于成功赋值路径；full pyright 0 errors 直接否定该类型假设。 |
| DS-C-003 resume 未显式 factory | `rejected-with-reason` | public execution helper 的默认 factory就是 production SIGINT owner；session resume 使用默认值是有意装配，且本任务明确不新增/重构 resume。 |
| DS-C-004 unified scope | `pass/no-fix` | fresh namespace 是已批准 breaking design；不读旧 scope、不提供兼容。 |

### Addendum D

| ID | Decision | Reason |
|---|---|---|
| DS-D-001 | `accepted` | 见 accepted findings。 |
| DS-D-002 adversarial compactor 缺失 | `rejected-with-reason` | `test_llm_compaction` 覆盖 malformed/truncated JSON、unknown/duplicate keys、type/enum/blank；`test_compaction_operation` 覆盖 semantic invalid、bounded repair、whole replacement 与 exhaust；`test_compact_pipeline` 覆盖跨 pass duplicate repair/exhaust，S8 又有真实 invalid repair/exhaust/fallback。premise 不成立。 |
| DS-D-003 multiprocess recovery 错误矩阵 | `rejected-with-reason` | attachment/process recovery 不是 F01-F07 accepted oracle；本 PR 相关 recovery 已有 owner/public SIGKILL evidence。新增存储损坏、锁竞争和恢复进程 crash 是独立 work unit。 |
| DS-D-004 public smoke 无 invalid recovery | `rejected-with-reason` | public compact smoke 已含 rejected proposal；完整 repair/exhaust/fallback由 operation/pipeline deterministic tests与S8真实 interactive conjunction覆盖。测试职责无需集中到一个 smoke 文件。 |
| DS-D-005 private monkeypatch | `rejected-with-reason` | 这些测试在 owner boundary 注入 runner/scheduler/clock failure，且均断言注入 seam 被调用；full-real evidence不使用 fake provider。没有“方法未调用却静默通过”的直接例证。 |
| DS-D-006 REPL driver 是 God function | `rejected-with-reason` | driver只协调 typed composer/Host/wait/cancel owners；chord、attachment、closeout、rendering均已拆为独立 typed state/helper。按行数再抽状态机会建立第二套生命周期 owner，review 无 semantic drift或失败反例。 |
| DS-D-007 compact input property 重算 | `rejected-with-reason` | 投影只遍历 bounded frozen material tuples；没有性能测量或复杂度风险。cached property 与 frozen slots 会扩大实现，且不修 correctness。 |
| DS-D-008 permit 无 `__post_init__` | `rejected-with-reason` | permit 是 module-private authority，只由已经验证 request/trigger/sequence 的 shared owner构造；外部不能用自行构造的值提交 terminal。防御性构造校验没有可达生产失败。 |
| DS-D-009 readable text 在重绑定 identity | `rejected-with-reason` | `readable_text` 是 frozen LLM input boundary 的语义内容，不只是 UI display；同 refs/kind 但不同文本表示 material drift，必须 fail closed，不能仅按 refs错误重绑定。 |

## DeepSeek open questions adjudication

| Question | Decision |
|---|---|
| Memory 是否持久化 response identity | 已由 design owner回答：不进入业务 Memory；EventLog canonical fact/manifest保留 lineage。 |
| 单 issue repair feedback 可能超过 cap | 每个 path/message/label 先截断到 240 chars；单 issue且无 label 的 JSON 上界远低于 8192。`RuntimeError` 是不可达 invariant guard，不是产品 open question。 |
| S8 bundle 是否交付 | 已交付 immutable bundle `/Users/leo/workspace/.dayu-cli-ci/pr190-wu-cli-conformance-f01-f07-s8-20260803T022326Z-9fec164715bc/bundle`，digest `7a80d9bcfb97bb7c8a80df8d2f10016d6f98577e01294f540a7ba2d9cea33b72`；aggregate dual review已读取并校验。 |
| F08-F13 是否完成 | 已由 PR 190 前序 `wu-cli-interactive-02` accepted commits完成；本 work unit只追加 F01-F07，不重新打开前序 frozen scope。 |

## Residual risks and owners

- GitHub reports zero checks: repository CI/config owner；只能报告“no checks”，不能伪称 CI pass。本地 full suite、pyright 与 immutable evidence 是独立证据。
- G01-G07 overall registry calibration: user/Oracle controller；不影响 init/prompt/interactive command-level readiness，也不由实现 Agent裁决。
- Phase 5 scheduler/test races reproducible on clean base: Host scheduler/test-runtime owner；non-regression，不在本 fix 猜测 timing patch。
- Host public cancel smoke test-order flake: Host public-smoke/test-runtime owner；aggregate adjudication已保留，需独立稳定 reproduction。
- renderer target pin / formal scenario promotion: Oracle renderer/calibration owner，merge 后处理；实现 Agent只报告 observation。
- resolved Authorization durable projection: effective-execution durable projection owner；S8只保留脱敏 evidence，不在本 work unit扩展 schema。
- real provider nondeterminism: deterministic owner matrix与真实 Mimo conjunction共同降低，不修改 frozen oracle。
- large PR cross-slice interaction: S1-S8 dual review、aggregate review、PR review、full suite、pyright与真实 evidence共同覆盖；PR fix 已完成双 re-review、453-test affected suite 与 full pyright。最终 accepted commit 仍需在 push 后生成 exact-head immutable evidence refresh。

所有 residual 均已分类；没有需要实现 Agent重新裁决 frozen behavior 的 open question。

## Re-review artifact integrity

- MiMo re-review SHA-256: `bd6bc08fb3fda679f7a5a16e8931edb859c92b0f68f002523acb43b90269a239`
- DeepSeek re-review SHA-256: `4a82d434a5c3cdaec5ad06e0f30bd63e32b1766689763fbed7ec3f61f51c1ca4`
- 两路均逐项给出三项 accepted finding 的 `已修复` 状态、无 new finding，并保留既有 residual owner；Controller 逐项独立核对 actual diff、回归测试、active-symbol inventory 与 pyright，不以“两路一致”代替证据。

## Current gate verdict

`PR-REVIEW-PASS — READY-FOR-ACCEPTED-PR-REVIEW-COMMIT`

Next entry: 创建 accepted PR review commit -> push -> exact-head immutable post-fix evidence refresh -> `draft-PR-pass` -> final closeout。
