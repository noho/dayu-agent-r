# UF-FIX08 existing-source-auto-repair：Goal Confirmation

## Gate

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`goal confirmation`
- design inputs：`docs/host/design.md`、`docs/engine/design.md`
- oracle input：`docs/cli_ci_oracles.json` 的 `upload_filing.existing-source-integrity`
- scenario input：`docs/cli_ci_scenarios.json` 的 `UF-FIX08`
- frozen evidence inputs：`UF-I01`–`UF-I10`
- completion status：`confirmed`
- artifact path：`docs/gateflow/uf-fix08-existing-source-auto-repair-goal-confirmation-20260816.md`

## Preflight

- 当前分支：`codex/upload-filing-oracle`，不是 protected trunk。
- 工作树：preflight 时干净。
- merge / rebase / cherry-pick / revert：均未进行。
- 实际 remote 名为 `github`；抓取 `github/main` 后，本地 `main` 与 `github/main` 同为
  `256786b255021ee429a20f22aad726b1ad33916c`，`main...github/main = 0/0`，无需执行 fast-forward mutation。
- 当前分支以 `main` 为祖先且单向领先 58 个提交，`main...HEAD = 0/58`。
- 用户明确要求在当前分支提交且无需 PR；本 work unit 保留 goal、plan、review、implementation、deepreview、local commit
  与 final closeout gates，不执行 push / draft PR / PR review 链。
- Agent pane 已确认：AgentMiMo=`ai-0:1.1`、AgentCodex=`ai-0:1.4`、AgentDS=`ai-0:1.5`。

## 第一性原理判断

问题成立，且严重性评估准确。

一个 source 只有在以下事实同源时才是可消费的 published source：稳定 target identity、authoritative originals、唯一 primary
Docling 派生物、`meta.files` 的 name/size/digest、`primary_document`、source-kind manifest 以及实际 published tree。任一事实不一致时，
download、upload、snapshot 或 downstream 若继续 skip/读取，就会把损坏状态伪装成成功，因此必须 fail closed。

但“发现损坏”不等于“只能要求用户理解并手工修内部目录”。当请求已经通过当前严格静态准入、ticker/calendar/year、converter
capability、primary/companions 和内容转换，且 exact filing target 已存在、storage 能给出稳定 published revision、损坏只位于可由本次
完整 authoritative local selection 全量重建的 target publication facts 时，`auto` 的业务含义应是原子替换该 target，而不是继续走
identical-fingerprint skip。反之，缺少稳定 identity/revision、meta/descriptor 结构不可信、损坏涉及不能由本次 target 重建的其它
source，或动作不是 `auto` 时，没有足够事实证明替换安全，必须继续 fail closed。

因此 root cause 不是单一 skip 条件，而是 source integrity contract 与 upload published-state contract 没有闭合：现有 storage
classification 只把已声明文件的 physical missing/size/digest mismatch 分类为 `REPAIR_REQUIRED`；缺 meta、manifest 不一致、primary
pointer 与 Docling 派生关系等仍以 `ValueError` 旁路；upload fresh state 又只暴露 raw `source_meta`，使 preparation、skip 与 publication
无法消费 storage owner 的同一个 typed classification/revision。正确修复必须先补齐 owner contract，再让 upload 机械消费。

## 语义 Owner 判定

