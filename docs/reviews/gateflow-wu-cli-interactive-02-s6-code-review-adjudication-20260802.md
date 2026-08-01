# WU-CLI-INTERACTIVE-02 S6 Code Review Adjudication

## 1. Gate facts

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Gate：S6 code-review adjudication
- Reviewed base / current HEAD：`9ad45cf717f192b12f411d03332b971f30aff472`
- Implementation artifact：
  `docs/reviews/gateflow-wu-cli-interactive-02-s6-implementation-codex-20260802.md`
- Independent reviews：
  - `docs/reviews/code-review-wu-cli-interactive-02-s6-mimo-20260802.md`
  - `docs/reviews/code-review-wu-cli-interactive-02-s6-ds-20260802.md`
- Controller decision：`no accepted code or documentation finding`；进入 unchanged-diff 双路 re-review。

Controller 直接读取了两份 review、完整 implementation artifact、exact worktree diff、
`docs/cli_ci_scenarios.json` 的 base/current JSON object，以及外部 evidence root
`/Users/leo/workspace/.dayu-cli-ci/interactive-s6-20260802-Meo1Jt`。Agent 结论不自动构成通过。

## 2. Controller validation

- exact scope：9 个批准的职责文件修改，加 1 个 implementation artifact；production、测试代码、
  utils 与 frozen calibration adjudication 均无 diff。
- registry object-level comparison：精确删除计划指定的 17 条，未新增 scenario；只修改 5 条
  保留 pairwise row 和 `prompt.P37-label-followup`，其余 436 条 scenario object 完全相同。
- 5 条保留 row 只从 `command_parameter_ids` / `raw_stable_claims` 删除
  `parameter:config:default`，两个 `init-deepseek-config-explicit` precondition 字段不变。
- 当前总数 442（prompt 383 / init 59）；prompt parser argv 中 `--config` 为零；global 与
  `registry_status` 保持 `calibration`。
- `docs/cli_ci_oracles.json` 相对 base byte-identical；JSON parse、dangling/ref、readiness、
  `git diff --check` 均通过。
- external CI-owned root 的 ownership marker 绑定 target commit `9ad45cf7`；第二个 candidate 的
  durable `CONTEXT_COMPACTED` 同一 payload 绑定 operation、accepted attempt、proposal manifest
  ref/digest、candidate/result 与真实 successful response identity。provider/model 来自 durable
  response fact，provider request id 为 `present`，client correlation 存在，敏感字段为零。

## 3. Finding adjudication

### MiMo

MiMo 报告无实质 finding，接受其 validation facts，但不接受 Residual Risk 1 中“scenario registry
reordering”的表述。JSON array 没有发生重排；unified diff 在删除 array 元素后按位置匹配后续对象，
造成文本上看似成片替换。Controller 的 scenario-id keyed 比较证明其余 436 个对象和值、顺序均未改变。
这不要求实现修改。

### DS F-001 — `implementation_findings_do_not_reduce_readiness=[]`

- 裁决：`rejected_as_missing_prior-artifact-trace`，不是产品、registry 或 S6 evidence defect。
- 直接证据：这 6 条 prompt finding 已由进入当前 `main` 的 PR #189 修复；当前仓库中的
  `docs/reviews/wu-cli-prompt-01-final-closeout-controller.md` 逐项给出 owner、1301 项受影响测试、
  owner coverage、完整 pyright、321/321 frozen real CLI replay 与最终 `pass`。
  `docs/reviews/code-review-20260731-205900.md` 又逐条独立 deepreview 六个 root cause 与 owner fix，
  结论为无实质 finding。S6 当前 CLI focused 605 项和 CLI/Service integration 1181 项再次通过。
- 语义判断：`implementation_findings_do_not_reduce_readiness` 只应保存当前仍存在、但经裁决不阻降的
  finding；已由 owner 修复并完成真实 replay 的 finding 不应继续列入。清空是 resolved truth 的
  机械投影，不是 S6 通过测试间接猜测。
- 处置：不修改 registry；本 adjudication 补齐 prior-artifact trace，finding 关闭。

### DS F-002 — dimension counts 缺少机械重算证据

- 裁决：`rejected_as_already_proven`。
- 直接证据：implementation artifact §4.2 / §6 已记录 object/ref/readiness validator 通过；Controller
  又从 base/current JSON 重新执行 exact object comparison，验证 17 删除、6 精确变更、442 总数与
  global calibration。dimension counts 均来自当前 scenario object 的机械聚合，不存在手工语义改写。
- 反例检查：DS 将 input-class count 变化解释为 P30 “重新编号”，但 P30 object 在 keyed comparison
  中完全不变；该解释不是 count owner 的直接证据。
- 处置：无实现或文档修改。

### DS F-003 — JSON 字段顺序使 canonical SHA-256 不可比

- 裁决：`rejected_as_factually_incorrect`。
- 直接证据：现有 canonical owner `workspace/tmp/build_prompt_scenario_registry.py::_canonical_digest`
  调用 `json.dumps(..., sort_keys=True, separators=(",", ":"))`。pretty JSON 中 object member 的展示
  顺序不会影响 canonical digest；digest 改变来自 inventory version 与实际 parser action 变化，
  不是字段排序漂移。
- 处置：不扩张为 harness serializer work。

### DS F-004 — `docs/cli_ci.md` 应新增 subsection heading

- 裁决：`rejected_as_style_preference`。
- 直接证据：新增规则紧接 `Registry-level readiness proof`，随后才进入原有 parser leaf 定义，
  其适用范围和上下文明确；不存在错误 owner、断链引用或不可导航的既有 heading。
- 处置：不为纯样式偏好制造 diff。

## 4. Validation 与 residual risks

S6 implementation validation 维持：full pyright 0；CLI/Service integration 1181 passed / 7 skipped；
Engine/Host 2957 passed / 1 skipped / 6 deselected，另 6 个 failure 精确为已在 S5 clean base 复现的
phase5 scheduler/test race。I0554 三条静态 owner proof 3 passed。两条 memory smoke 通过。

已分类 residual risks：

1. 行为项 29 已取得当前 target 的真实、同源、脱敏 compactor durable identity raw evidence；formal
   report renderer 仍锁定旧 target，因此不登记 accepted scenario，也不裁决 G06。
2. G01-G07 全部保持后续 CLI calibration obligation，global registry 继续 `calibration`。
3. `interactive_calibration_plan.py` 的旧 removed-option obligations 与 formal renderer target pin 是
   已知 harness owner gap；不在 S6 approved write scope，未用其输出伪造 ready。
4. awaiting entrypoint smoke 的 callback execution port drift 已复现，属于既有 harness/public-contract
   gap；未归因给 S6，也不越界修复。
5. 六条 phase5 race 是已分类 baseline failure，不是未分类 S6 regression。

## 5. Decision 与 next gate

两份独立 review 均未证明需要修改 S6 exact diff 的 correctness、stability 或 owner-boundary defect。
DS 四项均按上述直接证据关闭；没有 accepted finding，因此不派发 AgentCodex fix，也不制造 no-op fix
artifact。下一 gate 为 MiMo / DS 对 unchanged implementation diff、本 adjudication 与 residual-risk
分类执行独立 re-review；两路都通过后，Controller 才可创建 accepted S6 commit。
