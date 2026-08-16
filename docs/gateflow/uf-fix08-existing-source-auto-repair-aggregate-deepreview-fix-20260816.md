# UF-FIX08 existing-source-auto-repair：aggregate deepreview fix

## Gate 元数据

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`aggregate deepreview -> fix`
- 日期：2026-08-16
- 分支：`codex/upload-filing-oracle`
- 输入 HEAD：`65d352e6`
- accepted plan：`docs/gateflow/uf-fix08-existing-source-auto-repair-plan-20260816.md`
- aggregate review inputs：`docs/reviews/deep-review-20260816-191226.md`、
  `docs/reviews/deep-review-20260816-192359.md`（两者均为未跟踪只读输入，本 gate 未改写）
- aggregate re-review inputs：`docs/reviews/deep-review-20260816-194657.md`（首版 PASS，未覆盖
  R1 adversarial 场景，不作为 gate pass）、`docs/reviews/deep-review-20260816-195058.md`（R1 blocker
  真源）；两者均保持未跟踪只读
- completion status：`REREVIEW_FIX_COMPLETE_AWAITING_AGGREGATE_RE_REVIEW`
- blocking questions：无
- current gate / next entry point：`aggregate deepreview re-review`
- 用户约束：不 commit、不 push、不创建 PR，本轮停在 aggregate re-review gate
- artifact path：
  `docs/gateflow/uf-fix08-existing-source-auto-repair-aggregate-deepreview-fix-20260816.md`

## 第一性原理与直接证据

### M1：canonical 目录与异源 descriptor

Controller 将 review finding 1 升级为 blocker 的动机成立：如果 exact canonical 目录真能被异源
descriptor 解析为另一 source，`MISSING + auto` 会违反 fail-closed 与数据保护契约。但对当前 HEAD
的 owner 代码复核后，review 证据链的关键前提不成立：

1. `dayu.fins.storage._fs_identity._read_identity_descriptor()` 在枚举模式下也使用
   `directory.name` 与 `derive(namespace, descriptor external_identity)` 做双向校验。
2. descriptor 声明的 document identity 与当前 canonical locator 不一致时，该 owner 必定抛
   `ValueError`，不会返回 review 所假设的“可读异源 identity”。
3. `_inspect_source_kind_unguarded()` 已在 exact requested canonical 目录分支将该错误投影为
   `UNSAFE(IDENTITY_UNTRUSTED)/revision=None`；whole-kind 将无法归属的 root fact 投影为
   `SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`。

因此 M1 不存在可修的 production root cause；若再在 inspector 重复校验 canonical path，反而会形成
identity owner 之外的重复语义。本 gate 以 filing/material、published/staged/whole owner contract tests 锁定已有
invariant，finding 最终状态为「证据失效」。

### M2：空 actual inventory 与 trusted manifest 悬空 source ID

M2 真实存在。根因不在 workflow 的 preflight 条件，而在 storage inspector 生成 public fact 的边界：

1. `_apply_manifest_facts()` 能识别 `manifest_ids - actual_source_ids` 并生成 shared
   `SOURCE_MANIFEST_UNTRUSTED`。
2. 旧实现只把该 reason 叠加到已有 inventory item。actual inventory 为空时，没有任何
   `SourceIntegrityClassification` 承载该 unsafe 事实。
3. public `list_source_integrity()` 只投影 `inspection.inventory`，因此返回空 tuple；
   `classify_source_integrity_preflight()` 机械得出 clean，与同一 payload 的 kind-level unsafe 事实矛盾。

修复保持唯一 owner 在 `dayu.fins.storage`：inspector 现在为每个 trusted manifest 悬空 document ID
生成稳定排序的 synthetic `UNSAFE(SOURCE_MANIFEST_UNTRUSTED)/revision=None` source inspection，并与
实际 inventory 的 unsafe 投影合并。该 inspection 是“manifest 已声明该业务 identity，但其物理 source
不存在”的 typed 事实，不伪造 meta、revision、provenance、files 或 canonical item。

