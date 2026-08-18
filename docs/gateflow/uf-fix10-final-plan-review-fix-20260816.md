# UF-FIX10 same-request-concurrency final plan review fix

## 0. Gate 元数据

- work unit：`UF-FIX10 same-request-concurrency`
- gate：`final plan review -> Controller fix`
- 日期：2026-08-16
- 当前分支：`codex/upload-filing-oracle`
- reviewed target：`docs/gateflow/uf-fix10-same-request-concurrency-plan-20260816.md`
- final review artifact：`docs/reviews/plan-review-20260816-231939-ds.md`
- 前序 fix artifacts：`docs/gateflow/uf-fix10-plan-review-fix-20260816.md`、`docs/gateflow/uf-fix10-plan-rereview-fix-20260816.md`
- Controller decision：接受DS最终review F-1/F-2并提升为blocking findings C-F1/C-F2；不接受F-1建议的expected-red处理，改为重划S1/S2 activation boundary；F-2选择模块级唯一meta owner方案
- scope：只修订plan并新增本artifact；不修改生产代码、测试、README，不运行pytest/pyright，不commit
- changed files：`docs/gateflow/uf-fix10-same-request-concurrency-plan-20260816.md`、`docs/gateflow/uf-fix10-final-plan-review-fix-20260816.md`
- completion status：`FIX COMPLETE / RE-REVIEW REQUIRED / IMPLEMENTATION NOT AUTHORIZED`
- artifact path：`docs/gateflow/uf-fix10-final-plan-review-fix-20260816.md`
- next entry point：`re-review`

## 1. 第一性原理裁决

两项finding的动机均成立，但C-F1不能靠声明expected red关闭：

1. S1若先删除filing preparation early-skip、让identical继续conversion，却尚未把shared publication route接入SEC/CN/HK，现有workflow会把本应`skipped`的请求按旧commit路径投影为`uploaded`。这不是无害的测试红态，而是一个真实、可被执行的错误中间语义。因此正确修复是把observable activation boundary整体后移：S1只落地不接线的owner contract/infrastructure并保持完整Fins suite全绿；S2一次性切换prepare、shared route、三条workflow与tests。
2. create-overwrite fresh rebase需要重建staging meta。现有 `_build_upsert_meta()` 不依赖实例状态，却是实例方法；若rebase另写九字段逻辑，会形成两个durable meta真源。正确修复是把它提升为 `docling_upload_service.py` 模块级私有唯一owner，让existing prepare与rebase共同调用；document version从fresh meta重算，revision继续由storage source-document owner新写。

两项都属于当前work unit的sequencing/semantic-owner正确性，不是新目标或额外hardening。

## 2. Findings 裁决与 fix 状态

| finding | Controller 裁决 | fix 状态 | plan closure | residual classification |
| --- | --- | --- | --- | --- |
| C-F1：S1先改变filing preparation但S2尚未接线，会造成现有Fins workflow回归 | `accepted`；拒绝expected-red路径，采用activation-boundary重划 | `已修复` | §3.2、§5、§6.3、§6.5、§7.1、§8-§11、§13-§14一致冻结：S1只新增types/protocol、batch fresh reader、pure arbitration helper、Docling helpers/meta-owner refactor与owner tests；现有filing early-skip及SEC/CN/HK行为不变，完整`tests/fins`必须全绿。filing identical继续conversion、typed disposition接线、shared publication route及workflow tests全部进入S2同一原子slice；allowed files、validation、success signals、prerequisites、goal mapping与stop conditions同步更新 | `fixed in current slice`（plan fix）；DS R-1同源风险已从根因消除，不保留expected-red residual |
| C-F2：create-overwrite rebase未pin staging meta唯一构造owner | `accepted`；选择模块级helper方案 | `已修复` | §5/§6.3/§8-§11/§13-§14冻结：将不依赖`self`的 `_build_upsert_meta()` 提升为模块级私有唯一九字段owner，existing prepare与fresh rebase共同调用，禁止复制；rebase以fresh previous meta保持`first_ingested_at/created_at`，同fingerprint version保持、异fingerprint递增；revision不进入Docling meta真源，由storage owner真正写入时新建；S1 owner tests与S2端到端test均精确断言 | `fixed in current slice`（plan fix）；无meta-owner residual |

没有`rejected-with-reason`、`deferred-with-owner`或`needs-more-evidence` finding；C-F1/C-F2均为`accepted / 已修复`。

## 3. C-F1 slice closure

