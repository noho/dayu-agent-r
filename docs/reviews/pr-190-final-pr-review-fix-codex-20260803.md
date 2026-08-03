# PR 190 Final PR Review Fix — Codex

## Gate 与范围

- 日期：2026-08-03。
- Gate：PR review → fix。
- 角色：implementation / fix Agent。
- PR：[#190](https://github.com/noho/dayu-agent-r/pull/190)，`codex/interactive-oracle` → `main`。
- Reviewed target：`main..0f7dc59168aca6e5f5b5bb30c059711465347bf2`。
- Prompt follow-up：`7cf1027c..0f7dc591`，共 6 commits。
- 输入 review：
  - `docs/reviews/pr-190-final-pr-mimo-review-20260803.md`；
  - `docs/reviews/pr-190-final-pr-ds-review-20260803.md`。
- 既有裁决真源：
  - `docs/reviews/wu-cli-conformance-f01-f07-aggregate-deepreview-controller-adjudication.md`；
  - `docs/reviews/wu-cli-conformance-f01-f07-draft-pr-pass-controller-adjudication.md`；
  - `docs/reviews/wu-cli-conformance-f01-f07-final-closeout.md`；
  - `docs/gateflow/pr-190-compactor-llm-facing-aggregate-deepreview-acceptance-20260803-193014.md`。
- 本 gate 唯一 changed file / artifact path：
  `docs/reviews/pr-190-final-pr-review-fix-codex-20260803.md`。

## 第一性原理判断

代码修复的必要条件是 review 提供了新的、可复现且归属于当前 owner boundary 的 production failure，或提供了足以推翻既有 frozen contract / controller 裁决的新直接证据。本轮两路 final review 均未满足该条件：MiMo 明确为 `PASS — 无 blocking finding`，DS 明确为“无新增 Critical / High Finding”且 code review 支持 merge；DS 后续列出的若干 residual 是既有观察的重述，没有新失败数据、可达反例或新的 owner 证据。

因此本 gate 的正确 fix 不是修改代码，而是把 review 事实与既有裁决重新对齐。若恢复旧枚举、增加 broad catch、为不存在的 asyncio 调度点加竞态补偿、按 source kind 穷举相同 trust boundary，反而会违反 frozen v2 design、掩盖 invariant failure、制造下游特例或扩张无证据的测试/产品语义。

## Final review 逐项裁决

### A. 两路没有新的 production finding

**裁决：accepted as review fact；无 code fix。**

- MiMo 的最终结论是 code-review `PASS`，correctness、semantic ownership、LLM-facing、overcoupling、stability 与 v2 migration 均未报告 production finding。
- DS 的 finding summary 明确没有新增 Critical / High finding，并确认无 semantic ownership drift、无过度耦合、无兼容 shim；其 merge-readiness 结论同样支持代码质量通过。
- DS 的 residual 列表没有新增失败路径，只重列既有设计观察、环境 observation 或 out-of-scope provider selection 说明。

没有 accepted finding，故不存在应由 implementation Agent修复的 production/test/prompt/design 项。

### B. 已关闭的旧观察不得被 residual 标签重开

**裁决：rejected-with-reason；最终 finding 状态为 `证据失效`；无 code fix。**

1. `intent_type` / continuity `reason`
   - 既有 aggregate controller 已对恢复旧闭集枚举作出 `REJECT-WITH-REASON`。
   - frozen v2 design 在 `docs/host/design.md` 明确写为 `intent_type: str`、`reason: str`；production contract `CompactForwardIntentV2`、`CompactReferenceContinuityV2` 与 Memory projection 同样使用 `str`，prompt 则给出非空、业务可读和禁止内部状态/错误码的自足语义。
   - DS final review 自身也承认这是 v2 有意设计且不影响 Host correctness。把它再次标为 residual 不能推翻 frozen contract，也不能授权恢复旧 vNext enum。

2. VT100 reader broad catch
   - 既有 controller 已以 `REJECT-WITH-REASON` 关闭：`_read_loop` 分别处理 terminal/select/read/strict UTF-8 的预期 I/O 失败；PromptToolkit parser resolution 是同步内部 invariant。
   - DS 没有给出 `Vt100Parser.feed/flush` 在当前合法或畸形输入 contract 下抛出异常的可复现数据。建议的 `except Exception: break` 既会掩盖 programming/invariant error，也不会向 `wait_next` 投递 typed terminal/error，不能修复其声称的永久等待。
   - 若未来要引入 reader failure channel，那是新的 runtime/public failure 语义，需要独立设计；不能在本 gate 添加 broad catch。

3. `_flush_submit_handoff_input` 竞态
   - `dayu/cli/composer.py::_flush_submit_handoff_input` 在最初的 ambiguity sleep 之后，依次执行 `application.is_done`、`flush_keys()`、`feed_multiple()`、`process_keys()`；这四步之间没有 `await`。
   - 它们在同一 asyncio event-loop task 内同步执行，其他 coroutine 无法在 DS 假设的 check/flush 窗口切换 `application.is_done`。既有 controller 已据此 `REJECT-WITH-REASON`。
   - final review 没有新增调度点或失败数据，故旧竞态假设仍然失效。

4. multi-pass summary 与 provider selection
   - multi-pass summary 的 newline 合并已由 controller 以 disjoint material、frozen pass order 与 root-level 全量 revalidation 证据 `REJECT-WITH-REASON`；DS 未提供新 coherence predicate 或失败样本。
   - prompt aggregate acceptance 已明确拒绝把测试的 Mimo-first / DeepSeek-only selector 升级为 production provider-selection contract。`LLMContextCompactor` 接收注入 runner 是当前正确边界，本 gate不得创造 provider 语义。

这些观察都保持 closed；不得据此修改 production、测试、prompt、design、README、oracle 或 scenario。

### C. DS 的 45 commits 是统计误述

**裁决：accepted as artifact metadata correction；无 code fix。**

- `git rev-list --count main..0f7dc591` 的直接结果是 `43`，不是 DS artifact 所写的 `45`。
- `git diff --shortstat main..0f7dc591` 仍为 `364 files changed, 141152 insertions(+), 15597 deletions(-)`；merge base 为 `113ea34d47b95812d79aa31705949bbb46bc6061`。
- 该误述只影响 review artifact 的 commit-count 元数据，不改变 reviewed tree、diff 内容、owner contract 或任何代码结论。按用户约束不原地修改 DS reviewer artifact。

### D. MiMo corrected artifact 已严格分离两组真实证据

**裁决：accepted；无 code fix。**

- 前序 F01-F07 full-real evidence 精确归属于 `main..7cf1027c` closeout：真实 Mimo / `mimo-v2.5-pro` bundle、F01-F07 mandatory matrix 与当时的 accepted compact evidence只能证明前序 closeout。
- 本次 Compactor LLM-facing follow-up 精确归属于 `7cf1027c..0f7dc591`。本次 Mimo、DeepSeek real smoke 均为 `network_unavailable`，没有非空 candidate，因此 strict parse、governance acceptance、caps compliance、injection resistance 与 whole-candidate repair 的真实模型行为均为 `not_observed`。
- corrected MiMo artifact 没有用前序 full-real bundle冒充本 follow-up 的真实模型行为证据；deterministic matrix 只被用于证明 owner contract。

### E. previous-* 未逐个 injection 参数化不构成 owner gap

**裁决：rejected-with-reason；最终 finding 状态为 `证据失效`；无 code fix 或额外测试要求。**

- `CompactionRequest.compact_input` 把 previous/trace/evidence/answer 全部机械投影为同一个 `CompactInputV2.source_boundary`；previous kind 只在 `_previous_source_kind` 中映射业务 kind，不产生 trust-policy 分支。
- `CompactInputV2.to_json()` 统一序列化完整 `current_input` 与完整 `source_boundary`。
- `llm_compaction._compaction_request_prompt_block_vnext` 对完整 `request.to_json()` 只应用一对 `UNTRUSTED_COMPACTION_MATERIAL_JSON_BEGIN/END` marker，没有按 `source_kind` 分支、过滤或重写。
- 因而 trust boundary 的唯一 owner 是包围完整 typed input JSON 的 renderer marker，而不是各 source kind。当前四个不同材料位置的 adversarial canary 已证明 production renderer 的共同路径；穷举 previous-* kind 不会增加 owner contract 证明。
- prompt aggregate acceptance 已逐项作出同一裁决，完整自然语言 evaluation 仍归既有 Issue 80；本 gate不得创造新的参数化测试要求。

### F. `not_observed` 的 gate 含义

**裁决：保留为已分类 observation；无 code fix。**

- `not_observed` 严格阻止把本 follow-up 的真实 provider strict parse、governance acceptance、caps compliance、injection resistance 或 repair 行为写成 behavior pass / formal conformance pass。
- 它不否定 deterministic tests 对 parser、renderer、typed boundary 与 governance owner contract 的证明，也不产生 production failure。
- 因此 `not_observed` 不阻止完成 Gateflow 的 code-review/fix/re-review/final-closeout 记录；它只把真实模型行为与 formal conformance 的最终裁决保留给 user / Oracle controller。
- 本 artifact 不替 user / Oracle controller 宣告 formal conformance pass、mark ready、approve 或 merge，也不新增 real-provider 测试要求。

## Exact-head 与状态复核

| 检查项 | 直接证据 | 结论 |
|---|---|---|
| 本地 HEAD | `git rev-parse HEAD` = `0f7dc59168aca6e5f5b5bb30c059711465347bf2` | PASS |
| remote-tracking HEAD | `refs/remotes/github/codex/interactive-oracle` = `0f7dc59168aca6e5f5b5bb30c059711465347bf2` | PASS |
| GitHub PR head | `gh pr view 190` 的 `headRefOid` = 同一 OID | PASS |
| PR identity | `number=190`、`state=OPEN`、`isDraft=true`、`baseRefName=main`、`headRefName=codex/interactive-oracle`、`mergeable=MERGEABLE` | PASS |
| PR commit count | `git rev-list --count main..0f7dc591` = `43` | PASS；纠正 DS 的 45 |
| Follow-up commit count | `git rev-list --count 7cf1027c..0f7dc591` = `6` | PASS |
| Frozen registry | `git diff --exit-code 7cf1027c..0f7dc591 -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json docs/cli_ci.md` = exit 0 | PASS；follow-up 零 diff |
| Reviewer artifacts 当前 corrected bytes | MiMo SHA-256 `5f30c2368d8a01f1c39292f9fd32df1159b1ac31fe1217b8540eef378b9ad6eb`；DS SHA-256 `6bbcb45a89d5f43b4b17b01a84621ad854408c4277c2d7cc02ec38128d882af3` | PASS；本 gate 未写入 reviewer artifacts |
| Pre-fix 工作树 | 仅两份 final reviewer artifacts 为未跟踪文件 | PASS；与用户声明一致 |
| Post-fix 工作树 | 仅两份 final reviewer artifacts与本 artifact 为未跟踪 review artifacts | 预期状态；无代码或其它文档改动 |

## Validation 与 docs decision

- 本 gate 执行的是 review 证据裁决，没有修改运行时代码、测试或 LLM-facing 内容；没有可接受 production finding需要触发测试或 pyright 重跑。
- 既有 prompt aggregate acceptance 已记录 focused/Host/full validation 与 pyright 0；本 artifact 不把这些 deterministic 结果扩张为本 follow-up 的真实 provider behavior pass。
- Docs decision：只新增 Gateflow 要求的 durable fix artifact。按用户明确边界，不修改 README、design、prompt、oracle、scenario 或两份 reviewer artifact。
- 未执行 commit、push、mark ready、approve、merge、request reviewers 或其它外部状态写入。

## Residual risks 与 uncovered areas

1. 本 follow-up 的真实 provider behavior 仍为 `not_observed`。
   - 分类：`requiring explicit user decision`。
   - Owner：user / Oracle controller 负责 formal conformance 与最终 PR 裁决；这不是 implementation code defect，也不派生新的测试要求。
2. F01-F07 既有 Host public-cancel test-order flake、Oracle registry overall calibration 等 residual 保持原 owner 与原裁决。
   - 分类：`assigned to later work unit` / 既有 controller owner。
   - 本 final review 没有提供新证据重开它们，本 gate不扩张 scope。

没有 unclassified residual risk，没有 blocking code finding。

## Completion status

- Accepted production findings：`0`。
- Code/test/prompt/design/README/oracle/scenario fixes：`0`。
- DS 重列且与 frozen design / 直接调度证据冲突的旧观察：`证据失效`，保持 closed。
- Artifact-only reconciliation：完成。
- Gate verdict：`PR-REVIEW-FIX-PASS — NO-CODE-FIX`。
- Next entry point：由 user / Oracle controller执行 final PR re-review / adjudication，并保留 formal conformance 与最终 PR 决策权。
