# UF-FIX07 multi-file-primary-and-collision plan fix

## Gate 元数据

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Gate：`fix`（after plan review，已由 re-review 收敛）
- 日期：2026-08-15
- 主控：AgentController
- Reviewed target：`docs/gateflow/uf-fix07-multi-file-primary-collision-plan-20260815.md`
- Review artifacts：
  - `docs/reviews/plan-review-20260815-183830.md`
  - `docs/reviews/plan-review-20260815-184718.md`
  - `docs/reviews/plan-review-20260815-190003.md`
  - `docs/reviews/plan-review-20260815-190711.md`
- Scope：记录 plan fix 及 re-review 最终收敛；不实施生产代码、测试或 README
- 决策：`PLAN ACCEPTED / ACCEPTED PLAN COMMIT PENDING`
- Blocking open question：无
- 下一入口：AgentController 执行 `accepted plan commit`
- Artifact path：`docs/gateflow/uf-fix07-multi-file-primary-collision-plan-fix-20260815.md`

## Changed files

- 修订：`docs/gateflow/uf-fix07-multi-file-primary-collision-plan-20260815.md`
- 修订：`docs/gateflow/uf-fix07-multi-file-primary-collision-plan-fix-20260815.md`
- 新增：`docs/gateflow/uf-fix07-multi-file-primary-collision-plan-re-review-adjudication-20260815.md`

未修改生产代码、测试、README、goal artifact、oracle、scenario registry 或 frozen evidence；未 commit、push、创建或推进 PR；
未执行 UF-PF07、UF-PF12。

## Finding 裁决与最终状态

最终状态仅使用 Gateflow 闭集：`未修复`、`已修复`、`部分修复`、`证据失效`。

| Finding | 主控裁决 | 裁决理由 | 写入 plan 的修订 | 最终状态 |
| --- | --- | --- | --- | --- |
| DS-F1 delete 携 files 契约缺失 | `accepted` | delete files 不能继续走 path/role 校验后被忽略；Fins static admission 是组合错误 owner | 新增 `FILES_NOT_ALLOWED_FOR_DELETE` closed usage code 与固定消息；冻结 `TOO_MANY_FILES`（若命中）→ files-not-allowed → primary-not-allowed precedence；files error 在 resolve/duplicate/exists/role 前，files+primary 时 files 优先；Slice 1 增加 exact code/message 与不可达副作用测试 | `已修复` |
| DS-F2 path identity 污染 fingerprint | `accepted` | storage collision identity 与 identical/update 判定不是同一事实；path-derived identity 进入 fingerprint 会无意改变 skip 语义 | filing fingerprint 明确只由 `original_filename`、`sha256`、`size`、`source` 构成并排除 identity/path/order；同 basename/同内容换目录仍 skip，改名仍 update/version increment；补 Slice 3 tests 与 Slice 4 README 决策；material fingerprint 保持现状 | `已修复` |
| DS-F3 case/hardlink equality 未冻结 | `accepted`（clarity） | duplicate 与 membership 必须使用同一可跨入口复现的相等规则，不能暗中依赖 inode 或宿主大小写行为 | normalized equality 冻结为 `resolve(strict=False)` 后 exact path-string、case-sensitive equality；不 `normcase`、不按 inode 合并 case alias/hardlink；加入 boundary 与 tests | `已修复` |
| DS-F4 material identity failure contract 不清 | `accepted`（scope narrowing） | UF-FIX07 的 collision-free storage schema 只需解决 filing；把它扩到 material 会引入未确认行为与新错误契约 | filing-only identity/`original_filename`/`derived_from`；material asset names、derived names、files metadata、fingerprint、events、failure path 保持现状；只做 material regression tests，不新增 material duplicate 处理 | `已修复` |
| DS-F5 coverage 可能失败 | `rejected-with-reason` | review 只有代码规模推测，没有实际 coverage failure；预设豁免会削弱项目硬 gate | 保留每个修改生产文件 `--fail-under=80`；明确无预先豁免，实测失败必须在 current scope 修复或停止交主控，禁止范围蔓延 | `证据失效` |
| MiMo-F1 固定消息实现路径不清 | `rejected-with-reason` | 直接代码证据表明现有 `_USAGE_MESSAGES: Mapping[FinsUploadUsageCode, str]` 已同时承载固定字符串与需格式化字符串，`fins_upload_usage_failure()` 统一读取；无需第二套 mapping/wrapper | plan 明确六个 code 的固定字符串直接加入现有 `_USAGE_MESSAGES`，非 file usage 分支直接消费，不新增 `_FIXED_USAGE_MESSAGES` 或消息 facade | `证据失效` |
| MiMo-F2 `_PendingFileAsset` 字段传递不清 | `accepted`（clarity） | 新 metadata 必须从唯一构造点产生，不能依赖下游 fallback | §6.6 table 与 Slice 3 exact changes/tests 写明 `_build_original_assets()`：filing original identity/basename/None；`_build_pending_assets()`：filing derived identity/继承 basename/exact `derived_from`；material 两字段显式 `None` | `已修复` |
| MiMo-F3 `file_uploaded` 事件映射不清 | `accepted`（clarity） | 用户事件必须显式消费可读投影，不能误暴露 storage digest | §6.6 table 与 Slice 3 写明 `_store_upload_assets()`：filing event `name=asset.original_filename`、source 保持；storage name/URI 仍 identity；material event 保持 `asset.name`；补 exact assertions | `已修复` |
| MiMo-F4 CLI/tool primary 文案同源不足 | `accepted` | CLI 与 LLM-facing schema 必须机械消费共享 owner，避免两入口语义漂移 | `FinsUploadFormatTextProjection` 新增 `filing_primary` 与 `upload_tool_primary`；CLI/tool 各自机械消费；两个字段由同一关键规则片段组成并测试单文件、多文件、membership、顺序、delete/material 规则同源 | `已修复` |

