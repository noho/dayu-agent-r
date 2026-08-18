# UF-FIX08 existing-source-auto-repair：final closeout

## Gate 元数据与完成状态

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`final closeout`
- 日期：2026-08-16
- 模式：`local-only`
- branch：`codex/upload-filing-oracle`
- base：`5859856e46af42c9ae5a2a5c07fab1ba59dc91d3`
- accepted deepreview commit / HEAD：`f959eddd8d23c2f52e6f402bb0d3a6224258dc1e`
- completion status：`FINAL CLOSEOUT PASS / LOCAL WORK UNIT COMPLETED`
- blocking questions：无
- artifact path：`docs/gateflow/uf-fix08-existing-source-auto-repair-final-closeout-20260816.md`
- artifact ownership：本文件由 final closeout gate 新增；依用户指令不 commit，由 Controller 后续提交
- PR status：`not created per user instruction`
- push status：`not pushed per user instruction`
- Gateflow PR chain：`USER-EXPLICITLY-SKIPPED`；不记作 `draft-PR-pass`，不补做或假设 PR review
- next entry point：用户可在本地审阅并自行推送，或另行授权后续独立 work unit；UF-FIX08 当前 local work unit 已完成

## 目标、动机与第一性原理结论

目标成立，且原始严重性判断成立。一个可消费 source publication 的最小事实不只是“目录或文件存在”，而是 exact source identity、可信
meta/provenance/revision、完整且唯一的文件声明、regular physical set、size/digest、primary/derived 关系，以及 source-kind manifest 与
actual tree 的双向一致。UF-FIX08 前，classifier、snapshot、commit validator、upload state、skip 与 workflow 分别读取或重建这些事实，
损坏 publication 可能被误判为可跳过、可读取或可 reset；这不是单个 skip 条件的局部 bug，而是完整性 contract 与修复授权 owner 不闭合。

最终方案没有在 workflow、Service、CLI、snapshot 或测试 fixture 增加 fallback。它先把完整性与 canonical projection 收敛到 storage
owner，再由 validator 产生唯一 repair authorization，最后由 Docling、repository 与既有 batch owner 机械执行。该路径复用现有 opaque
revision、publication guard、writer reservation、staging、commit validator、backup/journal 与 old-or-new swap，没有新增第二套事务、repair
journal、revision 或兼容读取，因此满足当前需求且没有过度设计。

## 最终 owner architecture

| 业务语义 | 唯一 owner | 消费边界 |
| --- | --- | --- |
| published/staged source 的四态完整性、closed reasons、可信 revision 与 canonical source/manifest projection | `dayu.fins.storage` public integrity contract 与 `_fs_source_integrity` filesystem inspector | classifier、upload state、snapshot、commit、download 只消费 typed inspection，不从 raw fields 重判 |
| fresh upload company/source 同版状态 | `FilingUploadStateRepositoryProtocol` filesystem implementation | validator 只接收同一 publication guard 内产生的 classification 与可信 business meta |
| existing-source repair eligibility | `validate_fins_upload_filing_request()` | 只有 `REPAIR_REQUIRED + exact auto + 完整非空 selection` 产生 `ExistingSourceAutoRepair`；其它层不得重判 |
| repair disposition | `dayu.fins.upload_repair_contract`，唯一 production producer 为 ingestion validator | Docling/workflow 只检查 closed discriminator并原样传递 |
| originals、primary/companions、derived、fingerprint 与 final source mutation | `DoclingUploadService` | converter 只产生 bytes，workflow 不拼装或重算资产关系 |
| Phase B status/revision recheck、repair reset、remaining canonical manifest rewrite | source repository `reset_source_document_for_repair()` | workflow只传 expected integrity与 batch；stale/blocked 均在 reset 前失败 |
| company/source/assets/meta/manifest 原子 publication | 既有 filesystem batch、commit validator 与 swap/recovery owner | caller-owned同一 batch只产生完整 old 或完整 new；失败 rollback |
| LLM/user-facing bounded failure code、文案与 retry hint | `dayu.fins.upload_failure` 及既有 usage owner | workflow/runtime/direct/CLI 只投影 typed reason，不暴露 path、revision、raw meta 或异常字符串 |

