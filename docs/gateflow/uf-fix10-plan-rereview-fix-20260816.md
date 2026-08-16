# UF-FIX10 same-request-concurrency plan re-review fix

## 0. Gate 元数据

- work unit：`UF-FIX10 same-request-concurrency`
- gate：`re-review -> Controller fix`
- 日期：2026-08-16
- 当前分支：`codex/upload-filing-oracle`
- reviewed target：`docs/gateflow/uf-fix10-same-request-concurrency-plan-20260816.md`
- re-review artifacts：`docs/reviews/plan-review-20260816-224957.md`、`docs/reviews/plan-review-20260816-225732.md`
- 前序 fix artifact：`docs/gateflow/uf-fix10-plan-review-fix-20260816.md`
- Controller decision：两路 re-review 虽均为`pass`，仍将 DS residual R1/R2 提升为 accepted findings C-R1/C-R2；无 rejected/deferred finding
- scope：只修订plan并新增本artifact；不修改生产代码、测试、README，不运行测试/pyright，不commit
- changed files：`docs/gateflow/uf-fix10-same-request-concurrency-plan-20260816.md`、`docs/gateflow/uf-fix10-plan-rereview-fix-20260816.md`
- completion status：`FIX COMPLETE / RE-REVIEW REQUIRED / IMPLEMENTATION NOT AUTHORIZED`
- artifact path：`docs/gateflow/uf-fix10-plan-rereview-fix-20260816.md`
- next entry point：`re-review`

## 1. 第一性原理裁决

两项 residual 的动机均成立，且不能留到实现或code review阶段再解释：

1. C-R1 触及已冻结的显式action业务语义。现有 `_can_skip_upload` 既是sequential identical skip的直接owner事实，plan若仅允许raw auto skip，就会把显式`update` identical重传从`skipped`改为publish ok。正确修复不是在workflow补action特例，而是让Docling preparation同源产生closed typed initial disposition，publication owner只在stable fresh view和strict identity/company条件下消费该事实。
2. C-R2 触及Host强约束下的取消优先级。`begin_batch()`可能长时间等待writer；只在SKIP terminal前观察取消，会让等待期间已取消的CONFLICT/PUBLISH candidate继续产生业务结果或mutation。正确owner是持有open batch token的publication owner，并且必须在fresh read前及closed arbitration后、mutation/terminal前各观察一次。

两项都是当前publication owner contract的必要正确性条件，不是额外hardening；提升为accepted finding没有扩大work unit。

## 2. Findings 裁决与 fix 状态

| finding | Controller 裁决 | fix 状态 | plan closure | residual classification |
| --- | --- | --- | --- | --- |
| C-R1：显式`update` identical sequential重传会从existing skipped漂移为publish ok | `accepted` | `已修复` | §3/§5/§6.3/§7.1-§7.4/§9-§13冻结filing专用`FilingInitialSkipDisposition`；Docling preparation基于既有`_can_skip_upload`同源产生`NOT_ELIGIBLE`或`IDENTICAL_PUBLICATION`，禁止bool/default；identical filing仍conversion并进入batch；stable + fresh action合法 + typed identical + exact identity + company keep保留sequential skip，含explicit update；changed收敛只允许`MISSING -> COMPLETE` raw auto/no-overwrite；explicit create/no-overwrite conflict，create-overwrite fresh rebase后publish | `fixed in current slice`（plan fix）；S1 owner tests + S2 route/terminal tests |
| C-R2：取消只在SKIP terminal前观察，等待writer期间取消仍可能投影CONFLICT/PUBLISH | `accepted` | `已修复` | §3/§5/§6.4/§7.1/§7.5/§9-§13冻结双checkpoint：取得token后、fresh read/arbitration前立即观察；closed arbitration后、任何company/source mutation或SKIP/CONFLICT terminal前再次观察；任一命中rollback-first cancelled，rollback失败path-free `STORAGE_IO`；进入existing commit ownership后保持既有late-cancel boundary | `fixed in current slice`（plan fix）；S1三候选owner tests + S2 route tests |

没有`rejected-with-reason`、`deferred-with-owner`或`needs-more-evidence` finding；C-R1/C-R2均为`accepted / 已修复`。

## 3. Codegen-ready closure

### 3.1 C-R1 contract closure