## Re-review 新 finding 收敛

| Finding | 主控裁决 | 裁决理由与落点 | 最终状态 |
| --- | --- | --- | --- |
| DS-R1 UF-A14/UF-PF03 residual 分类缺口 | `accepted` | plan §12 新增 residual：`UF-A14-delete-with-files-ignored` 因 `FILES_NOT_ALLOWED_FOR_DELETE` 已 stale；后续获授权 registry/evidence work unit 必须把 `UF-FIX07` 加入 `UF-PF03.blocked_by_finding_ids` 并更新相应 observation/evidence；当前仍严禁改 registry/oracle/frozen evidence | `已修复` |
| DS-R2 旧 fingerprint 首次重传未承诺 | `rejected-with-reason` | 该反例必须从旧 `name`-key source fingerprint 开始，但本 work unit 已按 fresh schema 明确排除旧 schema 兼容；旧状态首次重传/迁移属于 `UF-FIX08`，不能写成当前 README 或生产 contract 的承诺。plan §12 既有 fresh-schema residual 已覆盖，未改变 Slice 4 README 范围 | `证据失效` |

## 其它主控要求的落点

- registry 证据更正为 `docs/cli_ci_scenarios.json` 中的 `UF-FIX07` finding record，不再称为 scenario id。
- `tests/fins/test_fins_service_runtime.py` 已加入 Slice 1 allowed tests、Slice 1 pytest/pyright、Slice 4 affected validation 与
  overall allowed files。
- 100 上限仍以 raw entries 计数，100 个 different resolved path inputs 可发布 100 originals + 1 filing derived，101 个在
  workspace state read 前拒绝。
- storage `primary_document`、`process_filing`、publication atomicity 与失败零部分发布边界保持原 plan，不修改正确下游 owner。
- plan 仍按四个 small slices 执行，allowed files、禁止文件/动作与 stop conditions 除上述必要收紧外保持不变。

## Validation

本 gate 只修改 Markdown plan artifacts，因此未运行 implementation pytest、pyright 或 coverage，也未执行 UF-PF07/UF-PF12。
已完成以下静态核验：

- 两路 plan review 的 9 个 finding 与 DS re-review 的 2 个新 finding 均有 `accepted` 或 `rejected-with-reason` 裁决及
  Gateflow 闭集最终状态；
- 原 plan 包含 delete exact precedence、filing-only identity、fingerprint 公式、case-sensitive equality、projection 字段、
  三个 asset 方法映射、material regression、service runtime test、80% gate 与 stop condition；
- `rg -c '^\| (DS|MiMo)-F'` 返回 `9`；
- 两份 untracked artifact 分别执行 `git diff --no-index --check /dev/null <artifact>`，均无 whitespace-error 输出（exit 1
  仅表示存在预期新增内容）；tracked diff 的 `git diff --check` 通过；
- `git status --short` 只列出本 work unit 的 goal/plan/review Markdown artifacts，没有生产代码、测试、README、
  oracle/scenario/frozen evidence 变更。

## Docs decision

本 fix/re-review gate 不修改 README。实现 Slice 4 仍只记录 fresh-schema 当前 contract：filing fingerprint 不含 path identity、
同 basename/同内容换目录仍 identical-skip、改名仍 update，以及 material 行为未改变；不写旧 `name`-key fingerprint 的迁移或
首次重传承诺，该边界属于 `UF-FIX08`。

## Residual risks / uncovered areas

| 风险或未覆盖项 | 分类 | Owner / destination |
| --- | --- | --- |
| existing basename-based source schema（含旧 `name`-key fingerprint）兼容、首次重传或修复 | `assigned to later work unit` | `UF-FIX08`；当前只承诺 fresh schema |
| 同 document 并发 writer | `assigned to later work unit` | `UF-FIX10` |
| fresh company meta warning | `assigned to later work unit` | `UF-FIX11` |
| frozen scenarios/evidence 尚未按新 `--primary` contract 重跑 | `assigned to later work unit` | 后续获授权 registry/evidence work unit；本 gate 禁止修改或执行 |
| frozen UF-A14 仍记录 delete-with-files ignored | `assigned to later work unit` | 已 stale；后续获授权 work unit 更新 `UF-PF03.blocked_by_finding_ids` 与 observation/evidence，当前禁止修改 |
| case alias/hardlink 按不同 exact path string 处理 | `accepted boundary` | 本 work unit 明确接受；若改变需独立跨平台 identity 设计 |
| material collision/duplicate 行为保持现状 | `assigned to later work unit` | UF-FIX07 只做 material non-regression；若要改变需新 goal confirmation |
| optional real Docling integration 可能 skip | `covered by later approved slice` | Slice 3 fake-converter owner tests 是本轮 correctness gate；真实 evidence 另行授权 |
| coverage 是否实际达到逐文件 80% | `covered by current slice` | Slice 4 实测；失败即触发 stop condition，无预先豁免 |

全部 residual risk 已分类，无 blocking open question。

## Completion status

- Decision：`PLAN ACCEPTED / ACCEPTED PLAN COMMIT PENDING`
- 全部 findings：11 个；8 个 `accepted` 均为 `已修复`，3 个 `rejected-with-reason` 均为 `证据失效`
- Docs：只改 plan artifacts，README decision 已保留到 Slice 4
- Commit/PR/evidence：均未执行
- Next entry point：AgentController 执行 `accepted plan commit`；本 agent 未 commit，并停止等待主控