Host/Engine/Service/CLI 分层与装配没有变化；财报文档存取仍且只通过 `dayu.fins.storage`。

## What changed

### 1. Typed integrity contract

- `SourceIntegrityClassification` 收敛为 `MISSING`、`COMPLETE`、`REPAIR_REQUIRED`、`UNSAFE` 四态，并冻结 revision/reasons 不变量。
- repairable 与 unsafe 原因形成 closed set；`UNSAFE` 固定不公开可比较 revision，任一 unsafe identity comparison 都 fail closed。
- `FilingUploadPublishedState` 必须显式携带 exact target classification；`MISSING/UNSAFE` 不携带 source meta，可信状态只携带同次 inspection 的
  business meta。
- 新增 closed repair disposition、stale/repair-blocked storage exceptions，以及 path-free upload failure factories；未保留旧 schema alias、
  default、dual-read、wrapper 或兼容 re-export。

### 2. Unified filesystem inspector

- 新增 storage 私有 inspector，统一 identity/meta/provenance/revision、file declaration、physical set、size/digest、primary/derived、manifest 与
  cross-source facts。
- published/staged classifier、inventory、snapshot 与 commit validator 复用同一 typed payload；commit validator 继续独占 staging URI 与
  containment 资格，snapshot 只读取 `COMPLETE` publication。
- canonical manifest item 只由 trusted persisted meta 经现有 `FilingManifestItem` / `MaterialManifestItem` owner 生成，不读取或拼接损坏 manifest。
- same-basename asset 继续以 storage-owned name 与 exact `derived_from` 为身份；真正歧义仍为 `UNSAFE`，没有放宽 UF-FIX07 contract。

### 3. Repair eligibility

- ingestion validator 成为 existing-source repair 的唯一授权 owner；显式 `create/update/delete` 对损坏目标失败，`UNSAFE` 对所有 action 失败。
- static selection projection 抽成唯一纯 owner，validated request 复用同一 primary/companions 结果，不再复制 duplicate、selector、membership 或
  multi-file primary 规则。
- raw runtime start 在 job/observation 创建前原样传播 typed prevalidation failure；repair disposition 为 required contract，无默认兼容路径。

### 4. Atomic repair publication

- existing repair 即使 fingerprint 相同也禁止 skip，完整读取并发布 authoritative originals，只转换 authoritative primary。
- `reset_source_document_for_repair()` 在真实 staged tree 中先做 exact target status/revision recheck，再检查 filing siblings 与 material
  whole-kind 状态；stale 与 cross-source/material blocked 在任何 reset 前区分为不同 typed failure。
- remaining manifest 只使用 non-target inspection 的单点 canonical item；target reset、全部 assets、new revision、canonical manifest 与
  company decision 仍在现有 caller-owned batch 一次 commit。
- conversion、blob、manifest rewrite、commit 或 rollback 路径均保留 published old tree；成功后 re-read、snapshot 与 downstream只看到完整 new。

### 5. Workflow projection 与 downstream

- SEC/CN/HK filing workflow 共用 `_filing_upload_fresh_validation` 作为 fresh read + validator 的唯一 boundary，入口 preflight 的旧 disposition
  被丢弃。
- fresh typed failure、I/O 与 runtime lock operational failure投影为 bounded failed event；workflow不读取 raw meta、目录或异常字符串。
- market workflow机械传递 fresh repair disposition；durable job summary与 direct result消费同一 failure JSON。
- repair 后 snapshot 与 `process_filing` 只消费 new primary与同一 new revision，不扫描 originals/companions；US/CN/HK 各自 wiring均有真实
  filesystem deterministic coverage。

### 6. Download guards

- SEC/CN single-filing Phase A 在读取 previous meta 前、Phase B 在 identity comparison/reset前显式拒绝 `UNSAFE`。
- whole-tree preflight继续是 company、maintenance、rejection mutation前的唯一 owner；多 actual、多 repair target或未选中 target均 typed
  fail closed，唯一 accepted selected filing 可沿既有下载/upsert路径重建 canonical manifest。