| 语义 | 唯一 owner | 其它层职责 |
| --- | --- | --- |
| published/staged source 的 missing、complete、repair-required、unsafe 分类及封闭 reason | `dayu.fins.storage` 的 public source integrity contract 与 repository implementation | download、upload、snapshot、tests 只消费 typed classification，不从异常字符串、raw meta、目录扫描或文件存在性重判 |
| target 是否存在及其 opaque published revision | 同一个 storage integrity classification；revision 由 source mutation owner 生成并由 repository read/publication guard 验证 | workflow 只比较同 target 的 typed revision/presence，不读取 storage 私有 revision 字段 |
| `auto` repair eligibility | `dayu.fins.ingestion_runtime` 的 filing request validation boundary，机械组合 storage classification、exact target identity、requested action 与已通过的 authoritative `FinsUploadFilingFiles` | CLI、Service、pipeline 不自行推断；`create/update/delete` 和 unsafe classification 必须拒绝 |
| originals、primary/companions、derived asset、fingerprint 与待发布完整 source | `DoclingUploadService` 的 typed preparation boundary，消费 validated repair disposition；repair 时禁用 identical skip 并全量重产 | converter 只产内容；workflow 不拼文件集合或重算 repair reason |
| staged revision recheck、完整 tree validation 与 old-or-new 原子替换 | `dayu.fins.storage` repository/batch publication contract | pipeline 只在 caller-owned batch 中传入 expected typed classification/revision，失败即 rollback；不得直接改财报目录/meta/manifest |
| path-free bounded 用户失败 | 既有 `dayu.fins.upload_failure` typed failure owner | CLI/Service 只投影既有 failure，不暴露 path、traceback、raw meta 或内部 reason |

repair eligibility 不应下沉成“storage 看见损坏就自动修”的通用 framework。storage 只承诺事实分类、revision 与原子 publication；
是否允许用户命令触发 repair 仍属于 filing request owner，因为它需要同时裁决 `action=auto`、完整 local selection 和 exact target。

## 完整性分类边界

### `MISSING`

- exact target publication 不存在；不携带 revision 或 repair reasons。
- 普通 `auto` 仍按既有 create 语义处理，不属于 repair。

### `COMPLETE`

- target identity/meta/provenance/revision 合法；全部声明文件为 regular file，size/digest 与实物一致；实际文件集合与声明集合一致；
  `primary_document` 精确命中 primary Docling 派生物；source-kind manifest 与 actual published tree、source meta 投影双向一致。
- 只有该状态可以进入既有 identical-fingerprint skip。

### `REPAIR_REQUIRED`

- target identity、source meta 结构与 persisted revision 仍可信；损坏仅属于本次完整 local selection 可全量替换的 published facts，
  包括 original 或 primary Docling 缺失、实物 size/digest 与 meta 不一致、primary pointer/derived 投影可由 authoritative primary 重建，
  以及 source-kind manifest 缺失或投影不一致但 storage 能从仍可信的 staged tree 唯一重建 canonical manifest。
- 该状态不是 repair authorization；只有 selected exact target + `action=auto` + 非空完整 local selection 才产生 repair disposition。

### `UNSAFE`

- target/descriptor/meta/revision/provenance 无法建立可信 identity，存在未声明额外业务文件、非法/symlink/特殊文件、重复或非法文件身份、
  manifest dangling/duplicate/identity 冲突、损坏波及不能从当前 request 唯一重建的其它 source，或其它结构状态不封闭。
- 必须 typed fail closed；不得通过 `getattr`、默认值、loose parsing、目录猜测或重建 raw meta 进入 repair。

## 直接代码与数据证据

- `dayu/fins/storage/source_integrity.py` 当前 `SourceIntegrityStatus` 只有 `MISSING/COMPLETE/REPAIR_REQUIRED`，reason 只有
  `PHYSICAL_FILE_MISSING/SIZE_MISMATCH/DIGEST_MISMATCH`；没有 unsafe 状态、primary/derived 或 manifest reason。
- `dayu/fins/storage/_fs_source_document_core.py::_classify_source_integrity_unguarded` 只遍历 `meta.files` 并核对 physical
  missing/size/digest；缺 `meta.json`、非法 meta、未声明额外文件直接抛 `ValueError`，且没有校验 `primary_document` 或 source-kind
  manifest。因此现有 public classification 不是完整 source publication contract。
- 同模块 `_validate_published_source_manifest_unguarded` 在 `list_source_integrity` 外围单独校验 manifest，manifest 缺失或投影不一致
  直接抛 `ValueError`；这证明 manifest 事实尚未进入同一个 typed target classification。
