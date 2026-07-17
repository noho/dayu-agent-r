# WU-SEMANTIC-OWNERSHIP-01 / R11-S1 checkpoint stop Controller adjudication

## 1. Verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal sub-WU / attempted slice：R11 / `R11-S1 — Fins OLD batch classification owner`。
- accepted-plan commit：`f7b452f992b4797b32fea7c6f7212b5ec4345ec1`。
- AgentCodex stop evidence：
  `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-s1-implementation-codex.md`，
  172 lines / 9,801 bytes / SHA-256
  `a01e188e5acc4eae9e75e0106014d5af7b0c2cb697ab507e42812ac503b5258c`。
- Controller verdict：`STOP VALID / ACCEPTED PLAN-BOUNDARY FINDING R11-IMP-BF01`。
- product/test diff：empty；staged tree：empty；current full pyright：0 errors。

S1 未实现、未通过 checkpoint，也不得进入原 S2。当前必须先做 plan-only atomic cutover amendment，再经双路
complete plan re-review；不授权 product/test implementation、stage/commit、R12、push 或 PR。

## 2. Direct root-cause evidence

Accepted plan §5.1 要求 Fins 用 `UploadBatchFilingEntry`、`UploadBatchMaterialEntry`、
`UploadBatchSkippedEntry`、`UploadBatchPlan` 替换 generic contract；plan 只保留
`recognized_entries/material_entries/skipped_entries`，不得保留 generic `command_name`、`entries`、multi-file
`files` 或兼容 alias。§5.3 又要求 entry type 是唯一 command discriminator。

CURRENT `dayu/cli/commands/fins.py` 则在原 S2 owner 中静态依赖旧 contract：

- import `UploadBatchPlanEntry`；
- 读取 `plan.entries`；
- `_render_upload_batch_plan(tuple[UploadBatchPlanEntry, ...])`；
- 读取 `entry.command_name`、`entry.files` 及 generic optional material fields；
- 把这些字段投影成待删除 JSON argv protocol。

原 S1 exact allowlist 只有 Fins owner 与 owner test，明确禁止修改该 consumer；同时 checkpoint 要求 full pyright
从当前 `0 errors` 保持零新增/扩散。故：

1. 正确替换 producer contract 会立即让只读 CLI consumer import/attribute/type contract 失效；
2. 保留旧类型、字段、property、alias、`__getattr__`、dead dataclass、union wrapper 或 adapter 只为跨 checkpoint，
   都是 AGENTS 和 accepted plan 明令禁止的 compatibility seam；
3. 放弃 full pyright 或容忍 transient broken tree 又直接违反 AGENTS 与 plan validation gate。

这是 producer-consumer atomic contract cutover 的直接逻辑矛盾，不是测试、fixture、日志或 implementation 技巧问题。

## 3. Finding adjudication

### R11-IMP-BF01 — 原 S1/S2 checkpoint 不能形成合法中间 tree

- severity：BLOCKER（plan sequencing / slice boundary）。
- status：ACCEPTED / OPEN，等待 plan amendment。
- owner：R11 plan 的 producer-consumer cutover slice boundary。
- 最窄修复：把原 S1 Fins producer 与原 S2 CLI consumer/renderer 合并为同一个 atomic implementation slice；
  可保留 Fins-first、CLI-second 两个 ordered work packages，但二者之间不得建立 acceptance/checkpoint/commit，只有
  producer+consumer 全部 cutover 后才运行 full validation 与 Controller checkpoint。
- 不改变产品裁决、semantic owner、cumulative allowlist、S2→S1 gap return 的 owner 原则或 S3 packaging 范围。
- 原 S3 可成为第二个 slice；R11 总 slice 数从 3 降到 2，符合 umbrella optimization 的依赖/可验证边界。

## 4. Rejected alternatives

- 拒绝保留旧 `UploadBatchPlanEntry/Result`、`entries/command_name/files` 或 compatibility property/alias。
- 拒绝在 CLI 加 loose parsing、fallback、`hasattr/getattr`、旧/new schema dual reader 或 downstream repair。
- 拒绝跳过/推迟 full pyright、把 transient broken tree 当 checkpoint pass，或只跑 owner tests。
- 拒绝修改 Service/storage/runtime、增加跨层 adapter、创建新 sub-WU，或把 finding 转 residual。
- 拒绝改变已裁决的 Fins unique owner、current CLI projection、JSON protocol 删除与 executable script目标。

## 5. Plan amendment requirements

AgentCodex 只可修改 accepted R11 plan 和自己的 plan-amendment evidence，必须：

1. 全文把三-slice state machine 改成两个 slices：atomic Fins+CLI cutover → packaging/README/Windows gate。
2. 原 §5/§6 可保留为同一 slice 内两个 ordered work packages，但删除二者之间的 checkpoint/next-slice/stop
   语义；atomic checkpoint 只在两者都完成后发生。
3. 精确合并原 S1+S2 allowlists、tests/smokes/coverage/pyright/Ruff/scans；不能降低任何 gate。
4. 将原 §9.1 owner-gap return 重写为 atomic slice 内 Fins owner targeted correction：不得创建兼容 seam，必须在同一
   slice 重新跑 producer+consumer cumulative validation。
5. 更新 §1、§4、§5/§6 stop text、§9.1—§9.4、acceptance checklist 与所有“三 slices/S1→S2→S3”引用；
   S3 packaging 内容本身不扩 scope。
6. 明确 code review 仍只在两个 implementation slices 全部完成后对 cumulative diff 执行一次；不增加中间 commit。
7. Windows release blocker、Ruff 0.15.11 baseline、coverage、security/deferred/no-touch 与 no-push边界保持不变。

Plan fix 后必须由 Controller 完整读取，并由 AgentMiMo/AgentDS 对完整 amended plan 做双路 complete re-review；不能只审
delta。只有 R11-IMP-BF01 closed 且无新 accepted finding 后，才可做 accepted-plan amendment commit 和重新授权实现。

## 6. Workspace/gate truth

- `dayu/fins/upload_batch.py` 与 `tests/fins/test_upload_batch.py` locks 未变，diff empty。
- Controller control/auth artifacts 未被 Agent覆盖；Agent 只新增 stop evidence。
- full pyright independently reproduced：`0 errors, 0 warnings, 0 informations`。
- accepted/open finding：1 (`R11-IMP-BF01`)；blocker：1 plan-boundary blocker；actual residual：0。
- next gate：AgentCodex plan-only atomic-cutover amendment。

READY_FOR_R11_PLAN_BOUNDARY_FIX
