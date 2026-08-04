# Interactive Conversation Memory closure F10：code-review fix artifact

## Gate

- Gate：Gateflow code-review fix。
- Work unit：Interactive Conversation Memory closure F10。
- Base：accepted F09 commit `d04f7531f3a7bfef2de004afbb94b2d607704b36`；当前未提交 F10 diff。
- Reviewed artifacts：
  - `wu-interactive-memory-closure-f10-code-review-mimo.md`
  - `wu-interactive-memory-closure-f10-code-review-ds.md`
- Contract truth：accepted F10 plan、plan-amendment controller、fix-controller 与 controller adjudication。
- Decision：MiMo PASS 证据成立；DS F1–F4 关闭证据成立；DS 两个 low defense-in-depth observation 均
  `rejected-with-reason`，不构成 accepted contract gap，不修改 production/tests。
- Current gate / next entry point：re-review handoff。
- Artifact path：`docs/reviews/wu-interactive-memory-closure-f10-code-review-fix-codex.md`。

## 第一性原理判定

本 gate 要判断的不是“能否再加一层检查”，而是当前 owner chain 是否存在可复现的 correctness gap。
accepted amendment 已固定最小分层：

1. compact-material/pipeline 在持有 raw source snapshot 时，建立并验证
   `block_id -> (canonical refs, final-pack digest)` exact identity；
2. operation 不持有 raw snapshot，也不得从 prompt label、ordinal、kind、section 或 block-id 字符串反推；
   它验证 root/transient partition，以及 proof 与实际 selected pack 的 refs/digest multiset；
3. `_single_block_segment_selection` 只能从 root proof 取 entry，`_operation_pass_requests` 对每 pass 做
   per-block-id exact-root-subset、无重叠、无遗漏和 per-pass pack 校验；
4. selected proof 明确不增加 kind/section/label，不把完整 snapshot 塞入 request，不建立重复 owner。

因此，只有能在上述正式 producer/call path 中造成错误业务材料、partial group、错误 durable boundary、provider
越过应有 guard 或多 terminal 的反例，才是本 slice 的 correctness finding。仅证明某一层没有重复上游的全部知识，
不是 gap。

## DS low observation 逐项裁决

### DS-1：operation 使用 refs/digest sorted multiset

- Review observation：若两个都已 selected 的 block A/B 在 proof 中整体交换 refs+digest，sorted multiset 不变，
  operation 单独无法发现 block-id association 被交换。
- 裁决：`rejected-with-reason`；机械观察成立，但 correctness premise 不成立。

直接证据与反例分类：

1. pipeline `_validate_segment_against_source_snapshot` 从同一 raw snapshot 按 selected ids 重建
   `SelectedBlockProvenance`，并与 selection tuple 逐字段、逐顺序比较；正式 producer path 中 A/B association
   swap 在 request 进入 operation 前已失败。
2. operation 的 material pack 按 trace/evidence/answer section 重排并产生 prompt-local labels，pack block 按 accepted
   contract 不携带 source `block_id`。因此 operation 可诚实验证的 boundary identity 正是保留重复项的
   `(canonical_source_refs, packed_content_digest)` multiset；按 selection 顺序比 pack 顺序会依赖错误的 section/
   ordinal 假设。
3. 若只在“均已 selected”的 A/B 之间交换完整 proof values，actual pack 集合、root selected/excluded 二分、
   turn-group completeness、source boundary 与 durable candidate coverage 都不改变；这不是错误业务事实、丢失、重复或
   partial durable truth。
4. 若把 selected A 替换为 excluded B，或让 pack 实际包含另一组，proof/pack multiset 会改变，现有 operation guard
   fail closed；`test_whole_group_swap_proof_fails_before_provider` 已覆盖等数量完整 group swap。
5. transient path 不只用 multiset：`_operation_pass_requests` 还按 `block_id` 读取 root entry，并对 refs/digest 做
   frozen dataclass exact equality；全 pass 合并后再验证 root proof 无重叠、无遗漏。

DS 建议的“per-block-id pack compare”在当前类型中没有真实比较键。实现它只能：

- 把 block id/kind/section/label 加进 pack 或 proof，违反 accepted 最小 schema；
- 依赖 prompt label/section ordinal/tuple order 反推，属于 amendment 明确禁止的 surrogate proof；或
- 把 raw source snapshot 塞入 operation request，复制 pipeline owner并扩大 request。

这些动作增加耦合，却不能关闭新的业务正确性反例，因此不实施，也不新增会固化 plan 外强约束的测试。

### DS-2：transient snapshot validator 不接收 root segment

- Review observation：`_validate_segment_against_source_snapshot` 对 transient scope 验证 source-snapshot identity 与
  非空 root digest，但不单独接收 root selection 做 subset 比较。
- 裁决：`rejected-with-reason`；这是已接受的分层，不是下游补偿或验证缺口。

直接证据：

1. snapshot validator 对 root/transient 共用的职责已完整：selected/excluded ids 必须属于 snapshot，完整 memberships
   必须与 snapshot 相等，selected proof 必须由 snapshot 对 selected ids 机械重建后精确相等。只有 root scope额外拥有
   `selected ∪ excluded = snapshot` 的 root partition 语义。
