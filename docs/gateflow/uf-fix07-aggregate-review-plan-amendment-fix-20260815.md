# UF-FIX07 aggregate review plan amendment fix

## Gate 元数据

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Gate：`fix`（after aggregate plan amendment review）
- 日期：2026-08-15
- 基线 HEAD：`1e04273f0688806bcc0746a0f2178a01d4bc092b`
- Reviewed target：`docs/gateflow/uf-fix07-aggregate-review-plan-amendment-20260815.md`
- Review artifacts（只读）：
  - `docs/reviews/plan-review-20260815-215532.md`
  - `docs/reviews/plan-review-20260815-220208.md`
- Scope：只修订 plan amendment 并记录 plan-review fix；不实施生产代码、测试或 README
- Decision：`PLAN AMENDMENT FIXED / PLAN RE-REVIEW PENDING`
- Blocking open question：无
- 下一入口：`plan re-review`
- Artifact path：`docs/gateflow/uf-fix07-aggregate-review-plan-amendment-fix-20260815.md`

## Scope 与 changed files

本 gate 只允许并实际包含：

- 修订：`docs/gateflow/uf-fix07-aggregate-review-plan-amendment-20260815.md`
- 新增：`docs/gateflow/uf-fix07-aggregate-review-plan-amendment-fix-20260815.md`

未修改生产代码、测试、README、原 accepted plan、goal confirmation、code/plan review artifacts、registry、oracle、scenario 或 frozen
evidence；未运行 UF-PF07/PF12，未 commit、push 或创建 PR。

## Reviewer findings / open questions 裁决

全部 reviewer findings 与 open questions 均接受，并已转化为 code-generation-ready plan 条款。最终状态使用 Gateflow fix 闭集；
“已纳入计划”表示对应 reviewer item 的计划缺口已修复，不表示生产行为已经实现。

| ID | Review item | 裁决 | Plan 修订 | 最终状态 | 纳入标记 |
| --- | --- | --- | --- | --- | --- |
| `215532-F1` | `_resolve_document_version` 未在函数签名处绑定 unsafe typed fingerprint 行为 | `accepted` | amendment §4.2 增加 exact branch pseudocode：existing meta + `identical_skip_safe=False` 无条件 increment；§4.5 绑定同一 typed result 的 data flow | `已修复` | `已纳入计划` |
| `215532-F2` | ambiguous replay 未冻结精确 version 值 | `accepted` | §5.2 精确断言 create `v1`、same-primary ambiguous replay `v2`、primary flip `v3` | `已修复` | `已纳入计划` |
| `220208-F1` | 缺少 safe multi-file whole-set cross-directory move test | `accepted` | §5.3 新增整组 move owner test：identity 全变但 descriptor/roles 不变，fingerprint safe 且相同，skip 保持 v1 | `已修复` | `已纳入计划` |
| `220208-F2` | old v1 multi-file -> v2 transition 缺独立 fixture | `accepted` | §5.4 要求测试内独立旧公式 seed previous meta，首次 v2 upsert update 到 v2；禁止 production legacy helper、dual-read 与 shim | `已修复` | `已纳入计划` |
| `220208-OQ1` | goal confirmation 与 amendment 的关系不明确 | `accepted` | §1.1 明确 amendment 不 supersede/reopen goal confirmation，只修正 implementation plan，并直接映射已确认目标 #3 | `已修复` | `已纳入计划` |
| `220208-OQ2` | validation 只覆盖 focused file，未恢复 aggregate gate | `accepted` | §8 恢复原 Slice 4 的 13-file suite、full pyright、六个修改生产文件逐文件 branch coverage `>=80%`，并单列 aggregate fix production coverage | `已修复` | `已纳入计划` |

所有 reviewer items 均已纳入计划；没有 rejected、deferred、needs-more-evidence 或 remaining open question。

## 修订后的精确决策

### 1. Skip 与 version 的 owner 分离

- `_can_skip_upload()` 只决定是否提前返回 `skipped`：保留 overwrite/previous/deleted gates，并额外要求 typed fingerprint
  `identical_skip_safe=True` 且 previous digest 等于 `.value`；它不计算版本。
- `_resolve_document_version()` 只决定未 skip、继续发布时的 canonical version：没有 previous meta 为 `v1`；只要 existing meta 且
  `identical_skip_safe=False`，无论 digest 是否相等或缺失，都从 previous version 无条件增长一次；safe 时保持既有 digest-change
  规则。它不读取 overwrite/deleted/primary pointer，也不再次决定 skip。
- `prepare_upload()` 在两个 helper 间传递同一个 `_UploadSourceFingerprint`；持久化只消费 `.value`，不持久化 safe bool。

这消除了 reviewer 指出的实现歧义：只改参数类型、仍按字符串比较的实现不再满足计划。

### 2. 版本状态测试闭环