- typed disposition只属于filing prepared candidate；material继续使用既有mutation/early-skip路径，不携带伪造的filing事实。
- `IDENTICAL_PUBLICATION`只由preparation当时现有 `_can_skip_upload` 真源产生；publication owner禁止从raw action、fingerprint或bool重算。
- stable retransmission preservation与changed concurrency convergence是两套互斥predicate：前者保留sequential explicit update，后者只收敛`MISSING -> COMPLETE` raw auto/no-overwrite exact winner。
- changed `COMPLETE -> COMPLETE` 不论raw auto或explicit update，即使prepared/durable exact equal也不得冒充stable retransmission；固定typed conflict。
- explicit `create` + `overwrite=False` 的`MISSING -> COMPLETE`保持typed conflict；`create` + `overwrite=True`由Docling owner用fresh previous meta重绑prepared plan后publish，保持既有replace-existing语义。

### 3.2 C-R2 lifecycle closure

- checkpoint 1在线性获得writer token后立即执行，早于fresh read和arbitration，因此等待writer期间的取消不会读取或产生业务裁决。
- checkpoint 2在closed arbitration后立即执行，早于company stage、reset/store/create/commit及SKIP/CONFLICT terminal，因此三类候选使用同一cancel-first规则。
- 两个checkpoint均以rollback成功作为返回cancelled的前提；rollback失败固定为path-free `STORAGE_IO`，不得谎报cancelled/skip/conflict。
- PUBLISH通过checkpoint 2并进入既有commit ownership后，不增加第三套取消规则，继续遵守现有late-cancel/commit boundary。

## 4. 精确测试与成功信号更新

plan已加入或修正以下必须断言：

1. explicit `update` identical stable sequential重传仍`skipped`、stored=0，revision/document version/tree/meta/manifest均不变。
2. concurrent changed explicit `update`为不等价typed `SOURCE_PUBLICATION_CONFLICT`；stable且内容变化的显式update仍publish。
3. changed `MISSING -> COMPLETE`仅raw auto + `overwrite=False` + exact identity + company keep可skip；explicit create/no-overwrite conflict，create-overwrite publish。
4. filing identical仍conversion并携带closed disposition进入batch；material prepare/skip/publication结果不变。
5. 在writer barrier等待期间取消原本会走SKIP、CONFLICT、PUBLISH的三类candidate，均cancelled、rollback=1，fresh read/arbitration/company/source mutation/commit/业务terminal为0。
6. 第二checkpoint同样覆盖三类closed裁决；rollback失败为`STORAGE_IO`；进入existing commit ownership后的late cancel保持既有行为。

状态表、success signals、slice goal mapping、review focus、README落地决策、risks/open questions和completion report均已同步，未保留与C-R1/C-R2相反的旧规则。

## 5. Validation

- `git diff --check`：通过，exit 0，无输出。
- 未跟踪plan与本artifact分别执行`git diff --no-index --check /dev/null <artifact>`：无whitespace-error输出；exit 1仅表示相对`/dev/null`存在预期diff。
- 结构自检：通过；C-R1/C-R2各有唯一`accepted / 已修复`记录；plan包含closed typed disposition、stable/changed互斥predicate、create-overwrite publish、双cancel checkpoint、三候选取消测试及“无未分类residual risk”。
- scope自检：只修改plan并新增本artifact；未修改生产代码、测试、README，未产生staged变更。
- 本fix gate按用户要求不运行pytest、coverage或pyright。

## 6. Docs decision

- 本fix gate不修改任何README。
- accepted plan中的README决策只在后续实现落地后执行；当前仅修正计划内容，不把未来行为写成已实现事实。

## 7. Residual risks

- DS re-review R1/R2已提升为C-R1/C-R2并在当前plan fix中关闭，已从residual集合移除。
- DS R3保持已分类低风险：S1四个fixture文件只允许required-field机械diff；若实现验证出现真实断言语义冲突，implementation Agent必须stop并返回plan review，不得扩大fixture或生产兼容逻辑。
- plan原有SHA-256理论碰撞、post-`COMMITTED` guard release、manual filesystem writer、UF-FIX11、material concurrency及evidence/oracle事项均已有明确later-work-unit owner，分类不变。

没有未分类residual risk，没有blocking open question。

## 8. Completion

- decision：`Controller fix pass; re-review required`
- finding status：C-R1/C-R2全部`accepted / 已修复`
- implementation authorization：未授权
- tests/pyright/README：按本gate禁令未运行、未修改
- commit：未创建，且本gate禁止commit
- next entry point：`re-review`
