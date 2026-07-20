# Phaseflow Umbrella Work Optimization Control

## 定位

本文档是 umbrella work unit / 多 sub-WU findings 修复的附加总控文件。后续用户要求总控同时读取本文档时，本文档用于约束流程成本、slice 粒度、review 路由、验证复用和 residual 分类。

本文档不替代：

- `AGENTS.md`
- 设计真源文档
- 当前 work unit 的主 control doc
- Gateflow / Phaseflow 的强制 gate 顺序

若本文档与上述更高优先级约束冲突，以更高优先级约束为准。

## 背景问题

多份 full-repository deepreview 合并后，若将每个 finding 都拆成独立 sub-WU 或每个低风险 slice 都完整执行双路 review / fix / re-review / control-doc bookkeeping，会产生很高的固定流程成本。

上一轮 umbrella 修复的主要耗时来源是：

- 多路 Agent review / re-review 等待与 artifact 读取。
- sub-WU / slice 过细导致 gate 固定成本重复。
- focused tests / pyright / diff check 在相邻低风险 slice 中重复运行。
- controller adjudication 与 control-doc 更新大量重复。
- pre-existing validation failures 每轮重新归因。
- artifact 手工写作和 stale control-doc row 修正。

后续类似工作必须在不降低 correctness / semantic ownership 严格性的前提下，减少不必要的流程重复。

## 总原则

1. 风险驱动 gate 深度，而不是 finding 数量驱动 gate 数量。
2. 能批量修复的同质低风险 findings，应优先合并成一个 implementation pass 和一个 aggregate review pass。
3. 生产语义、schema、durable state、state machine、LLM-facing 文本、public contract 的变更仍按高风险 gate 执行。
4. 测试 harness、doc-only、局部 helper 命名、docstring、常量统一、diagnostic 分类等低风险 cleanup 可以降低 slice / review 粒度，但不能跳过验证和 controller 裁决。
5. pre-existing failures 必须一次性登记成 baseline residual；后续只引用 baseline artifact，不重复归因。
6. 每轮 control doc 的 current gate / next entry point 必须指向下一个未完成 gate，避免 stale row。

## 风险分级

### High Risk

命中以下任一项，默认执行完整 gate：

- 生产代码行为变更。
- durable schema、EventLog、memory、trace、audit、outbox、state machine 变更。
- public API / package export / CLI / Service / Host / Engine contract 变更。
- LLM-facing prompt、tool schema、memory / evidence projection、用户可见输出变更。
- 并发、取消、恢复、幂等、事务边界变更。

默认流程：

- plan
- plan review
- fix / re-review if needed
- per-slice implementation
- per-slice code review
- fix / re-review if needed
- aggregate deepreview

### Medium Risk

命中以下任一项，允许合并相邻 slice，但仍需双路 review：

- 测试 helper owner 迁移，影响多个测试目录。
- 生产 owner helper 替换测试侧 raw SQL / fixture 行为。
- public-contract test 断言方式迁移。
- 多个 consumer 同时迁移到同一测试 helper。

默认优化：

- 最多 2-3 个 implementation slices。
- 同类 helper / fixture 迁移可以合并为一个 slice。
- 每个 slice 可做 code review；若 slice 很小，允许 controller 明确裁决为合并到 aggregate review。

### Low Risk

命中以下项且不触及生产代码时，可采用批量 gate：

- 测试 docstring / helper name / constant reuse。
- 仅修复 test harness 局部 duplication。
- artifact / control-doc bookkeeping。
- README 同步或 no-update decision。
- 已有 review finding 的纯文档澄清。

默认优化：

- 多个 finding 合并成一个 fix batch。
- 一个 implementation artifact。
- 一个 controller validation artifact。
- 一个 aggregate review artifact。
- 无需每个 finding 单独双路 re-review，除非 reviewer 发现 material issue。

## Slice 切分约束

切分 slice 前必须回答：

- 是否有不同 semantic owner？
- 是否有不同 validation matrix？
- 是否有不同 failure blast radius？
- 是否需要不同 reviewer 专项知识？

只有答案为“是”时才拆分。否则优先合并。

禁止按以下方式机械切分：

- 每个文件一个 slice。
- 每个 raw finding 一个 slice。
- 每个测试目录一个 slice。
- 每个 reviewer comment 一个 slice。

建议默认：

- 小型 test harness cleanup：1 个 slice。
- 中型 helper ownership migration：1-2 个 slices。
- 生产 state machine / durable change：按真实 owner boundary 拆 2-4 个 slices。

超过 3 个 slices 时，plan 必须说明为什么不能合并。

## Review 路由优化

### 可合并到 aggregate review 的情况

- 低风险测试 cleanup。
- doc-only / artifact-only / README-only 变更。
- reviewer finding 是单文件常量、docstring、命名一致性。
- controller 能用直接证据验证修复。

