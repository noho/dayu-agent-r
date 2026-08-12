# UF-FIX09-S1 code review 综合裁决

## Gate 元数据

- gate：`code review adjudication S1`
- work unit：`UF-FIX09 shared-interruptible-docling-converter`
- slice：`UF-FIX09-S1`
- controller：`AgentController`
- base：`9527c6e0fd430082219b13daee31d300a8b44be4`
- frozen production SHA-256：`dab1d5ef4fe308bd4a73d9d983dde038fc304430b1d56a762c6c5a29e740cc86`
- frozen test SHA-256：`24e2928179bf4ce6384d3468b4a40333147ffc001ff43fef923aeeb23facaccb`
- AgentMiMo review：`docs/reviews/code-review-20260812-165218.md`
- AgentDS review：`docs/reviews/code-review-20260812-164911.md`
- adjudicated at：`2026-08-12T16:54:33+08:00`
- completion status：`S1 ACCEPTED — READY FOR S1 COMMIT`

## Scope 与直接验证

两路 reviewer 基于同一 frozen digest 独立执行 `/deepreview`，均复核 34 项 owner tests、focused
pyright 与 93% 单文件覆盖率。总控完整读取两份 artifact，并复核
`dayu.documents.docling_runtime` 的 lazy third-party import、runtime shielded cleanup/checkpoint
语义及 S1 tests 的 failure mapping。

## Accepted findings

1. **temp 创建/输入写入失败缺少 owner-level 回归（AgentDS F2）— accepted / fixed in current
   slice。** 增加 deterministic tests：`mkdtemp` 失败时不得创建 handle，返回
   `IPC_PROTOCOL`；`write_bytes` 失败时仍删除已创建 temp，且若 rmtree 同时失败应由 `CLEANUP`
   按既定优先级覆盖并保留原失败链。只允许改测试，生产逻辑已有正确分支。
2. **terminate/kill primitive 普通异常缺少回归（AgentDS F3）— accepted / fixed in current
   slice。** 增加 typed fake handle failure injection：terminate 抛异常、terminate 未退出后 kill
   抛异常，都必须记录对应 FAILED phase、最终映射 `CLEANUP`、仍调用 handle close 与 temp cleanup。
   只允许改测试。

## Rejected findings

1. **`_close_handle` while-loop 无上界（AgentMiMo F2、AgentDS F1）— rejected-with-reason。**
   循环只在当前 task 收到 `CancelledError` 时重入；普通 close failure立即返回。runtime
   `close()` 把 cleanup 放进 shielded task，内部 signal/join 均使用 bounded grace，queue cleanup
   由独立 checkpoint 推进。增加任意重试次数/总时限会在 shielded cleanup 尚未完成时放弃，随后
   删除 temp 并向上返回，反而破坏用户要求的 join/reap/close 与 descendant cleanup。若 runtime
   自身违反其 bounded contract，应在 runtime owner 修复，而非 Fins 层引入第二 timeout。
2. **测试隐式依赖 Docling 安装（AgentMiMo F1）— rejected-with-reason。**
   `dayu.documents.docling_runtime` 的 Docling imports 位于 `TYPE_CHECKING` 或函数内，模块和异常类
   在未安装 Docling 时可 import；spawn probe 在 child 内替换 conversion function，未执行真实
   third-party import。当前 34 项是 deterministic owner tests；真实 Docling 依赖另由 S2/S3
   integration gate验证。
3. **spawn probe 依赖 pytest（AgentDS F6）— rejected-with-reason。** 这是 pytest 测试 target，
   child 由同一个已激活 test environment spawn；pytest 是该入口的显式而非隐式依赖，不会进入
   production artifact。改用另一个 mock library不改变任何行为或风险。
4. **`wait_result=None` 防御分支（AgentDS F4）— rejected-with-reason。** 当前主状态机在
   `request_cancelled=False` 时不会生成该组合；保留防御性 fail-closed 已足够，不为不可达内部
   状态制造测试 seam。
5. **closed JSON 每个私有递归分支（AgentDS F5）— rejected-with-reason。** reviewer 已直接验证
   行为正确，生产 owner 总覆盖率 93%；为私有实现逐行追 coverage 不增加 contract 证据。真实
   success/serialization failure 已从 child target 边界覆盖。

## Open questions

无 blocking open question。

## Docs decision

S1 尚未迁移任何 caller 或用户可见行为；README 更新归 S2/S3。当前只新增 Gateflow/review
artifact，不修改 README。

## Residual risks

| 风险 | 分类 | owner / 下一步 |
| --- | --- | --- |
| 两个 accepted test gaps 尚未修复 | fixed in current slice | AgentCodex S1 fix |
| 修订测试是否保持 frozen production digest | covered by S1 code re-review | AgentMiMo + AgentDS |
| 旧 CN runner 与新 owner 暂时并存 | covered by later approved slice | S2 migration/delete |
| 真实 Docling 未在 S1 执行 | covered by later approved slice | S2 integration / S3 UF-PF09 |
| 非 POSIX descendant guarantee | assigned to later work unit | runtime platform work unit |

## Completion

AgentCodex 只能修改 `tests/fins/test_docling_process_converter.py` 闭环两项 accepted test gap；生产
文件不得修改。修订后重新冻结两个 digest，并同时交两路 reviewer re-review。未闭环前不得创建
S1 acceptance commit。

## Re-review acceptance

- 修订 production SHA-256 仍为
  `dab1d5ef4fe308bd4a73d9d983dde038fc304430b1d56a762c6c5a29e740cc86`；生产代码未因 test-gap
  finding 改动。
- 修订 test SHA-256 为
  `10028e22186162c8a5aab271a490323a5a2bd4bd451baca07c7269c92130c861`。
- AgentMiMo re-review：`docs/reviews/code-review-20260812-170513.md`，结论 `pass`，accepted gaps
  `2/2`，new/unresolved `0`。
- AgentDS re-review：`docs/reviews/code-review-20260812-170314.md`，结论 `pass`，accepted gaps
  `2/2`，new/unresolved `0`。
- 独立验证：owner tests `39 passed`；四文件 focused regression `97 passed`；AgentDS 额外 Fins
  regression `1196 passed, 1 skipped`；full pyright `0 errors, 0 warnings`；owner coverage `95%`；
  `git diff --check` 无告警。
- README decision：S1 尚未迁移 caller/用户行为，README 更新归 S2/S3。
- 最终裁决：无未分类风险、blocking question 或 accepted finding 未闭环；允许创建 S1 local
  acceptance commit，下一入口为 S2 implementation。