- provider、retry、overwrite、rejection policy与三轮 download identity retry保持不变。

### 7. Aggregate edge fixes

- M2：empty actual inventory + trusted manifest dangling IDs 现在由 inspector 合成稳定排序、无 revision 的
  `UNSAFE(SOURCE_MANIFEST_UNTRUSTED)` typed inspections，使 exact/list/preflight/commit 同源失败关闭。
- R1：empty actual inventory + untrusted manifest 无可信 document ID可投影时，whole-kind inspector直接抛
  `SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`；不伪造 identity，不误杀 clean empty workspace，也不回退 M2 synthetic 路径。
- private inspection revision 与 canonical-items/blocked-reason gating 的中文 docstring 已补齐，明确私有事实不得公开投影、blocked reason必须先于
  canonical items消费。

## Accepted commits 与 scope

| Commit | Accepted gate |
| --- | --- |
| `c8e75629` | accepted plan for UF-FIX08 existing-source-auto-repair |
| `cc07db75` | Slice 1 integrity contracts |
| `a29c8eb5` | Slice 2 integrity inspector |
| `1fd52c96` | Slice 3 repair eligibility |
| `4812878b` | Slice 4 staged repair owner |
| `1e062f6c` | Slice 5 workflow repair projection |
| `65d352e6` | Slice 6 download guards |
| `f959eddd` | accepted aggregate deepreview |

`5859856e..f959eddd` 是上述八个提交的线性范围，共 91 个文件：20 个 production Python 文件、14 个 test Python 文件、3 个 README、
16 个 Gateflow artifacts 与 38 个 review artifacts。production 全部位于 `dayu/fins`；没有 `dayu/host`、`dayu/engine`、`dayu/service`、
`dayu/cli` 或 `dayu/config` production diff。

## Verification

以下均为各 accepted gate artifact 记录的 Python 3.11 `.venv` 单进程结果；final closeout 未改代码，因此不重复运行测试或 pyright，只执行最终
格式、scope 与 frozen guards。

| Gate | 结果 |
| --- | --- |
| Slice 1 | storage/ingestion/Service/CLI focused `637 passed`；pyright `0 errors, 0 warnings, 0 informations` |
| Slice 2 | storage/snapshot/commit owner suite `351 passed`；修改模块 branch-aware coverage `84%–100%`、total `87%`；pyright 0 |
| Slice 3 | owner suite `333 passed`，storage owner `297 passed`，focused `1181 passed`，coverage run `1196 passed`；`tests/fins` `1802 passed, 1 skipped`；修改模块 coverage `82%–93%`；pyright 0 |
| Slice 4 | affected matrix `345 passed, 1 skipped`；`tests/fins` `1827 passed, 1 skipped`；修改模块 coverage `80%–97%`、total `87%`；pyright 0 |
| Slice 5 | direct files `430 passed`；focused `1221 passed`；`tests/fins` `1842 passed, 1 skipped`；Service/CLI `188 passed`；三个 production模块 coverage `100% / 92% / 92%`；pyright 0 |
| Slice 6 | download files `201 passed`；focused `1230 passed`；`tests/fins` `1851 passed, 1 skipped`；Service/CLI `188 passed`；SEC/CN download coverage均 `83%`；pyright 0 |
| Aggregate fix / final accepted validation | focused `1238 passed`；`tests/fins` `1859 passed, 1 skipped`；pyright `0 errors, 0 warnings, 0 informations`；`_fs_source_integrity.py` branch coverage `86%`（501 statements、208 branches） |
| Final aggregate reviews | `deep-review-20260816-200421.md`：`PASS`，独立新增节点 `8 passed`、相关 matrix `558 passed`、pyright 0；`deep-review-20260816-200444.md`：`PASS`，R1节点 `6 passed`、focused `1253 passed`、pyright 0 |