这一修复使 exact target、whole filing/material inventory、public preflight、commit validator 与 repair blocked
继续消费同一 inspection；没有改 workflow、CLI、public preflight 签名、revision 比较、publication guard 或
batch capability。

### R1：空 actual inventory 与 untrusted manifest

`deep-review-20260816-195058.md` 证明 trusted-dangling 修复仍遗漏 sibling branch：当 manifest
存在但结构不可信、actual inventory 为空时，`_apply_manifest_facts()` 返回空 inventory 与
shared `SOURCE_MANIFEST_UNTRUSTED`。whole-kind public list 无 classification 承载该事实，因而
preflight 误判 clean。

最终修复在同一 inspector owner 内、`_apply_manifest_facts()` 之后立即 gate：只有
whole-kind mode + empty inventory + shared `SOURCE_MANIFEST_UNTRUSTED` 时抛
`SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`。untrusted manifest 不能提供可信 document ID，因此
不生成 synthetic inspection；exact mode 继续用 requested ID 投影 UNSAFE，nonempty inventory 继续逐项
UNSAFE。workflow、public preflight signature、revision/guard/batch 契约均未变。R1 最终状态为「已修复」。

## 唯一语义 owner 与 changed files

唯一 owner 为 `dayu.fins.storage` 的 filesystem source-kind inspector。workflow 只继续消费 public typed
inventory/preflight，没有新增路径、raw meta、shared reason 或 blocked reason 二次判断。

| 文件 | 变更 |
| --- | --- |
| `dayu/fins/storage/_fs_source_integrity.py` | 为 trusted manifest 悬空 ID 投影稳定 UNSAFE inspection；whole-kind 空 inventory + untrusted manifest 直接 typed fail-closed；补充 private revision 与 canonical-items gating 中文 docstring |
| `tests/fins/test_fins_storage_atomicity.py` | 新增 M1 已有 identity-owner invariant 的 filing/material exact/staged/whole contract tests；新增 M2/R1 filing/material exact/list/preflight contract tests |
| `tests/fins/test_sec_pipeline_download.py` | 参数化真实 SEC whole-tree 空 inventory + trusted-dangling/untrusted manifest 零 company/provider/rejection 副作用测试 |
| `docs/gateflow/uf-fix08-existing-source-auto-repair-aggregate-deepreview-fix-20260816.md` | 本 fix gate 的根因、裁决、验证与 residual owner artifact |
| `docs/gateflow/uf-fix08-existing-source-auto-repair-aggregate-rereview-fix-20260816.md` | R1 re-review fix 的独立 durable artifact |

## Aggregate findings 逐项裁决

