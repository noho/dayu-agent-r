# UF-FIX07 multi-file-primary-and-collision plan re-review adjudication

## Gate 元数据

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Gate：`re-review adjudication`
- 日期：2026-08-15
- 主控：AgentController
- Reviewed target：`docs/gateflow/uf-fix07-multi-file-primary-collision-plan-20260815.md`
- Fix artifact：`docs/gateflow/uf-fix07-multi-file-primary-collision-plan-fix-20260815.md`
- Scope：汇总四份 review、裁决全部 findings、关闭 plan review loop；不进入 implementation 或 commit
- 决策：`PLAN ACCEPTED / ACCEPTED PLAN COMMIT PENDING`
- Blocking open question：无
- 下一动作：AgentController 执行 `accepted plan commit`
- Artifact path：`docs/gateflow/uf-fix07-multi-file-primary-collision-plan-re-review-adjudication-20260815.md`

## 四份 review artifact 汇总

| Artifact | Gate / reviewer | 原结论 | 本次收敛 |
| --- | --- | --- | --- |
| `docs/reviews/plan-review-20260815-183830.md` | initial plan review / MiMo | `pass-with-risks`；MiMo-F1–F4 | F2–F4 accepted 后均已修复；F1 因 `_USAGE_MESSAGES` 直接代码事实与 finding 前提不符而证据失效 |
| `docs/reviews/plan-review-20260815-184718.md` | initial plan review / DS | `pass-with-risks`；DS-F1–F5 | F1–F4 accepted 后均已修复；F5 无实测 coverage failure，保留 80% gate 后证据失效 |
| `docs/reviews/plan-review-20260815-190003.md` | re-review / MiMo | `pass`；确认原 9 findings 全部关闭，无新 blocker | 接受 pass；未产生新 finding |
| `docs/reviews/plan-review-20260815-190711.md` | re-review / DS | `pass-with-risks`；原 9 findings 全部关闭，新增 DS-R1/DS-R2 两个低风险 finding | DS-R1 accepted并补 residual；DS-R2 rejected-with-reason，fresh-schema 边界已覆盖 |

## 全部 finding 最终状态

Gateflow fix/re-review 最终状态只使用：`未修复`、`已修复`、`部分修复`、`证据失效`。

| Finding | 最终裁决 | 关键落点或理由 | 最终状态 |
| --- | --- | --- | --- |
| MiMo-F1 固定 usage message 实现路径 | `rejected-with-reason` | 现有 `_USAGE_MESSAGES: Mapping[FinsUploadUsageCode, str]` 已统一承载固定串和模板串；新 closed codes 直接加入该 mapping，不需要第二套机制 | `证据失效` |
| MiMo-F2 `_PendingFileAsset` 字段链 | `accepted` | plan §6.6 与 Slice 3 明确 `_build_original_assets()`、`_build_pending_assets()`、`_store_upload_assets()` 的 filing/material exact field mapping | `已修复` |
| MiMo-F3 `file_uploaded` 用户投影 | `accepted` | filing event 使用 `original_filename`、storage 使用 identity；material event 保持 `asset.name`，有 exact tests | `已修复` |
| MiMo-F4 CLI/tool primary 文案同源 | `accepted` | `FinsUploadFormatTextProjection.filing_primary` 与 `.upload_tool_primary` 由同一规则片段产生并被两个入口机械消费 | `已修复` |
| DS-F1 delete 携 files 契约 | `accepted` | 新增 `FILES_NOT_ALLOWED_FOR_DELETE`；冻结 raw count → files error → primary error precedence，且在 resolve/duplicate/exists/role 前拒绝 | `已修复` |
| DS-F2 path identity 污染 fingerprint | `accepted` | filing fingerprint 只含 `original_filename`、`sha256`、`size`、`source`，排除 path identity；同 basename/同内容换目录 skip，改名 update | `已修复` |
| DS-F3 case/hardlink equality | `accepted` | resolve 后 exact path-string case-sensitive equality；不 `normcase`、不按 inode 合并，duplicate/membership 复用同一 helper | `已修复` |
| DS-F4 material identity failure scope | `accepted` | identity 与新 metadata 只用于 filing；material names、metadata、fingerprint、events、failure path 保持现状并做回归 | `已修复` |
| DS-F5 coverage 推测风险 | `rejected-with-reason` | 没有实测 failure；保留逐生产文件 80% gate，失败时 current scope 修复或 stop/escalate，不预先豁免 | `证据失效` |
| DS-R1 UF-A14/UF-PF03 residual 分类 | `accepted` | plan §12 已明确 frozen `UF-A14-delete-with-files-ignored` 因新 code stale；后续获授权 work unit 更新 `UF-PF03.blocked_by_finding_ids` 与 observation/evidence；本轮禁止改 registry/oracle/evidence | `已修复` |
| DS-R2 旧 fingerprint 首次重传 | `rejected-with-reason` | finding 以旧 `name`-key fingerprint durable state 为前提；本 work unit 明令 fresh schema、不兼容读取。旧状态首次重传、迁移或修复属于 `UF-FIX08`，不能转写成当前 README/生产 contract 的承诺 | `证据失效` |

汇总：11 个 findings 中，8 个 `accepted` 均为 `已修复`；3 个 `rejected-with-reason` 均为 `证据失效`；没有
`未修复`、`部分修复`、`deferred-with-owner` 或 `needs-more-evidence` finding。

## 最后两项裁决说明

### DS-R1：accepted，仅做 residual 分类

`FILES_NOT_ALLOWED_FOR_DELETE` 把 delete-with-files 从 frozen UF-A14 的“ignored / exit 0”改成 closed usage rejection；因此旧
observation 已 stale。当前 plan/implementation work unit 没有 registry/evidence 写权限，正确 owner 是后续获授权的
registry/evidence work unit。该 owner 必须：