- `dayu/fins/storage/_fs_storage_infra.py::_validate_complete_source_tree` 与
  `_validate_complete_source_directory` 已在 commit 前严格校验 source-kind manifest、meta/provenance/revision、files 与
  `primary_document`，说明完整 publication 规则已有 owner 级事实，但 read classification 与 commit validation 目前是两套不对称路径。
- `dayu/fins/storage/_fs_source_snapshot.py` 已把 persisted revision 作为 snapshot 同版 identity，并独立验证 meta/files/primary；
  它尚未消费完整 source integrity classification，存在 read contract 漂移风险。
- `dayu/fins/storage/repository_protocols.py::FilingUploadPublishedState` 当前只含 `company_meta` 与 raw `source_meta`；
  `_FsFilingUploadStateMixin.read_filing_upload_state` 也只在 publication guard 内读取这两项，没有返回 target integrity/revision。
- `dayu/fins/ingestion_runtime.py::validate_fins_upload_filing_request` 只根据 `published_state.source_meta` 解析 auto/create/update/delete，
  因此无法区分 complete、repairable 与 unsafe existing target。
- `dayu/fins/pipelines/docling_upload_service.py::prepare_upload` 在读取 originals 并计算 fingerprint 后立即调用 `_can_skip_upload`；
  该函数只比较 raw previous fingerprint、overwrite 与 deleted flag，不知道 published source 是否完整。这是 identical-fingerprint repair
  被错误截断的直接调用链证据。
- SEC 与 CN/HK upload workflow 都先 fresh-read state、prepare，再 begin batch；当前 `commit_prepared_upload_batch` 没有像 download
  Phase A/Phase B 那样比较 preparation 前 classification 与 batch staging classification，因此不能证明 repair 没有覆盖已变化 publication。
- SEC/CN download 已使用 `classify_source_integrity`、`classify_staged_source_integrity` 与
  `has_same_source_publication_identity` 做 Phase A/Phase B identity recheck，证明现有 repository/batch contract 可复用，无需新建 adapter。
- accepted oracle 明确要求 existing source 任一 original/Docling/meta/manifest 不一致 fail closed，同时允许完整本地输入的 safe auto
  atomic rebuild；scenario registry 将该缺口登记为 `UF-FIX08`。本 work unit只读取，不修改 oracle、scenario registry 或冻结 evidence。

## 目标与成功信号

1. storage public integrity contract 对 published 与 staged target 使用同一封闭 typed classification/revision，覆盖 originals、primary
   Docling derived、meta size/digest、primary pointer、source-kind manifest 与 actual tree，并明确 `UNSAFE`。
2. download、upload published-state、source snapshot 与 commit validation 复用同一个 owner 级 classification/revision 事实或其唯一内部
   validator；不存在 consumer 自行从 raw meta、路径、异常文本或目录结果重判。
3. `action=auto`、exact selected target、完整非空 local selection 且 classification=`REPAIR_REQUIRED` 时，validated request 携带 typed
   repair disposition；其它 action、missing/unsafe/identity 不确定或不完整请求不进入 repair。
4. repair preparation 全量读取 authoritative originals、只转换 authoritative primary、重建 originals/primary Docling/meta/manifest，
   即使 input fingerprint 与旧 meta 相同也不得 skip。
5. publication 在 begin-batch staging 中复核与 preparation 同 target 的 presence/revision 和 repair eligibility；不一致时 typed fail closed，
   不使用陈旧判断覆盖新 publication。本轮不实现 UF-FIX10 的一般同请求竞争 success/skip 收敛。
6. staging 完整性复核通过后，source reset、全部 assets、source meta、manifest 与 company meta decision 通过同一个 ticker batch old-or-new
   原子提交；转换、staging、复核、commit 或 rollback 任一步失败都不留下半修复、临时 publication 或孤立 company meta。
7. 成功后 public repository 重读为 `COMPLETE` 且 revision 已变化；snapshot 的 primary、file metadata、size/digest、manifest、
   requested/stored summary 与 downstream `process_filing` 消费同一新 source。
