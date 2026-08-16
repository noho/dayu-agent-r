# UF-FIX08 existing-source-auto-repair：Plan Review Adjudication

## Gate 元数据

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`plan re-review -> accepted plan`
- 日期：2026-08-16
- reviewed plan：`docs/gateflow/uf-fix08-existing-source-auto-repair-plan-20260816.md`
- review artifacts：
  - `docs/reviews/plan-review-20260816-120620.md`
  - `docs/reviews/plan-review-20260816-121010.md`
  - `docs/reviews/plan-review-20260816-122554.md`
  - `docs/reviews/plan-review-20260816-123328.md`
  - `docs/reviews/plan-review-20260816-123436.md`
- Controller decision：两路终审分别为 `pass` 与 `pass-with-risks`；RF1-RF4均已修复、无 blocker，plan accepted
- rejected / needs-more-evidence：无
- deferred-with-owner：RF5（低），本 work unit implementation review/deepreview focus，非阻塞
- changed files：
  - `docs/gateflow/uf-fix08-existing-source-auto-repair-plan-20260816.md`
  - `docs/gateflow/uf-fix08-existing-source-auto-repair-plan-review-adjudication-20260816.md`
- completion status：`ACCEPTED`
- next entry point：`Slice 1：冻结 public integrity/state/repair contracts` implementation
- blocking questions：无
- artifact path：`docs/gateflow/uf-fix08-existing-source-auto-repair-plan-review-adjudication-20260816.md`

## Scope 与约束

本轮只做 acceptance bookkeeping，不修改 plan 技术 contract。未修改生产代码、测试、README、oracle、registry、evidence、Host/Engine design；未运行实现测试、
pyright、coverage或真实 CLI evidence；未 commit、push或创建 PR。

裁决原则：所有 finding 均以 goal confirmation、storage/upload/snapshot/publication 直接代码事实和 Controller 的全量 accepted 指令为
约束。修复只补齐 code-generation-ready contract、slice、tests和failure path，不扩展 UF-FIX10、UF-FIX11、material repair、旧 schema
兼容、真实 evidence或registry修改。

## Review 120620 findings 裁决

| Finding | Decision | Plan fix位置 | 修复内容 | 最终状态 | Residual分类 |
| --- | --- | --- | --- | --- | --- |
| 01 `_can_skip_upload` 缺少repair disposition传入机制 | accepted | §7.1、§9 Slice 4、§11.3 | 冻结`prepare_upload(..., repair_disposition=...)` required keyword与`_can_skip_upload(..., *, repair_disposition=...)` exact signature；`ExistingSourceAutoRepair`第一条规则固定返回false，禁止调用点boolean旁路 | 已修复 | fixed in current plan fix |
| 02 `read_filing_upload_state` 缺少同guard inspector路径 | accepted | §6.1、§9 Slices 1-3 | 冻结`_inspect_source_kind_unguarded`接口；caller持publication guard或先验证真实batch，函数不接收/探测token且不二次加锁；state core同guard消费inspection | 已修复 | fixed in current plan fix |
| 03 `has_same...`对UNSAFE的测试不精确 | accepted | §9 Slice 1、§11.1 | 精确要求first/second/both为UNSAFE三种组合全部`ValueError`，另保留cross-target拒绝 | 已修复 | fixed in current plan fix |
| 04 commit validator URI归属不清 | accepted | §6.1、§6.2、§11.1 | inspector只拥有publication content/meta/role/manifest完整性；commit validator在inspection COMPLETE后独立验证staging URI和containment，URI不泄漏到published inspector | 已修复 | fixed in current plan fix |
| 05 Slice 2/3 inspector依赖风险 | accepted | §6.1、§9每个slice prerequisites | 写死private signatures/return payload/capability precondition；每个slice新增prerequisites，Slice 3不得返工locking seam | 已修复 | fixed in current plan fix |
| 06 repair期间snapshot可见性窗口 | accepted | §7.2、§11.3 | barrier测试固定：published target保持Phase A old classification/revision并按old损坏拒绝snapshot；complete sibling snapshot仍读old bytes/revision，永不观察staging MISSING/半写 | 已修复 | fixed in current plan fix |
| 07 canonical manifest items来源不清 | accepted | §5.2、§6.1、§6.2、§11.1/11.3 | canonical items只由trusted source meta经`FilingManifestItem`/`MaterialManifestItem` owner生成；禁止读取、merge或复制损坏manifest item | 已修复 | fixed in current plan fix |