| Finding | Gateflow 裁决 | fix/re-review 状态 | 直接依据与去向 |
| --- | --- | --- | --- |
| 1 / M1 canonical 目录被异源 descriptor 占据 | `accepted` 后证据复核 | `证据失效` | `_read_identity_descriptor` 已作 locator↔identity 双向校验；exact 已是 `IDENTITY_UNTRUSTED`，whole 已 typed fail-closed；新增 owner 回归，不增加重复 production 校验 |
| 2 / M2 空 inventory + trusted manifest 悬空 ID | `accepted` | `已修复` | inspector 为每个悬空 ID 投影稳定 `UNSAFE/SOURCE_MANIFEST_UNTRUSTED`，exact/list/preflight 同源，SEC 真实 workflow 零副作用 |
| R1 / 空 inventory + untrusted manifest | `accepted` | `已修复` | whole-kind inspector 在 shared unsafe 事实无 classification 载体时直接抛 `UNSAFE_PUBLICATION`；不伪造 ID，exact/nonempty 分支不变 |
| 3 / private revision 在 public UNSAFE 后保留 | `accepted` | `已修复` | `_SourcePublicationInspection` 中文 docstring 明确其仅为私有 content fact，不得对外投影 |
| 4 / canonical items 与 blocked reason 并存 | `accepted` | `已修复` | `_SourceKindPublicationInspection` 中文 docstring 明确必须先 gate blocked reason，非空时 canonical items 不构成 repair 授权 |
| 5 / `_ordered_reasons` 非 enum 值 | `rejected-with-reason` | `证据失效` | 签名只接受 `SourceIntegrityReason` typed list/tuple，当前全部调用点受 pyright 约束；非 enum 输入在当前 typed call sites 不可达，不为未来非法调用扩张 runtime contract |
| 6 / raw runtime `RuntimeFileLockError` | `deferred-with-owner` | `未修复` | 事实存在，但不违反 UF-FIX08 当前 integrity/repair invariant；job 仍在创建前停止。按 Controller 边界不扩 scope，归属后续 Fins upload operational failure projection owner |
| 7 / 手工构造 validated request 的 MISSING+update | `deferred-with-owner` | `未修复` | 事实存在，但 production producer 均经唯一 validator，accepted plan 只冻结 repair disposition 不变量；归属后续 Fins validated-request contract hardening owner |
| 8 / SEC/CN 顶层 download generic 差异 | `deferred-with-owner` | `未修复` | 按 Controller 裁决归属 future general download failure projection owner；CN generic 残余同样不在本 gate |

### 低项 / Info 裁决

| 项 | 裁决 | 分类 / owner |
| --- | --- | --- |
| L1 inspector 两次 physical read TOCTOU | `rejected-with-reason` | caller-held publication guard 是 accepted plan 的当前一致性边界；manual writer 绕过 lock 继续归 storage operational policy |
| L2 catch 闭集依赖跨模块异常面 | `rejected-with-reason` | 无可达 typed 输入会产生已举例的闭集外异常证据；不扩大 catch |
| L3 public classification 不校验 ticker/document 值域 | `rejected-with-reason` | production constructor 输入由 identity owner 校验；本 gate 不重复值域 owner |
| L4 public repository docstring 保留结构 `ValueError` 说明 | `rejected-with-reason` | operational/capability `ValueError` 仍是 public Raises 的一部分；本 finding 未证明用户可见契约被破坏 |
| L5 upload-state 早返回不校验 document ID | `rejected-with-reason` | 公开 caller 已在进入分支前通过 identity owner 校验，不可达 |
| L6 snapshot kind 自动探测改为双 inspection | `rejected-with-reason` | 这是 accepted fail-closed 一致性方向，非缺陷 |
| L7 repair manifest 重写只保留当前三字段 | `rejected-with-reason` | 当前 manifest schema owner 只定义该字段集；未来 schema 扩展时由 schema owner 同步，不预留 compatibility |
| L8 空 selection 防御分支 | `rejected-with-reason` | 保留 producer-invariant fail-loud 防御，不影响当前 validator precedence |
| L9 fresh validation 未列 AssertionError | `rejected-with-reason` | owner 违约应 fail loud，不投影为业务失败 |
| L10 fresh validation 潜在 format-error 投影 | `rejected-with-reason` | static/post-init 同源校验使该路径当前不可达 |
| L11 exact-target 防御分支不可达 | `rejected-with-reason` | 不影响 typed contract，不做无关机械清理 |
| L12 download Phase B fake seam | `rejected-with-reason` | storage 真实 staged UNSAFE owner tests 与 workflow 零副作用分支测试已分层覆盖 |
| L13 clear preflight 宽异常 tuple | `rejected-with-reason` | 与本 gate source inspection 修复无直接关联，既有删除零副作用断言未被削弱 |
| L14 CLI renderer fixture 直建 identity | `rejected-with-reason` | renderer 单测不拥有 identity admission 语义；service/ingestion tests 已消费真源 |
| L15 无 repair 专用 barrier | `rejected-with-reason` | repair 复用同一 batch publication 机制，既有 barrier 与 repair rollback/old-tree 测试已覆盖机制与业务层 |