### 必须 per-slice review 的情况

- 修改生产代码。
- 修改 public contract。
- 修改 durable state / schema / EventLog / memory / trace。
- 修改 LLM-facing 文本。
- 修改并发、取消、恢复、幂等逻辑。
- slice 之间存在依赖或可能互相掩盖失败。

### Re-review 策略

accepted finding 修复后：

- High / Medium risk：双路 re-review。
- Low risk：允许单路 re-review或 controller direct validation，但必须在 adjudication 中说明理由。
- 若 finding 来自单一路 reviewer 且 fix 是纯机械替换，可只派原 reviewer re-review。

## Validation Profile

后续 plan 应优先引用预定义 validation profile，避免每轮重新设计命令。

### `test-harness-low`

适用：

- 测试 helper / docstring / constant / assertion cleanup。

最低验证：

```bash
source .venv/bin/activate
pytest <affected-tests> -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

### `durable-test-medium`

适用：

- 测试侧 durable helper / raw SQL diagnostic / projection helper 迁移。

最低验证：

```bash
source .venv/bin/activate
pytest <affected-durable-tests> -q
python -m pyright dayu/ tests/ utils/
git diff --check
rg <owner-helper-and-raw-sql-classification-patterns>
```

### `protocol-test-medium`

适用：

- cancellation fake、runner fake、compactor fake、tool fake 等测试替身迁移。

最低验证：

```bash
source .venv/bin/activate
pytest <affected-protocol-tests> -q
python -m pyright dayu/ tests/ utils/
git diff --check
rg <old-fake-or-old-method-patterns>
```

### `production-high`

适用：

- 生产语义、schema、state machine、public contract、LLM-facing 文本。

最低验证由 plan 按 owner boundary 明确列出，不能只使用默认 profile。

## Baseline Failure Registry

如果验证遇到疑似 pre-existing failure，controller 应：

1. 复跑最小失败命令。
2. 在当前变更前的 baseline commit 上复现，或用已有 artifact 证明已知。
3. 写入当前 validation / adjudication artifact。
4. 后续相同 failure 只引用该 baseline，不再重复归因。

baseline residual 必须包含：

- 失败命令。
- 失败测试名。
- baseline commit 或 artifact。
- 与当前 owner path 无关的直接证据。
- 后续 owner / destination。

## Artifact 优化

每个 artifact 应短而完整，避免重复粘贴长日志。

必须包含：

- scope
- changed files
- decisions / findings
- validation commands and results
- README decision
- propagation audit
- residual risk classification
- stop status

可以省略：

- 完整 pytest 输出。
- 与裁决无关的长 diff。
- 已在其它 artifact 中记录且本轮未变化的历史流水账。

## Control Doc 更新约束

control doc 每次更新只记录：

- 当前 gate / next entry point。
- 本 gate artifact。
- accepted commit。
- accepted finding final status。
- residual risk destination。

不得在当前状态行无限追加所有历史细节。历史流水账应进入 review artifact 或 archive。

更新后必须检查：

- 是否仍有旧 row 写着过期 next gate。
- 是否 current gate 指向刚完成的 gate。
- 是否 P3 / sub-WU 被误写成 umbrella final closeout。
- residual risk 是否缺 owner / destination。

## Agent 使用优化

默认仍使用用户指定的 Agent 路由。

允许优化：

- 同一低风险 batch 可只派一次双路 aggregate review。
- fix 很小且机械时，优先派原 finding reviewer re-review。
- controller 不应让 Agent 重读无关历史 artifact；handoff 必须给出精确 scope 和 expected artifact。
- large review 时，reviewer scope 应按 owner boundary 分工，而不是泛泛全仓重复。

## Completion Definition

对于 umbrella WU：

- 修完当前 review findings 不等于 umbrella 完成。
- 当前 batch 完成后，control doc 的 next entry point 应指向下一轮 full-repository deepreview 或用户指定的下一 sub-WU。
- 只有后续 full-repository deepreview / PR gate / final closeout 全部满足时，umbrella 才能 final closeout。

对于单个 sub-WU：

- plan / implementation / accepted findings / aggregate deepreview 全部关闭后，sub-WU 才算 locally accepted。
- 若 aggregate residual 已分类且有 destination，可进入下一个 sub-WU 或 full-repository review。

## Completed Finding Fix Batch: WU-CLI-SMOKE-01-R1 Slice 1

- Source reviews: `docs/reviews/code-review-20260721-005108.md` 与 `docs/reviews/code-review-20260721-005320.md`。
- Controller adjudication: `docs/reviews/wu-cli-smoke-01-r1-slice1-code-review-controller-adjudication.md`。
- Risk: Low Risk / `test-harness-low`；只接受 DS-F03 renderer close owner-level direct test，不修改生产代码。
- Batch policy: 单一 test-only fix batch，不按 finding 或文件继续拆 slice。
- Review policy: 附加总控允许单路 narrow re-review，但用户已指定 AgentMiMo / AgentDS 两路同时 review，因此本批仍执行双路 narrow re-review。
- Validation: focused renderer test、prompt / interactive CLI regression、全量 pyright、`git diff --check`。
- Deferred owner: DS-F02 归本 WU Slice 2 的真实 Host → Service → CLI transient / slow-consumer E2E；不得作为本低风险 batch 的 fake-only 扩 scope。
- Rejected item: DS-F01 描述的 late delta 在下一次 `drain_nowait()` 会被 terminal set 过滤，未形成 terminal 后交付；Slice 2 barrier 继续验证既定并发 acceptance。
- Baseline residual: none。
- Fix artifact: `docs/reviews/wu-cli-smoke-01-r1-slice1-fix-codex.md`；test-only fix complete。
- Controller validation: `docs/reviews/wu-cli-smoke-01-r1-slice1-fix-controller-validation.md`；99 tests passed、pyright 0 errors、diff check pass。
- Re-review artifacts: `docs/reviews/code-review-20260721-011148.md` 与 `docs/reviews/code-review-20260721-010824.md`；两路均确认 DS-F03 fixed，无新增 material defect。
- Re-review adjudication: `docs/reviews/wu-cli-smoke-01-r1-slice1-code-rereview-controller-adjudication.md`；decision=`accepted-slice1-rereview`。
- Accepted Slice 1 commit: `70ccda60`。
- Final batch status: completed。主 control doc 已进入 Slice 2 implementation；DS-F02 由 Slice 2 owner 收口。

## Active Finding Fix Batch: WU-CLI-SMOKE-01-R1 Draft PR #180

- Source reviews: `docs/reviews/wu-cli-smoke-01-r1-pr-180-review-mimo.md` 与 `docs/reviews/wu-cli-smoke-01-r1-pr-180-review-ds.md`；两路代码/架构结论均 PASS。
- Controller adjudication: `docs/reviews/wu-cli-smoke-01-r1-pr-180-review-controller-adjudication.md`；decision=`fix-required`。
- Accepted finding: PR180-F01；PR body 使用字面量反斜杠-n 而非真实 Markdown 换行。文字内容正确，但 PR metadata 格式不满足 draft-PR-pass。
- Risk: Low Risk / PR-metadata-only。
- Batch policy: 单一外部 metadata fix，不拆 slice；不得触碰 production/test/design/README。
- Fix owner: AgentCodex；仅允许修复 PR #180 body 换行并写 `docs/reviews/wu-cli-smoke-01-r1-pr-review-fix-codex.md`。
- Review policy: 用户指定 AgentMiMo / AgentDS 两路 review，因此 fix 后仍执行双路 PR re-review。
- Validation: `gh pr view` 证明 body 为真实多行、无字面量反斜杠-n；Draft=true、review requests 为空、base/head 与标题不变；工作树仅包含预期 artifacts/control。
- Baseline residual: accepted aggregate live-only、capacity 256、cross-domain ordering 与可控 worker 边界继续有效，不因 metadata fix 改变。
- Fix artifact: `docs/reviews/wu-cli-smoke-01-r1-pr-review-fix-codex.md`；PR180-F01 metadata-only fix complete，PR code head 未变。
- Controller validation: `docs/reviews/wu-cli-smoke-01-r1-pr-review-fix-controller-validation.md`；真实 Markdown 多行、无 closing directive、Draft/head/base/title/reviewer invariants、两项 Windows CI pass 与工作树边界均已验证。
- PR re-review artifacts: `docs/reviews/wu-cli-smoke-01-r1-pr-180-rereview-mimo.md` 与 `docs/reviews/wu-cli-smoke-01-r1-pr-180-rereview-ds.md`；两路均确认 PR180-F01 fixed、0 blocking、无新增 finding。
- PR re-review adjudication: `docs/reviews/wu-cli-smoke-01-r1-pr-180-rereview-controller-adjudication.md`；decision=`accepted-PR-rereview`。
- Final batch status: completed；等待 accepted PR review commit/push 与最终远端 head CI closeout。

## 下次使用方式

用户可要求：

```text
按 $phaseflow 推进，同时读取 docs/phaseflow-umbrella-optimization-control.md 作为附加总控约束。
```

controller 必须在 goal confirmation 或 resume 时说明：

- 当前 work 是否适用本文档；
- 本轮采用 High / Medium / Low 哪个风险级别；
- 是否合并 findings / slices；
- review / re-review 是否采用优化路由；
- validation profile；
- baseline residual 是否可复用。