2. transient 的 root relationship 由唯一持有 root request 的 producer
   `_single_block_segment_selection` 产生：block id 必须在 source material 中，且必须在 root
   `selected_block_provenance` 中精确出现一次；entry 直接取 root proof，不重算，并绑定 root selection digest。
3. provider boundary `_operation_pass_requests` 再验证 transient scope、root digest exact equality、memberships equality、
   per-block provenance exact-root-subset、block-id 无重叠、全体 block-id 无遗漏、source boundary exact partition，并先调用
   `_validate_operation_selected_pack` 校验每个 pass 自身 pack。
4. 绕过 producer 手工注入一个“snapshot 中存在但 root 已排除”的 transient block，会在 operation 的
   `root_provenance_by_id.get(block_id) is None` 分支 provider 前失败；
   `test_reactive_pass_provenance_tamper_fails_before_provider` 已覆盖 exact-root-subset 与 per-pass pack 两类篡改。

给 snapshot validator 增加 `root_segment` 参数会让 pipeline 的 source identity validator复制 transient/root relationship
owner；当前没有第二个 transient producer，也没有绕过 operation 的 provider path。故不扩大函数签名、不建立重复 owner、
不补冗余测试。

## MiMo PASS 项复核

| 项目 | 独立复核 | 直接证据 |
|---|---|---|
| semantic owner / compat | PASS | 单一 `_packed_content_digest`；无 fallback、shim、loose parser或下游补偿 |
| schema / LLM surface | PASS | proof 与双 digest 仅 Host-internal；repair projector只含 action/issues |
| atomic selection / budget | PASS | stable atomic units、collective precedence、真实 block item count、strict prefix |
| provenance fail closed | PASS | snapshot exact proof；operation pack multiset；transient per-id exact root subset |
| root/transient partition | PASS | root selected/excluded exact snapshot partition；passes 对 root无重叠遗漏 |
| same-text/same-ref | PASS | packer无 dedup；same-text/different-ref保留；same-ref pipeline/operation拒绝 |
| excluded mapping | PASS | key-sort copy + `MappingProxyType`；JSON/digest canonical order同源 |
| repair binding | PASS | request/source-boundary 双 digest；dispatcher clear + operation defensive guard |
| F09 fixture migration | PASS | 只迁移 compactor manifest fixture required descriptor；无 production compat |
| Memory/RunInput/LLM 隔离 | PASS | 下游未改；governance proof/digest不进入 LLM-facing material |
| current anchor duplicate owner | PASS | duplicate section owner跳过 anchor；canonical-ref overlap由pipeline/operation独占 |
| initial selection | PASS | 无 raw snapshot路径从 final pack读取 proof；previous/current reasons完整 |

MiMo residual 中 transient snapshot validator 不重复 root subset 的事实存在，但其 own artifact 已正确判定：exact partition
由 operation owner保障，不是 finding。

## DS F1–F4 关闭证据复核

| Finding | 状态 | 关闭证据 |
|---|---|---|
| F1 evidence final-pack digest | 已修复 | `_packed_content_digest`区分 ordinary/evidence，四个指定调用点直接复用；source digest语义不变 |
| F2 transient exact subset | 已修复 | single-block producer只取 root entry；operation逐项 exact subset，并验证无重叠遗漏与每-pass pack |
| F3 excluded mapping immutability | 已修复 | constructor key-sort copy 后以只读 mapping保存；外部 mutation与直接写入 tests均拒绝 |
| F4 selected packer dedup | 已修复 | dedup helper删除；packer一项不漏；same-text保留、same current ref双层fail closed |

DS code review 的其余 adversarial PASS 证据与当前代码一致。DS residual 3（initial selection 使用 prompt-local labels）是
无 raw source snapshot 的 explicit initial helper contract，未与 recovery selection 混用；属于当前已验证边界，不升级为本
slice finding。正式 provider scenarios 与全树 Ruff debt维持 implementation artifact中的既有分类。

## Changed files

本 fix gate 不修改 production、tests 或稳定事实文档；只新增本 durable fix artifact。两项 observation均没有可复现
correctness反例，修改代码反而会扩大 schema/函数签名或复制 owner。

## Validation

- F10 focused owner suite：`337 passed, 1 skipped in 3.40s`；skip 为明确禁跑的 opt-in real compactor smoke。
- 全仓 pyright：724 files analyzed，0 errors、0 warnings、0 informations。
- F10 精确 production/tests pathspec Ruff check：通过。
- `git diff --check`：通过。
- 三份 frozen baseline digest 保持不变：
  - CLI oracles：`da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201`
  - CLI scenarios：`7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093`
  - F08–F10 finding baseline：`95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08`
- 未运行五条正式 CLI scenarios，未 commit。

## Residual risks / uncovered areas

- DS-1、DS-2：`rejected-with-reason`；不是 deferred correctness risk，不需要 future owner。
- 真实 provider 与五条正式 CLI scenarios：`covered by later approved evidence/readiness gate`。
- 全树 Ruff lint/format accepted-base debt：`assigned to later work unit`；F10精确 pathspec必须继续为green。
- code-review fix 尚待独立 re-review：`covered by current Gateflow re-review gate`。

没有 unclassified residual risk，没有 blocking open question。

## Completion status

Code-review fix audit 完成；无代码修复需要。当前停在 re-review handoff，不提交，不运行正式 scenarios。