## Review 121010 findings 裁决

| Finding | Decision | Plan fix位置 | 修复内容 | 最终状态 | Residual分类 |
| --- | --- | --- | --- | --- | --- |
| F1 whole-manifest-missing与non-target COMPLETE要求矛盾 | accepted | §5.2、§6.1、§6.2、§7.2、§11.1/11.3 | whole missing定义为source-kind shared reason，per-target/inventory均报告；inspection另带不含manifest reason的`content_classification`；Phase B sibling要求content COMPLETE且public reasons仅为shared reasons，不要求public status字面COMPLETE；download的multi-source/非selected拒绝与single selected repair最终按RF4收敛 | 已修复 | fixed in current plan fix |
| F2 Phase B non-target损坏失败类型未闭合 | accepted | §5.1、§5.5、§6.2、§8、§9 Slice 4、§11.3 | 新增`SourceIntegrityRepairBlockedReason/Error`；target stale仍用revision conflict，non-target/cross-source/canonical阻断用repair-blocked；新增`SOURCE_REPAIR_BLOCKED` bounded path-free public failure，禁止落stale或unexpected runtime | 已修复 | fixed in current plan fix |
| F3 fresh `FinsUploadPrevalidationError`传播未闭合 | accepted | §5.5、§7.1、§8、§9 Slices 3/5、§10、§11.2/11.4 | raw runtime start Raises加入typed prevalidation且job创建前原样抛出；SEC/CN/HK fresh validation显式转换typed failed event；async job持久化同一failure JSON/retry hint，不走generic `str(exc)` | 已修复 | fixed in current plan fix |
| F4 Slice 1遗漏service/CLI required fixtures | accepted | §8.2、§9 Slice 1、§10 | allowed files与验证命令加入`tests/service/test_fins_direct.py`、`tests/cli/test_fins_commands.py`；所有required state constructors同slice迁移且禁止default兼容 | 已修复 | fixed in current plan fix |
| F5 CN/HK矩阵矛盾且不足 | accepted | §8.2、§9 Slice 5、§11.4 | shared service/storage覆盖完整grid；US覆盖UF evidence组合；CN固定success+revision conflict/rollback+unsafe/company atomicity；HK固定success+stale或unsafe typed projection | 已修复 | fixed in current plan fix |
| F6 snapshot拒绝异常契约未指定 | accepted | §6.1、§7.2、§11.4 | light/full对REPAIR_REQUIRED/UNSAFE统一抛固定path-free `ValueError("source snapshot 只允许读取完整 source")`；不新增异常、不改read runtime，并写exact assertion | 已修复 | fixed in current plan fix |

## Review 121010 open questions 收敛

Controller 要求全部material问题收敛，因此四个open questions也在plan中给出确定答案：

| Open question | Decision / plan fix | 最终状态 | Residual分类 |
| --- | --- | --- | --- |
| 结构/role歧义与physical missing precedence | identity/meta/declaration/role/unsafe filesystem检查全部先于physical repair reason；同时命中固定UNSAFE | 已修复 | fixed in current plan fix |
| `_assert_authoritative_filing_identity`比较字段 | 只比较canonical ticker、document ID、internal document ID；不比较旧/fresh disposition/status/revision/reasons，fresh request自校验expected target | 已修复 | fixed in current plan fix |
| deleted + damaged auto repair | 明确仍授权repair；成功meta固定恢复`is_deleted=False/deleted_at=None` active source，并加owner test | 已修复 | fixed in current plan fix |
| manifest canonical field白名单 | 不在inspector/plan新建白名单；唯一字段owner是既有`FilingManifestItem`/`MaterialManifestItem.from_source_meta().to_dict()` | 已修复 | fixed in current plan fix |