### 3.1 S1 behavior-preserving boundary

- S1 allowed production scope只包含storage typed contract/reader实现、pure arbitration helper、Docling helper与meta-owner refactor、typed failure contract；不编辑SEC/CN/HK workflow。
- S1不把closed disposition接入`prepare_upload()`，filing identical仍按现有路径early `skipped`且converter不执行。
- S1不新增可达的`execute_prepared_filing_publication()` lifecycle route；pure arbitration只由owner tests直接消费。
- S1 validation显式包含完整`pytest tests/fins -q`，expected completion signal要求全绿、无expected red、全部market workflow observable不变。
- 若S1出现任一existing Fins红测、identical继续conversion、shared route可达或workflow变化，必须stop并返回plan review，不得提前改S2文件补偿。

### 3.2 S2 atomic activation boundary

- `docling_upload_service.py`、`filing_upload_publication.py`、SEC/CN/HK workflow及对应Docling/publication/workflow/runtime tests全部进入S2 allowed files。
- S2在同一implementation/review slice同时完成：filing identical继续conversion、required typed disposition接线、pure arbitration接入双cancel-checkpoint batch lifecycle、SEC/CN/HK改走shared route、workflow assertions迁移。
- S2 prerequisites要求S1 focused/full-Fins/pyright全绿且existing behavior未变；S2 completion要求focused/full-Fins继续全绿。
- 不接受prepare已切换但workflow/tests未迁移，或tests先接受未来行为但production尚未接线的中间checkpoint。

## 4. C-F2 owner closure

- 唯一owner：`dayu/fins/pipelines/docling_upload_service.py::_build_upsert_meta()`模块级私有helper。
- 唯一九字段集合：`updated_at`、`first_ingested_at`、`created_at`、`document_version`、`source_fingerprint`、`ingest_complete`、`source_provider`、`is_deleted`、`deleted_at`。
- existing prepare与`rebase_prepared_filing_create_overwrite()`必须共同调用该helper；禁止复制、局部更新或在publication owner重建meta。
- rebase先用fresh previous meta与prepared fingerprint调用现有 `_resolve_document_version()`：同fingerprint保持fresh version，异fingerprint在fresh version上递增；随后由唯一meta helper保持fresh `first_ingested_at/created_at`并构造staging meta。
- Docling staging meta不拥有revision。真正source write继续由storage source-document owner剔除producer revision并写入新revision；owner test与S2 create-overwrite route test分别断言职责边界和端到端结果。

## 5. Validation

- `git diff --check`：通过，exit 0，无输出。
- 两个未跟踪目标artifact分别执行`git diff --no-index --check /dev/null <artifact>`：无whitespace-error输出；exit 1只表示相对`/dev/null`存在预期diff。
- 结构自检：通过；C-F1/C-F2各有唯一`accepted / 已修复`记录；plan包含S1 full-Fins green/no-expected-red、S2 atomic activation、双slice allowed files/validation/prerequisites/goal mapping、模块级meta owner、fresh时间/version与storage revision断言，以及“没有未分类residual risk”。
- scope自检：只修改plan并新增本artifact；未修改生产代码、测试、README，未产生staged变更。
- 本fix gate按用户要求未运行pytest、coverage或pyright。

## 6. Docs decision

- 本fix gate不修改任何README。
- accepted plan中的README决策只在S2完整实现落地后执行；当前artifact不把未来行为写成已实现事实。

## 7. Residual risks

- DS最终review R-1与C-F1同源，已通过消除错误中间态关闭，不再保留为residual。
- DS最终review R-2/R-3仍是已冻结、已分类的设计tradeoff，分别由S2 README/route tests与strict identity tests覆盖；不构成blocking或未分类风险。
- DS最终review R-4中的SHA-256理论碰撞、post-`COMMITTED` guard release、manual writer、UF-FIX11、material concurrency及oracle/scenario/evidence事项继续由plan列明later-work-unit owner。
- C-F2的meta构造漂移风险已由唯一owner与精确owner/route断言关闭，不留implementation自行选择。

没有未分类residual risk，没有blocking open question。

## 8. Completion

- decision：`Controller final plan review fix pass; re-review required`
- finding status：C-F1/C-F2全部`accepted / 已修复`
- implementation authorization：未授权；本artifact不实现任何生产或测试代码
- tests/pyright/README：按本gate禁令未运行、未修改
- commit：未创建，且本gate禁止commit
- next entry point：`re-review`