## 验证

全部命令均在 `source .venv/bin/activate` 后执行，未使用 xdist，未运行 UF-PF08/UF-PF12、
真实 CLI、真实 provider 或 converter evidence。

| 验证项 | 结果 |
| --- | --- |
| R1 新增精确节点（filing/material owner、SEC trusted/untrusted，含 trusted M2 回归） | 6 passed |
| storage + SEC/CN download 相关 matrix | 408 passed |
| accepted plan focused matrix | 1238 passed，3 个第三方 deprecation warnings |
| `tests/fins` 全量 | 1859 passed，1 skipped（环境条件），3 个第三方 deprecation warnings |
| 全仓 pyright `dayu/ tests/ utils/` | 0 errors，0 warnings，0 informations |
| 单进程 branch coverage focused suite | 1238 passed；`dayu/fins/storage/_fs_source_integrity.py` 86%（501 statements，208 branches，阈值 80%） |
| `git diff --check` | 通过；新增未跟踪 artifact 的 `git diff --no-index --check` 无 whitespace diagnostics（exit 1 仅表示文件与 `/dev/null` 存在内容差异） |
| scope / frozen guards | 通过；tracked diff 仅 3 个 production/test 文件，另有 aggregate fix/rereview-fix 两份 artifact；oracle/scenario/Host/Engine design 与 Host/Engine/Service/CLI production 零 diff |

coverage 实际报告：501 statements，63 missed，208 branches，36 partial branches，86% total。

## README decision

- `dayu/fins/README.md`：已有稳定 contract 明确 `MISSING` 仅代表 exact target 不存在，identity/manifest/
  cross-source 不可信必须 `UNSAFE`，whole-tree download 在业务副作用前 fail closed。本修复恢复已文档化的契约，不修改 README。
- `tests/README.md`：既有 focused 命令已包含两个新测试文件，owner matrix 已明确 manifest/cross-source
  `UNSAFE` 与 download 零副作用，不机械追加 work-unit 过程说明。
- 根 `README.md`、`dayu/README.md`：用户可见安装/CLI/workflow 与分层关系均未变，不更新。

## Residual risks / uncovered areas

| 风险 | 分类 | owner / destination |
| --- | --- | --- |
| 一般同请求并发 success/skip 收敛 | assigned to later work unit | `UF-FIX10` |
| fresh company meta warning | assigned to later work unit | `UF-FIX11` |
| material existing-source repair | assigned to later work unit | 后续独立 material repair work unit |
| 旧 schema corpus 读取/迁移 | assigned to later work unit | 后续显式 migration work unit |
| UF-PF08/UF-PF12 真实 evidence 与 registry/oracle 状态 | assigned to later work unit | evidence / registry adjudication work unit |
| SEC/CN 一般 download typed terminal projection | assigned to later work unit | future general download failure projection owner |
| raw runtime lock operational failure projection | assigned to later work unit | Fins upload operational failure projection owner |
| 手工构造 validated request 的非 repair 状态↔action 强化 | assigned to later work unit | Fins validated-request contract hardening owner |
| manual filesystem writer 绕过 repository lock | assigned to operational policy | storage operational policy |
| SEC/CN Phase B identity churn 真实注入、material exception conversion 直接节点、repair 专用 barrier | covered by existing mechanism tests / uncovered direct nodes | 后续 download concurrency / storage coverage hardening；不改变本 gate contract |

无 unclassified residual risk，无 blocking open question。

## Gate decision

M2 与 re-review R1 的 accepted blockers 均已在唯一 storage owner 修复，M1 经 identity-owner 直接证据与新增真实回归判定为
证据失效；accepted 低项 3/4 已澄清，其余 finding 已分类。AgentMiMo 首版 PASS
未覆盖 R1，不作为 gate pass。本 gate 不 commit、不 push、不创建 PR，
当前停在 `aggregate deepreview re-review`。