唯一 skip 是环境条件门控的真实 Docling integration；重复出现的 3 条 warning 来自已安装 `edgar` package 的 deprecated imports，不是本
work unit 新增 failure。

Final closeout guards：

- `git diff --check`：通过；
- 新增 closeout artifact 对 `/dev/null` 的 `git diff --no-index --check`：无 whitespace diagnostics（exit 1 只表示存在新增内容）；
- branch/base/HEAD/commit chain：通过；
- scope guard：通过；closeout 前工作树干净，closeout 后仅本 artifact 未跟踪；
- frozen guard：oracle、scenario、Host/Engine design、registry/evidence 命名路径以及 Host/Engine/Service/CLI production 相对 base均零修改。

## README updates / decision

- 根 `README.md`：按最终用户手册职责更新一处 upload action 说明；说明完整输入下 `auto` 可原子重建安全可修复目标，显式 action与 unsafe
  状态在发布前失败。未写 storage enum、revision、测试或 work-unit过程。
- `dayu/fins/README.md`：按 Fins developer stable contract职责更新四态完整性、trusted revision、validator-only authorization、fresh/staged
  recheck、old-or-new batch、snapshot complete-only与 download fail-closed；删除过时的仅三类 physical corruption表述。
- `tests/README.md`：按测试维护者职责新增 accepted focused命令与 integrity/repair/publication/snapshot/downstream/download owner matrix。
- `dayu/README.md`：不更新；`UI -> Service -> Host -> Engine`、Fins capability位置与 assembly均未改变。
- Engine/Host/config README：不更新；对应 package职责与公共边界未变化。
- Aggregate M2/R1 fix没有新增 README diff：它恢复上述已文档化的 manifest/actual-tree `UNSAFE` 与 whole-tree side-effect-free
  fail-closed contract。

## Findings final state

| Finding | Final state | 结论 / owner |
| --- | --- | --- |
| M1 canonical目录被异源 descriptor占据 | `证据失效` | identity owner已对 locator与descriptor identity双向校验；exact为`IDENTITY_UNTRUSTED`、whole typed fail-closed，新增 filing/material published/staged/whole回归后关闭，不重复生产校验 |
| M2 empty inventory + trusted manifest dangling IDs | `已修复` | storage inspector synthetic UNSAFE投影；exact/list/preflight/commit与SEC真实workflow同源且零副作用 |
| R1 empty inventory + untrusted manifest | `已修复` | storage whole-kind typed `UNSAFE_PUBLICATION`；clean empty、nonempty untrusted与M2路径均不回退 |
| Aggregate Finding 3/4 docstrings | `已修复` | private revision不可公开投影、blocked reason先于canonical items消费的owner contract已写明 |
| Aggregate Finding 5 `_ordered_reasons`非法类型 | `rejected-with-reason / 证据失效` | typed signature与全部当前调用点已由pyright闭合；不扩张不可达非法runtime contract |
| Aggregate Finding 6 raw runtime lock projection | `deferred-with-owner / 未修复` | fresh workflow boundary已typed处理；更上层raw runtime lock operational projection归后续 Fins upload operational failure owner |
| Aggregate Finding 7手工构造validated request状态/action强化 | `deferred-with-owner / 未修复` | production唯一producer已经validator闭合；额外constructor hardening归后续 Fins validated-request contract owner |
| Aggregate Finding 8一般SEC/CN download terminal projection | `deferred-with-owner / 未修复` | 当前lower owner已fail-closed；统一terminal code/schema归后续 general download failure projection work unit |
| L1–L15 | `rejected-with-reason` | final reviews复核原裁决成立；涉及manual writer、catch闭集、值域、snapshot探测、future manifest schema、fake seam等均未构成当前contract blocker |

所有 slice accepted findings 已修复、裁决闭环或在后续 slice完成；aggregate final reviews均为 PASS。没有未分类 finding、部分修复 finding、
blocking open question或当前 work unit 内未完成的 accepted finding。

## 未执行与冻结状态