## Review 122554 第二轮裁决

Controller 已明确接受 RF1-RF4；无 rejected、deferred 或 needs-more-evidence：

| Finding | Decision | Plan fix位置 | 修复内容 | 最终状态 | Residual分类 |
| --- | --- | --- | --- | --- | --- |
| RF1 frozen inspector未定义whole-kind inventory/commit调用形状 | accepted | §6.1、§9 Slice 2、§11.1 | inspector增加冻结whole-kind mode：`requested_document_id=None`且`target=None`；inventory/commit在同一guard/batch内每source kind只调用一次并消费同一inventory/shared/canonical payload，禁止逐document重扫或跨capability聚合 | 已修复 | fixed in current plan fix |
| RF2 remaining canonical items载体歧义 | accepted | §6.1、§6.2 step 5、§9 Slice 4、§11.3 | remaining items只消费同一次inspection中每个non-target的单点`canonical_manifest_item`并稳定排序；明确禁止消费会因target损坏而为空的aggregate tuple，补target-local damaged + complete sibling成功测试 | 已修复 | fixed in current plan fix |
| RF3 reset中的UNSAFE `ValueError`逃逸 | accepted | §6.2 step 3、§9 Slice 4、§11.3 | staged comparison前gate UNSAFE与非`REPAIR_REQUIRED`；comparison产生的`ValueError`在storage method内转为path-free revision conflict，且不吞invalid input `ValueError`；service只映射`SOURCE_REVISION_STALE` | 已修复 | fixed in current plan fix |
| RF4 download whole-manifest-missing表述过宽 | accepted | §7.2、§9 Slice 6、§11.4 | 多source、非selected或非唯一repair target继续typed fail closed；单一实际filing且为accepted selected target时保留既有selected repair下载/upsert重建manifest行为，并补SEC/CN回归 | 已修复 | fixed in current plan fix |

## 两路终审与 acceptance 裁决

| Artifact | Conclusion | RF1-RF4 | Blocker | Controller acceptance |
| --- | --- | --- | --- | --- |
| `docs/reviews/plan-review-20260816-123328.md` | `pass` | 全部已修复 | 无 | 接受 |
| `docs/reviews/plan-review-20260816-123436.md` | `pass-with-risks` | 全部已修复 | 无 | 接受；RF5按下表归类 |

RF5 的 acceptance bookkeeping：

| Finding | Decision | 最终状态 | Residual分类 | Owner / destination | 授权边界 |
| --- | --- | --- | --- | --- | --- |
| RF5（低）：exact-target whole-kind scan在SEC/CN per-filing Phase A/B中的潜在成本放大 | deferred-with-owner | 未修复 | covered by later approved slice | 本work unit各受影响slice的implementation review，以及aggregate deepreview | 只检查实际实现是否出现material性能回归并记录证据；不授权workflow inventory cache、跨filing stale inspection复用、inspector contract重设计或任何scope expansion。若出现material证据，另行提请Controller裁决，不在当前plan内自行优化 |

RF5 是明确分类的非阻塞 residual risk，不改变已冻结技术 contract，不阻塞 plan acceptance 或 Slice 1 启动。

## 修订后的关键 contract 决策

### Shared manifest 与 Phase B

- whole manifest missing是shared reason，不表示每个sibling content损坏。
- public per-target/inventory可为`REPAIR_REQUIRED(SOURCE_MANIFEST_MISSING)`；private
  `content_classification`仍可为`COMPLETE`。
- upload Phase B只允许target-local repair + sibling content COMPLETE + sibling reasons仅为同一shared reasons。
- canonical items完全从trusted metas经现有manifest item owner生成；损坏manifest只是被替换对象，不是输入。
- download不取得upload的multi-source canonical rewrite授权：multi-source/非selected遇shared reason typed fail closed，只有单一accepted
  selected filing沿既有download repair路径重建。