8. create/update/delete 对损坏 target 继续 fail closed；缺文件、非法 primary、converter/content failure、unsafe structure 与 stale revision
   使用既有 typed bounded failure owner 输出无路径、无 traceback、可行动错误。
9. US/CN/HK owner-level tests覆盖 original missing/digest changed、Docling missing、meta size/digest mismatch、manifest missing、unsafe state、
   identical fingerprint bypass、revision conflict、conversion/staging/publication rollback、snapshot/downstream read；受影响测试、单文件覆盖率
   目标与 pyright 通过，并按职责更新 README。

## 非目标与 Scope Boundary

- 不实现旧 schema、旧 basename/name-key fingerprint 或旧无角色 multi-file state 的兼容读取、迁移或 dual-read。
- 不处理 UF-FIX10 一般同请求 concurrency、UF-FIX11 company meta warning、material repair 或其它修复项。
- 不执行 UF-PF08、UF-PF12 或任何真实 CLI evidence；不修改 `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 或冻结 evidence。
- 不引入通用 repair framework、adapter fallback、compatibility shim、下游补偿、CLI/Service 特判或 pipeline 直写财报目录。
- 不回退既有静态零副作用校验、action/update identity、完整集合原子替换、typed bounded failure、requested/stored summary、共享可中断
  converter、calendar/year、ticker alias、UF-FIX06 capability、UF-FIX07 primary/companion 与无碰撞 asset identity contract。
- 不修改 Host / Engine lifecycle、EventLog、memory、trace、tool loop 或调度状态机。

## Design Document Alignment

- `docs/host/design.md` 明确 Host 不承载财报业务语义、不直接管理财报原文仓储规则；因此 repair classification、revision 与
  publication 不进入 Host，也不能借 Host EventLog/trace 兜底。
- `docs/engine/design.md` 把 Engine 限定为单次 run、Runner 与 tool loop；Engine 不访问 Fins repository，也不拥有 upload repair。
- 真实修改边界应位于 `dayu.fins.storage` public integrity/publication contract、Fins filing request validation、共享 upload
  preparation/workflow 的机械消费与 owner-level tests；CLI/Service 无需新增 repair 分支。

## 本轮不做的过度设计

- 不建立跨 source kind、跨 provider 的通用 repair orchestration framework；只扩展已有 source integrity 与 batch publication contract。
- 不新增第二套 revision、repair journal 或数据库；复用 persisted source revision、publication guard、writer batch、staging validation 和
  old-or-new directory swap。
- 不为 unsafe corruption 设计猜测式恢复，也不扫描用户目录寻找“可能完整”的附件集合。
- 不把每个 corruption reason 暴露给用户；用户只需提供完整合法输入，内部 reason 只服务 owner contract 与测试。
- 不让 upload workflow复制 download 的 provider-specific preflight；只复用 storage classification/revision 的通用事实与最小 Phase A/Phase B
  recheck 模式。

## Blocking Open Questions

无。用户已明确 repair 仅限 exact selected target、`action=auto`、完整 local input、fresh schema 与现有 batch publication；unsafe 状态、
其它 action、concurrency/evidence/registry 边界也已冻结。实现细节可在这些 owner boundary 内形成 code-generation-ready plan。

## Residual Risks / Uncovered Areas

| 风险或未覆盖项 | 分类 | owner / destination |
| --- | --- | --- |
| 同 request / 同 document 并发 success/skip 收敛 | assigned to later work unit | `UF-FIX10` |
| fresh company meta warning | assigned to later work unit | `UF-FIX11` |
| material source repair | assigned to later work unit | 后续独立 work unit |
| UF-PF08、UF-PF12 与真实 CLI post-fix evidence | assigned to later work unit | 后续 evidence work unit；本轮禁止执行 |
| registry 与冻结 evidence 仍描述修复前观察 | assigned to later work unit | 后续 registry/evidence work unit；本轮禁止修改 |

## Next Entry Point

进入 `plan`：先由 AgentCodex 产出 code-generation-ready plan，再由 AgentMiMo 与 AgentDS 并行执行两路 plan review。