- 未运行 UF-PF08、UF-PF12、`dayu-cli`、真实 provider、真实 converter 或其它真实 evidence；deterministic pytest不冒充真实 evidence。
- 未刷新 `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 或任何 scenario/registry/calibration状态。
- frozen evidence、Host/Engine design与既有 review/gate artifacts零修改；final closeout只新增本文件。
- oracle/registry仍保留 fix前真实观察，后续只有独立 evidence/adjudication work unit可以更新。

## Remaining risks / owners

| Remaining risk / uncovered area | 分类 | Owner / destination |
| --- | --- | --- |
| preparation期间一般同请求并发的success/skip收敛 | assigned to later work unit | `UF-FIX10`；当前只做repair Phase B stale、零重试与old/new保护 |
| fresh company meta warning | assigned to later work unit | `UF-FIX11` |
| material existing-source auto repair | assigned to later work unit | 独立 material repair work unit；当前只在filing repair前阻断不完整material，不授权修复 |
| 旧 schema corpus读取与迁移 | assigned to later work unit | 显式 migration work unit（需另行授权）；当前fresh schema无compat/dual-read |
| UF-PF08/UF-PF12真实 evidence与oracle/scenario/registry裁决 | assigned to later work unit | evidence / registry adjudication owner |
| 一般SEC/CN download typed terminal code/schema | assigned to later work unit | future general download failure projection owner；不固化现有generic fallback |
| raw runtime lock operational failure projection | assigned to later work unit | Fins upload operational failure projection owner |
| 手工构造validated request的非repair状态↔action不变量强化 | assigned to later work unit | Fins validated-request contract hardening owner |
| manual filesystem writer绕过repository lock | assigned to operational policy | storage operational policy；当前guard、Phase B与commit validator不承诺治理外writer协调 |
| exact-target whole-kind scan的大 corpus性能 | assigned to later work unit | 独立storage performance量化/优化；当前没有material correctness regression证据，不授权stale cache |
| 多悬空ID + nonempty inventory排序、SEC/CN Phase B churn、material exception conversion与repair专用barrier的额外直接节点 | covered by deterministic implementation/existing mechanism tests；可后续强化 | storage/download coverage hardening owner |

所有 residual risk 均已分类且有 owner/destination；它们不改变 UF-FIX08 已完成的 existing-source safe auto-repair contract。

## PR / push / issue status

- PR status：`not created per user instruction`。
- Draft PR URL：`N/A`。
- Push：未执行；当前分支只保留本地 accepted commits。
- PR review / accepted PR review commit / final push：未执行，也不声称通过。
- Gateflow `ready-to-open-draft-PR -> push -> create draft PR -> PR review -> fix -> re-review -> accepted PR review commit -> push -> draft-PR-pass`
  整条链由用户在本次 local-only请求中显式跳过；状态记录为 `USER-EXPLICITLY-SKIPPED`，不是 `draft-PR-pass`。
- Issue link：`N/A`；UF-FIX08是本地 work unit，用户未提供GitHub issue编号，且禁止GitHub外部写入。
- Issue closeout comment：`N/A`；未创建或修改任何外部issue/comment。
- 本 gate 不 commit；由 Controller 按用户指令决定如何提交本 closeout artifact。

## Final decision 与 next entry point

UF-FIX08 已在当前本地分支完成 accepted plan、六个 implementation/review loops、aggregate deepreview/fix/re-review、accepted deepreview
commit、职责内 README与最终 local-only closeout。最终 owner architecture闭合，accepted findings无遗留 blocker，验证门槛通过，冻结 scope零
修改，remaining risks均已有后续 owner。

`UF-FIX08 existing-source-auto-repair` 当前 local work unit：`COMPLETE`。

Next entry point：用户可在本地审阅本 artifact与 `5859856e..f959eddd`，随后自行 push；如需继续，应以 UF-FIX10、UF-FIX11、material
repair、migration、download failure projection、runtime operational projection、validated-request hardening或 UF-PF08/UF-PF12 evidence中的
任一项新开独立 work unit，不在 UF-FIX08 中继续扩 scope。