1. 将 `UF-FIX07` 加入 `UF-PF03.blocked_by_finding_ids`；
2. 更新或重跑 UF-A14 对应 observation/evidence，使其与 accepted delete contract 一致；
3. 在此之前不得把旧 frozen observation 当作新 contract 的通过证据。

本次只在 plan §12 与 artifacts 中分类，不修改 `docs/cli_ci_scenarios.json`、`docs/cli_ci_oracles.json` 或任何 frozen evidence。

### DS-R2：rejected-with-reason，证据失效

DS-R2 的反例比较旧 `{"name": ...}` fingerprint serialization 与 fresh `{"original_filename": ...}` serialization，前提是读取并
延续旧 source durable state。但项目 schema 规则与本 plan 已明确：本 work unit 按 fresh schema 起步，不做旧 schema 兼容读取、
迁移、首次重传保证或自动修复。因而：

- 当前 identical-skip/update contract 只约束 fresh-schema state；
- 旧 source fingerprint 的首次重传、一次性 update 或 tree 修复属于 `UF-FIX08`；
- 本 work unit 不在生产代码添加兼容分支，不在 README 写迁移承诺，也不为旧状态增加测试；
- plan §12 的 existing-source/UF-FIX08 residual 已覆盖该边界。

该 finding 不揭示当前 approved scope 内缺失的实现契约，最终状态为 `证据失效`。

## Architecture、scope 与 blocker 裁决

- Raw/validated primary、CLI repeated selector、LLM tool primary、100 different files、duplicate normalized path、filing asset
  identity、original filename projection、derived identity、storage primary、`process_filing` 与 atomicity owner 均保持 plan 所定边界。
- DS-F4 的 filing-only scope narrowing 是主控已确认裁决；goal/oracle/frozen multi-file evidence 均指向 filing，因此 DS re-review
  提到的 goal wording 不构成需要重新 goal confirmation 的 blocker。
- Material、Host、Engine、runtime、storage/processor 生产代码仍不扩 scope。
- 四个 small slices、allowed files、tests/pyright/README/coverage gates 与 stop conditions 均保持 code-generation-ready。
- 无 blocking open question，无 unclassified residual risk，plan review loop 可以关闭。

## Changed files

- 修订：`docs/gateflow/uf-fix07-multi-file-primary-collision-plan-20260815.md`
- 修订：`docs/gateflow/uf-fix07-multi-file-primary-collision-plan-fix-20260815.md`
- 新增：`docs/gateflow/uf-fix07-multi-file-primary-collision-plan-re-review-adjudication-20260815.md`

未修改生产代码、测试、README、goal artifact、registry、oracle 或 frozen evidence；未执行 UF-PF07/UF-PF12；未 commit、push、
创建或推进 PR。

## Validation

本 gate 只修改 Markdown plan artifacts，因此不运行 implementation pytest、pyright 或 coverage。完成检查包括：

- 四份 review artifact 均已读取并列入汇总；
- 11 个 findings 均有裁决和 Gateflow 闭集最终状态；
- plan 顶部与 completion 状态、plan-fix 状态和本 adjudication 决策一致；
- plan §12 包含 UF-A14 stale、UF-PF03 后续 owner及当前禁止边界；
- DS-R2 只在 adjudication/residual ownership 中解释，未进入当前 README 或生产 contract；
- artifact whitespace checks 与 workspace status 检查通过；
- 没有生产代码、测试、README、registry/oracle/frozen evidence 变更。

## Docs decision

本 gate 不修改 README。Slice 4 只记录 fresh-schema 用户/开发者 contract，不记录旧 fingerprint schema 的迁移或首次重传保证；
该议题的 owner 是 `UF-FIX08`。

## Residual risks / uncovered areas

| 风险或未覆盖项 | 分类 | Owner / destination |
| --- | --- | --- |
| frozen UF-A14 与新 delete rejection contract 不一致 | `assigned to later work unit` | 后续获授权 registry/evidence work unit；更新 UF-PF03 dependency 与 observation/evidence |
| existing basename/name-key fingerprint source 的兼容、首次重传与自动修复 | `assigned to later work unit` | `UF-FIX08`；当前 fresh schema 不提供迁移承诺 |
| frozen multi-file scenarios 与真实 evidence 尚未按 `--primary` contract 重跑 | `assigned to later work unit` | 后续获授权 registry/evidence gate；当前禁止运行 UF-PF07/UF-PF12 |
| 同 document 并发 writer | `assigned to later work unit` | `UF-FIX10` |
| fresh company meta warning | `assigned to later work unit` | `UF-FIX11` |
| material collision/duplicate behavior | `assigned to later work unit` | 当前只做 non-regression，不新增 material 处理 |
| case alias/hardlink 按 exact path string 分开 | `accepted boundary` | 当前明确接受；改变需独立跨平台设计 |
| 逐生产文件 coverage 是否达到 80% | `covered by current slice` | Slice 4 实测；失败触发 stop condition，无预先豁免 |
| optional real Docling integration 可能 skip | `covered by later approved slice` | Slice 3 deterministic owner tests 为当前 correctness gate；真实 evidence 另行授权 |

全部 residual risk 已分类，无 blocker。

## Completion status

- Decision：`PLAN ACCEPTED / ACCEPTED PLAN COMMIT PENDING`
- Plan review loop：closed
- Findings：8 个 `已修复`，3 个 `证据失效`，无 open finding
- Docs：本 gate 仅更新 plan artifacts；README 未修改
- Commit：未执行
- Next entry point：AgentController 执行 `accepted plan commit`；本 agent 停止等待主控