### 两类 Phase B failure

- target presence/revision/repair eligibility漂移：`SourceIntegrityRevisionConflictError -> SOURCE_REVISION_STALE`。
- target仍匹配但non-target/cross-source/canonical rewrite受阻：
  `SourceIntegrityRepairBlockedError -> SOURCE_REPAIR_BLOCKED`。
- 两者都在target reset/manifest rewrite前发生，触发same-batch rollback exactly once，且不得落`UNEXPECTED_RUNTIME`。

### Inspector 与 commit validator

- `_unguarded` inspector由caller持guard或已验证batch；不传、检测或复用token，不内部加锁。
- exact-target mode传document ID并返回非空target；whole-kind mode传`None`且target为`None`。
- inventory/commit每source kind只调用一次whole-kind mode，并在同一guard/batch内消费同一份inventory/shared reasons/canonical facts。
- commit validator复用该content/manifest inspection后，仍独立拥有staging URI和containment资格检查。

### Repair remaining items、conflict 与 download

- repair remaining manifest items只来自每个complete non-target inspection的单点`canonical_manifest_item`；target损坏导致aggregate为空不构成阻断。
- reset在identity比较前gate UNSAFE/非`REPAIR_REQUIRED`，并在storage method内部把comparison `ValueError`转为typed revision conflict。
- download对multi-source/非selected whole-manifest-missing typed fail closed；单一accepted selected filing维持既有repair重建路径。

### Upload disposition 与失败传播

- workflow fresh validated request是Phase A expected truth；入口preflight disposition被丢弃。
- `_assert_authoritative_filing_identity`只比较deterministic identity。
- `repair_disposition`从fresh request原样进入`prepare_upload`、`_can_skip_upload`和prepared mutation。
- raw runtime start的typed prevalidation在job创建前抛出；fresh async validation转为typed failed event/job terminal。

## Validation

本 gate 是acceptance-bookkeeping-only，验证范围为artifact consistency与scope：

- 两路终审artifact `123328`、`123436`已完整读取并记录结论。
- 原13个findings、4个open questions及RF1-RF4均有accepted decision、plan fix位置、`已修复`状态和residual分类。
- RF5已分类为本work unit implementation review/deepreview focus，明确非阻塞且不授权workflow cache或scope expansion。
- plan completion已改为`ACCEPTED`，next entry point为Slice 1 implementation。
- 只更新本plan与现有adjudication artifact；未实现代码、测试或README，未提交。

实现测试、pyright、coverage与docs命令仍只属于后续approved implementation slices；本gate未执行。

## Residual Risks

| 风险 | 分类 | owner / destination |
| --- | --- | --- |
| 同request/同document一般并发success/skip收敛 | assigned to later work unit | `UF-FIX10` |
| fresh company meta warning | assigned to later work unit | `UF-FIX11` |
| material existing-source repair | assigned to later work unit | 后续独立work unit |
| 旧schema corpus读取/迁移 | assigned to later work unit | 后续显式migration work unit |
| UF-PF08、UF-PF12真实CLI post-fix evidence | assigned to later work unit | evidence work unit |
| registry/oracle仍描述fix前状态 | assigned to later work unit | registry/evidence adjudication |
| governance外manual filesystem writer | tracked by existing operational policy | storage operational policy |
| RF5：exact-target whole-kind scan潜在成本放大 | covered by later approved slice | 本work unit implementation review与aggregate deepreview；只观察/记录，不授权workflow cache或scope expansion |

没有unclassified residual risk，没有blocking question。

## Final Decision

`ACCEPTED`。

两路终审均确认RF1-RF4已修复且无blocker；RF5已有非阻塞owner与授权边界。下一入口是
`Slice 1：冻结 public integrity/state/repair contracts` implementation。本gate禁止且未执行提交或PR动作。