- distinguishable primary flip：`v1 -> v2`，相同选择 replay 必须 skipped 并保持 `v2`。
- ambiguous descriptor：create `v1`，same-primary replay `v2`，primary flip `v3`。
- ambiguous state 恢复 non-ambiguous：descriptor 改变触发 `v4`，随后同选择 replay skipped、保持 `v4`。

因此无限 churn 被明确裁决为当前 ambiguous state 的 `accepted conservative boundary`；它不是持久化永久状态。一旦 primary descriptor
重新唯一，typed fingerprint 恢复 safe，完成一次变化 update 后即可恢复 identical-skip。

### 3. Move 与 version transition evidence

- safe multi-file 整组跨目录移动时，path-derived identities 全部变化，但 descriptors、roles 与 v2 digest 不变；owner test 必须断言
  skip/version 不增长并证明新 primary 能在新 original identities 中 exact 命中。skip 后旧 published tree 保持不变是预期行为。
- old v1 multi-file fixture 必须在测试内独立计算旧无角色 digest并 seed `previous_meta`；当前 v2 builder 不提供 legacy mode。
  第一次 v2 upsert 必须 update/version increment，之后同 v2 selection 才可 skip。任何 dual-read 或 compatibility shim 都违反计划。
- single-file 旧/新公式保持相同，继续 move identical-skip，不被 multi-file version transition 误伤。

### 4. Goal 与 aggregate validation

- goal confirmation 保持 binding 且未修改。Finding 1 修复的是目标 #3 已要求的 authoritative-primary 同源链路，不是扩大 goal。
- 实现 gate 必须跑原 Slice 4 的 13 affected test files、`python -m pyright dayu/ tests/ utils/`、六个原 UF-FIX07 修改生产文件的
  单文件 branch coverage `>=80%`。本 aggregate fix 唯一生产文件
  `dayu/fins/pipelines/docling_upload_service.py` 必须明确记录 `>=80%`。
- coverage gate 不授权修改 allowlist 外五个生产文件；失败必须按 stop condition 分类，不能借 coverage 扩 scope。

## Docs decision

本 plan-review fix 不修改 README。后续 aggregate implementation 仍只允许按 amendment §6 修订 `dayu/fins/README.md`：

- originals 按 primary-first role order 读取，companions 保持原请求相对顺序；
- role-aware multi-file fingerprint 排除 path identity/order；
- ambiguous descriptor 使用 conservative update；
- single-file move、rename/content 与 material fingerprint 行为保持。

## Validation

本 gate 仅修改 Markdown plan artifacts，按用户要求未运行 implementation pytest、pyright、coverage 或 UF-PF07/PF12。完成的静态核验：

1. 两份 plan-review artifacts 共四项 findings、两个 open questions 均有 `accepted` 裁决、plan 落点、Gateflow 最终状态与
   `已纳入计划` 标记；
2. amendment 在函数签名/data flow 两处绑定 unsafe version 分支，并区分 skip/version owner；
3. tests 明确包含 distinguishable `v1 -> v2 -> skip(v2)`、ambiguous `v1 -> v2 -> v3`、non-ambiguous recovery、multi-file
   whole-set move 与 independent old-v1 seed；
4. validation 完整列出 13 affected tests、full pyright 与六个单文件 coverage gates；
5. amendment 明确不 supersede goal confirmation，保持目标 #3；
6. artifact whitespace/scope 与只读输入 hash 在完成后复核。

## Residual risks / uncovered areas

| 风险或未覆盖项 | 分类 | Owner / destination |
| --- | --- | --- |
| ambiguous descriptor replay 持续 update/version churn | accepted conservative boundary | 当前 descriptor state；恢复 non-ambiguous 后可恢复 skip；不引入 path/order identity |
| old v1 multi-file 首次 v2 upsert 会 update/version increment | fixed in current aggregate fix plan | §5.4 owner test；禁止 dual-read/shim；迁移需求仍归 `UF-FIX08` |
| 旧 basename-based source schema 兼容/自动修复 | assigned to later work unit | `UF-FIX08` |
| 同 document 并发 writer | assigned to later work unit | `UF-FIX10` |
| fresh company meta warning | assigned to later work unit | `UF-FIX11` |
| optional real Docling 与 UF-PF07/PF12 未执行 | assigned to later evidence work | 当前禁止执行，等待独立授权 |
| registry/oracle/frozen evidence 仍为修复前观察 | assigned to later evidence work | 当前只读，等待独立授权 |

全部 residual risks 已分类，无 blocking open question。

## Completion status

- Findings：四项 accepted findings 全部 `已修复`、`已纳入计划`。
- Open questions：两项均 accepted 并 `已修复`、`已纳入计划`；remaining open question 为 0。
- Changed files：只限 amendment 与本 fix artifact。
- Implementation/docs/evidence：均未修改或执行。
- Decision：`PLAN AMENDMENT FIXED / PLAN RE-REVIEW PENDING`
- Next entry point：`plan re-review`
- 按用户要求在此停止；不实现、不提交、不建 PR。
