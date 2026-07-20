# WU-SEMANTIC-OWNERSHIP-01 / R07 Completion Evidence — AgentCodex

## 1. Gate 身份、结论与写边界

- **umbrella WU**：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- **internal remediation sub-WU**：R07 Fins storage snapshot 与 opaque identity；不是新 WU，不是 umbrella closeout，也不是 R08。
- **当前 gate**：R07 accepted implementation commit 之后的 completion evidence gate。
- **结论**：R07 的 accepted plan、S1/S2/S3 累计实现、全部 review/fix/re-review 与最终 complete-tree finding 已闭合；**R07 COMPLETE**，当前 artifact 已完成并停回 **Controller validation**。
- **umbrella 状态**：`WU-SEMANTIC-OWNERSHIP-01` **未完成**；R08—R12 与后续 umbrella aggregate deepreview/closeout 尚未执行。
- **本 gate 唯一写入**：`docs/reviews/wu-semantic-ownership-01-r07-completion-codex.md`。
- **明确未做**：未修改 production、tests、README、control、design、accepted plan或旧 artifact；未 stage、commit、push、创建/修改 PR；未进入 R08 implementation；未实施 Issue 142/151/175/177/178 或统一 authorization。

第一性原理判断仍成立：opaque external identity 不应由路径组件规则定义，source publication revision 不应由 consumer 选择字段后重算，多文件/processor/citation 一致性也不能由 before/after double-read 恢复。正确 owner 是 `dayu.fins.storage` 的 identity mapping、complete-source published revision 与 stable snapshot；read runtime只拥有 snapshot-backed cache/borrow/resource lifecycle。accepted tree 已在这些 owner boundary 完成修复，不需要下游 fallback、compatibility shim、第二 mapping truth 或统一 authorization framework。

## 2. Accepted plan、transition 与 implementation commit lineage

| fact | exact value | 只读核验 |
| --- | --- | --- |
| accepted plan commit | `3b52ab112e37233f4f6452793cb18c15c204636d` | subject `docs: accept R07 Fins snapshot remediation plan` |
| accepted plan parent | `5f09e2cc2e4edfc7dc1388e14744bf1300637093` | 与 accepted-plan gate transition 一致 |
| accepted plan tree | `bedfef2d5fc98cff9f1fe3616e3440dedbec74bb` | 11-path plan/evidence/control transaction |
| accepted plan content SHA-256 | `ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1` | 从 accepted plan commit 的 plan blob直接计算；当前文件复算相同 |
| implementation transition commit | `386fef8d7a7ecbd977c455ca86bb8bab875d1a98` | subject `docs: enter R07 opaque identity implementation` |
| transition parent | `3b52ab112e37233f4f6452793cb18c15c204636d` | accepted plan commit 的直接子提交 |
| transition tree | `537905feab4cf804f73cbdc782d5dc4c136f65ab` | 仅更新 `docs/host/issues-implementation-control.md` |
| accepted implementation commit | `64dbfbaf10444f20b6a835604345e0b409dbbc49` | subject `fins: accept R07 storage snapshot remediation` |
| accepted implementation parent | `386fef8d7a7ecbd977c455ca86bb8bab875d1a98` | 精确唯一 parent；merge-base/ancestor关系通过 |
| accepted implementation tree | `5efd7a63bffda159ec87b313b805a4f6ce32aa54` | exact 60-path tree transaction |
| accepted implementation diff stat | `60 files changed, 20104 insertions(+), 3758 deletions(-)` | `git show --shortstat` 直接读取 |
| completion preflight HEAD | `64dbfbaf10444f20b6a835604345e0b409dbbc49` | HEAD 与 accepted implementation tree完全一致 |

lineage 精确为：

```text
5f09e2cc2e4edfc7dc1388e14744bf1300637093
  -> 3b52ab112e37233f4f6452793cb18c15c204636d  accepted plan
  -> 386fef8d7a7ecbd977c455ca86bb8bab875d1a98  implementation transition
  -> 64dbfbaf10444f20b6a835604345e0b409dbbc49  accepted implementation
```

accepted plan commit 的 exact 11-path closure 为：

```text
M docs/host/issues-implementation-control.md
A docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md
A docs/reviews/wu-semantic-ownership-01-r07-plan-entry-controller-validation.md
A docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-review-mimo.md
A docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-review-ds.md
A docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-review-controller-adjudication.md
A docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-fix-codex.md
A docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-fix-controller-validation.md
A docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-rereview-mimo.md
A docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-rereview-ds.md
A docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-rereview-controller-adjudication.md
```

## 3. Accepted implementation commit exact 60-path scope

以下清单直接来自 `git diff-tree --no-commit-id --name-status -r 64dbfbaf...`，不是从 plan allowlist反推。

### 3.1 Production：20 paths

```text
M dayu/fins/domain/document_models.py
M dayu/fins/ingestion_runtime.py
M dayu/fins/pipelines/sec_6k_primary_document_repair.py
M dayu/fins/pipelines/sec_fiscal_fields.py
M dayu/fins/service_runtime.py
M dayu/fins/storage/_fs_blob_core.py
M dayu/fins/storage/_fs_company_meta_core.py
A dayu/fins/storage/_fs_identity.py
M dayu/fins/storage/_fs_maintenance_core.py
M dayu/fins/storage/_fs_processed_core.py
M dayu/fins/storage/_fs_source_document_core.py
A dayu/fins/storage/_fs_source_snapshot.py
M dayu/fins/storage/_fs_storage_infra.py
M dayu/fins/storage/_fs_storage_utils.py
M dayu/fins/storage/fs_source_document_repository.py
M dayu/fins/storage/repository_protocols.py
M dayu/fins/tools/cache.py
M dayu/fins/tools/error_contract.py
M dayu/fins/tools/fins_tools.py
M dayu/fins/tools/read_runtime.py
```

### 3.2 Tests：7 paths

```text
M tests/fins/test_fins_ingestion_runtime.py
M tests/fins/test_fins_read_runtime.py
M tests/fins/test_fins_storage_atomicity.py
M tests/fins/test_fins_storage_provider.py
M tests/fins/test_processor_read_consistency.py
M tests/fins/test_read_runtime_semantic_ownership_guards.py
M tests/fins/test_sec_pipeline_download.py
```

`tests/fins/test_financial_read_contracts.py` 属于 accepted cumulative validation allowlist，但最终无需产生 diff，因此不在 commit path set中。

### 3.3 README：2 paths

```text
M dayu/fins/README.md
M tests/README.md
```

### 3.4 S1/S2/S3 implementation/review/fix/re-review/Controller artifacts：30 paths

```text
A docs/reviews/wu-semantic-ownership-01-r07-s1-implementation-codex.md
A docs/reviews/wu-semantic-ownership-01-r07-s1-controller-validation.md
A docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-mimo.md
A docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-ds.md
A docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-controller-adjudication.md
A docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-fix-codex.md
A docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-fix-controller-validation.md
A docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-rereview-mimo.md
A docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-rereview-ds.md
A docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-rereview-controller-adjudication.md
A docs/reviews/wu-semantic-ownership-01-r07-s2-implementation-codex.md
A docs/reviews/wu-semantic-ownership-01-r07-s2-controller-validation.md
A docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-mimo.md
A docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-ds.md
A docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-controller-adjudication.md
A docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-fix-codex.md
A docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-fix-controller-validation.md
A docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-rereview-mimo.md
A docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-rereview-ds.md
A docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-rereview-controller-adjudication.md
A docs/reviews/wu-semantic-ownership-01-r07-s3-implementation-codex.md
A docs/reviews/wu-semantic-ownership-01-r07-s3-controller-validation.md
A docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-mimo.md
A docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-ds.md
A docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-controller-adjudication.md
A docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-fix-codex.md
A docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-fix-controller-validation.md
A docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-rereview-mimo.md
A docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-rereview-ds.md
A docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-rereview-controller-adjudication.md
```

### 3.5 Control：1 path

```text
M docs/host/issues-implementation-control.md
```

总计：`20 production + 7 tests + 2 README + 30 artifacts + 1 control = 60 paths`。commit 中无 plan外 product/test、design、旧 artifact、`workspace/tmp`、R08+、deferred Issue或统一 authorization path。

## 4. Final semantic owner contract

### 4.1 Opaque external identity 与 fresh schema

- caller/domain 产生 exact external ticker/document identity；storage 不 strip、不大小写折叠、不 Unicode normalization，也不把 identity 当 filename/path component。
- storage 私有 identity owner按 namespace 派生 filesystem-safe private locator；locator grammar、prefix、长度、alphabet与算法不是 public/README/tool/LLM contract。
- `.identity.json` descriptor是 directory到 exact external identity 的唯一 round-trip truth；point lookup、enumeration、target/staging/backup、journal recovery、company inventory、source/material、processed、rejected、blob与maintenance都交叉验证 descriptor。
- descriptor missing/corrupt/namespace mismatch/external mismatch/collision/symlink一律 fail closed；没有scan fallback、reverse registry、旧 layout探测或双写。
- 这是 fresh schema cutover：不读取或迁移 `portfolio/<raw identity>/...` 旧布局，不提供compatibility alias/facade。
- lock/backup/private directory name只发现private candidate；business ticker/document ID只能从已验证descriptor/meta/manifest投影。lock-only inventory不投影private key。

### 4.2 Persisted published revision

- `SourceDocumentRevision` 只保留非空opaque `token`作exact equality；旧 `digest` 字段、`sha256:` grammar、selected-field hash builder与compat property均已删除。
- complete-source mutation/publication owner在create/update/replace/delete/restore的最终完整meta写入前生成token；producer不能注入或选择token。
- token与R06完整source tree在同一个batch commit point发布；rollback/precommit crash不改变published token，processed/company/maintenance-only batch保留原token。
- delete/reset后source、token与snapshot resource同时不存在；snapshot read返回明确missing，不从历史值或consumer hash恢复。
- private token算法不进入tool result、citation、README业务承诺或LLM-facing文本。

### 4.3 Stable light/full snapshot 与错误优先级

- source repository只提供一个typed snapshot read语义；storage在同一publication guard内拥有source-kind `0/1/2` resolution、exact identity、meta、provenance、revision、ordered files与primary filename。
- light snapshot不暴露published path/local URI；full snapshot从guard内打开的regular-file descriptors复制到snapshot-owned temp tree，processor只见该temp tree中的标准`Source`。
- post-copy再次核对persisted revision与descriptor。只有真实publication marker变化才丢弃attempt并有界重取；consumer不再做before/after double-read或retry。
- revision/descriptor未变时的inode/content/EOF/fstat/declared-size/hash异常是corruption/validation failure，不被伪装成`source_changed_during_read`。
- sustained publication churn只由storage抛typed consistency exhaustion；read runtime在单一owner处映射既有`ErrorCode.SOURCE_CHANGED_DURING_READ`。ordinary I/O、corruption、decode、not-found与cancellation保持各自typed边界。
- snapshot close显式、幂等、关闭后不可读；首次temp-root删除失败时保留cleanup locator供public close重试，不依赖`__del__`或OS自动回收。

### 4.4 Read/cache/borrow/citation 同源

- generic LRU只返回replacement/eviction/clear移出的值，不猜测资源close语义。
- `FinsReadRuntime`私有entry同时拥有processor、source meta、full snapshot、revision、source kind与provenance；独立meta cache已删除。
- active borrow覆盖processor调用、semantic enrichment、cross-document diagnosis、result与citation构造；retire后不再新借，最后一个borrow release后才关闭snapshot。
- same-document creation lock内按full snapshot再次double-check；只发布一个matching processor，losing snapshot立即关闭。
- runtime close与cache publication由同一lifecycle lock线性化：close-first禁止事后live publication，publication-first允许active borrow完成后清理。
- creation-lock registry使用weak-value lifecycle；重叠same-key caller靠局部强引用共享同一lock，历史missing/evicted key不被runtime永久拥有。
- citation机械投影当前borrowed snapshot的typed provenance；不按ticker/document重读repository、不从URI/provider字符串猜source，也不与另一version的result拼接。
- exact document read的source kind由storage typed resolution拥有；alias fallback枚举两个typed namespace并拒绝跨kind多文档歧义，不再filing-first。
- `list_documents`继续组合filing/material两个typed list projection，不新增batch snapshot API或per-document full-snapshot N+1。

### 4.5 Composition 与cleanup

- preprocess在same-ticker batch writer mutex后取得full snapshot，processor完成并关闭snapshot后才commit；precommit失败exactly-once rollback，commit开始后不二次rollback。
- SEC fiscal multi-file与active 6-K candidate assessment各自消费一份full snapshot；既有filename lowercase map、排序、suffix与XML fallback选择算法不变，没有提前实现R08 financial/XBRL分类。
- `DefaultFinsRuntime.close()`保持lazy/idempotent；未创建read runtime时不反向创建，close后新read fail fast。
- `_FinsReadProcessTarget`在completed、typed/business failed与unexpected execution failed三路都关闭runtime。首次public close失败后只执行一次同一public idempotent close follow-up；不访问private pending state，不新增cancelled envelope或Host/process-isolation语义。
- follow-up仍失败时只记录稳定的action/type/errno诊断；不泄漏raw message、path、key、revision、cause或traceback，原primary outcome不漂移。

## 5. Security retained / modified / non-leak boundary

| boundary | final disposition | accepted evidence |
| --- | --- | --- |
| external identity separator/dot/drive/absolute-looking文本 | **有意修改**为exact opaque identity round-trip | Unicode、层级、separator、drive-like、`.`/`..`、absolute-looking ticker/document IDs跨namespace通过 |
| filename/entry name | **保留严格单路径组件** | empty、dot/dotdot、separator、absolute/drive继续拒绝 |
| local URI/object key | **保留并收紧owner** | 只含private keys+safe filename；absolute、empty segment、traversal、backslash与symlink escape拒绝 |
| containment | **保留** | target/staging/backup/source/processed/rejected/snapshot temp均经contained-path/regular-file owner校验 |
| symlink | **保留并扩展** | identity descriptor、meta、manifest、business files、recovery与snapshot nodes均fail closed |
| atomic write/fsync | **保留** | descriptor与meta复用same-dir temp、flush/fsync、`os.replace`、parent fsync |
| R06 writer/publication/recovery | **保留** | writer mutex、短publication guard、minimal journal、crash phase与old/new完整性未退化 |
| exception graph | **收紧** | public storage error的`str/args/notes/cause/context/traceback`不暴露workspace/private locator；保留typed category/errno |
| revision/citation | **同源** | token由publication owner产生；citation/result来自同一borrowed snapshot，provider guessing为0 |
| LLM-facing result | **non-leak** | 9个read tools的completed/failed/cancelled及citation nested JSON递归测试禁止revision/private key/temp path/`local://` |
| authorization | **未触碰** | 没有Host principal/policy/capability/sandbox或统一tool authorization实现 |

关键旧路径扫描最终状态：

- raw external ticker/document ID直接参与path/object-key/lock/backup/staging join：`0`；
- private directory/lock/backup name反推business identity：`0`；
- `get_source_revision`、`_build_source_revision`、`revision_before`、`revision_after`：`0`；
- Fins source revision `.digest`字段访问：`0`；唯一命中为negative guard字符串；
- production `_resolve_source_kind`/filing-first probe：`0`；
- citation/provenance direct repository reread：`0`；
- pipeline raw repository source materialize：`0`；剩余materialize均消费snapshot-provided或processor-owned标准`Source`；
- `source_changed_during_read`只有`error_contract.py` code owner与read runtime单点mapping。

## 6. Complete finding ledger

### 6.1 Plan review / fix / re-review

| original finding/group | final disposition |
| --- | --- |
| MiMo `R07-PR-F01` coverage line-gate口径 | **CLOSED by `R07-PF-01`** |
| MiMo `R07-PR-F02` S3两个base F401未点名 | **CLOSED by `R07-PF-02`** |
| MiMo `R07-PR-F03` required source-kind/read-runtime解析建议 | **REJECTED WITH DESIGN EVIDENCE**；source repository拥有typed kind，storage `0/1/2` resolution保留 |
| MiMo `R07-PR-F04` revision字段仍暗示hash | **CLOSED by `R07-PF-03`**；breaking `digest -> token` |
| DS `F-R07-DS-01` lock-stem反推business ticker | **CLOSED by `R07-PF-04`** |
| DS `F-R07-DS-02` maintenance以private child name做`fil_`判断 | **CLOSED by `R07-PF-05`** |
| DS `F-R07-DS-03` snapshot静态损坏/retry分类不清 | **CLOSED by `R07-PF-06`** |
| DS `F-R07-DS-04` token type与S2时序 | **CLOSED by `R07-PF-03`** |
| DS `F-R07-DS-05` SEC fiscal文件选择语义 | **CLOSED by `R07-PF-07`**；只换snapshot owner，不改算法 |
| DS `F-R07-DS-06` creation lock内缺double-check | **CLOSED by `R07-PF-08`** |
| DS `F-R07-DS-07` runtime recursive non-leak coverage | **CLOSED by `R07-PF-09`** |
| DS `F-R07-DS-08` delete/reset snapshot absence | **CLOSED by `R07-PF-10`** |
| DS `F-R07-DS-09` list path可能N+1 | **CLOSED by `R07-PF-11`**；不新增batch snapshot API |
| Controller duplicate-gate finding | **CLOSED by `R07-PF-12`**；S3 cumulative review是R07唯一complete-tree final review，umbrella aggregate仍保留 |

Plan最终状态：`R07-PF-01..12 = 12/12 closed`；原始accepted findings全部closed，1项design-rejected，new material finding `0`，open/deferred/blocker `0/0/0`。re-review的MiMo `R07-RR-F01`与DS `NEW-OBS-01`均为no-action implementation confirmation，不形成open finding。

### 6.2 R07-S1 opaque identity

| accepted finding | final state |
| --- | --- |
| `R07-S1-CR-F01` destructive cleanup complete preflight | **CLOSED** |
| `R07-S1-CR-F02` `begin_batch` primary-error preservation | **CLOSED** |
| `R07-S1-CR-F03` raw filesystem/private locator producer-boundary projection | **CLOSED** |
| `R07-S1-CR-CV-F01` complete exception graph仍泄漏locator | **CLOSED**，归入CR-F03同owner correction |

S1 rejected-with-reason ledger保持未实施：MiMo `F01/F03/F04/F05`与DS `F01/F02/F03/F05/F06/F07/F08`共11项。它们分别涉及删除既有`fil_`业务分类、改变exact identity、越过test allowlist、false import evidence、忽略corrupt recovery/inventory、错误processed existence owner、重复guard、`exist_ok`竞态、local trust边界与fixture producer关系；最终双路re-review确认均未被误实现。S1最终new accepted/deferred/blocker为`0/0/0`。

### 6.3 R07-S2 persisted revision + snapshot

| accepted finding | final state |
| --- | --- |
| `R07-S2-CV-F01` marker read主失败被guard release覆盖 | **CLOSED** |
| `R07-S2-CV-F02` close失败后丢失temp-root cleanup authority | **CLOSED** |
| `R07-S2-CV-F03` initial fstat主失败被stream close覆盖 | **CLOSED** |
| `R07-S2-CR-F01` consumer close failure覆盖active primary | **CLOSED**；统一由snapshot context lifecycle拥有 |

两路其余review observations均为design confirmation、pre-existing typed debt、已满足的真实filesystem集成覆盖或被拒绝的exact-identity替代方案；没有转成accepted deferred finding。S2最终new material/open/deferred/blocker为`0/0/0/0`。

### 6.4 R07-S3 read/cache/citation 与complete-tree review

| accepted finding | severity | final state |
| --- | ---: | --- |
| `R07-S3-CV-F01` decode/build failure缺temp-root删除证据 | validation | **CLOSED** |
| `R07-S3-CV-F02` pre-publish cancellation cleanup/priority | validation | **CLOSED** |
| `R07-S3-CV-F03` process target三终态close覆盖 | validation | **CLOSED** |
| `R07-S3-CV-F04` docstring/comment/coverage/close后Raises文本收敛 | validation | **CLOSED** |
| `R07-CR-F01` close返回后仍可发布live entry/temp leak | HIGH | **CLOSED**；lifecycle lock线性化 |
| `R07-CR-F02` creation-lock registry无界增长 | MEDIUM | **CLOSED**；weak-value owner lifecycle |
| `R07-CR-F03` process target丢失public cleanup retry authority | LOW | **CLOSED**；一次public follow-up close |

MiMo对`R07-CR-F01`的错误具体root cause被Controller拒绝，但其最终fix-required gate结论已由正确的close/publication race承接；DS关于OS自动回收ordinary `mkdtemp` tree与GIL线程安全的初稿证据已在同任务修正，不改变PASS verdict。其余MiMo/DS observations为no-action、pre-existing debt、evidence-invalid或bounded/inherited risk，没有open accepted finding。

### 6.5 Final cumulative ledger

```text
accepted plan groups: 12 closed
S1 accepted groups: 4 closed
S2 accepted groups: 4 closed
S3 validation groups: 4 closed
complete-tree accepted groups: 3 closed
new material finding: 0
open: 0
deferred from R07 review: 0
needs-more-evidence: 0
blocker: 0
```

不存在把accepted finding改写成“后续优化”或转移给R08/Issue的情况。

## 7. Validation evidence

### 7.1 本 completion gate 独立只读复验

所有Python命令均在`source .venv/bin/activate`后执行。

| validation | result |
| --- | --- |
| final 7 exact owner nodes | `7 passed, 3 warnings in 1.31s` |
| cumulative 8 R07 test files | `494 passed, 3 warnings in 26.25s` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| 20 production + 8 validation-test scoped Ruff | `All checks passed!` |
| full Ruff fingerprint | inherited `150`：`F401=70, E402=66, F841=10, F541=3, F821=1` |
| formal directory suite | `4883 passed, 3 failed, 3 skipped, 5 deselected, 3 warnings in 121.52s` |
| inherited three-node isolation | `1 passed, 2 failed in 0.35s` |
| accepted implementation diff check | `git diff --check 386fef8d... 64dbfbaf...` PASS |
| completion pre-artifact staged/worktree | staged empty；worktree clean；HEAD=`64dbfbaf...` |

三条warning均来自installed `edgar` package既有deprecation warning，不是R07新增类型。

### 7.2 Formal inherited failure ledger

formal suite三项failure的六字段保持accepted plan §1.1指纹，不得被解释为R07豁免或修复授权：

| node | rule/type | stable location | current text fingerprint | isolation | owner/destination |
| --- | --- | --- | --- | --- | --- |
| `tests/runtime/test_log.py::test_configure_does_not_touch_root_by_default` | order-dependent `AssertionError` | `tests/runtime/test_log.py:101` | root logger仍有一个Dayu marker `StreamHandler` | isolated PASS | Runtime logging/test-order owner |
| `tests/service/test_host_admin.py::test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets` | `ConfigFieldError` | `dayu/runtime/config_loader.py:2303` | `missing required fields: ['wait_poller_policy']` | isolated FAIL，同指纹 | Service host-admin fixture/config owner |
| `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers` | `AssertionError` | `tests/service/test_import_boundary.py:101` | 仍仅`fins_wait_adapter.py`/`host_assembly.py`导入`_ingestion_tool_helpers` | isolated FAIL，同指纹 | Service import-boundary owner |

没有新增node、rule/error type、stable location或text fingerprint。裸`pytest -q`的`workspace/tmp/r06-base-9c07b88d` collection条件未被删除来制造绿色结果。

### 7.3 Final 20-file line coverage（accepted Controller evidence）

以下为最终fix/re-review/Controller链对coverage JSON按`covered_lines / num_statements`复算的line coverage；本 completion gate没有生成新的coverage artifact：

| production file | line coverage |
| --- | ---: |
| `dayu/fins/domain/document_models.py` | 96.30% |
| `dayu/fins/storage/_fs_identity.py` | 80.00% |
| `dayu/fins/storage/_fs_storage_utils.py` | 83.82% |
| `dayu/fins/storage/_fs_storage_infra.py` | 86.14% |
| `dayu/fins/storage/_fs_blob_core.py` | 88.06% |
| `dayu/fins/storage/_fs_company_meta_core.py` | 91.11% |
| `dayu/fins/storage/_fs_maintenance_core.py` | 92.39% |
| `dayu/fins/storage/_fs_processed_core.py` | 88.83% |
| `dayu/fins/storage/_fs_source_document_core.py` | 83.06% |
| `dayu/fins/storage/repository_protocols.py` | 100.00% |
| `dayu/fins/storage/fs_source_document_repository.py` | 96.10% |
| `dayu/fins/storage/_fs_source_snapshot.py` | 90.42% |
| `dayu/fins/ingestion_runtime.py` | 90.67% |
| `dayu/fins/pipelines/sec_fiscal_fields.py` | 92.11% |
| `dayu/fins/pipelines/sec_6k_primary_document_repair.py` | 82.32% |
| `dayu/fins/tools/cache.py` | 96.83% |
| `dayu/fins/tools/read_runtime.py` | 82.56% |
| `dayu/fins/tools/error_contract.py` | 100.00% |
| `dayu/fins/tools/fins_tools.py` | 85.80% |
| `dayu/fins/service_runtime.py` | 87.61% |

全部changed production file均`>=80%`，没有用branch composite或aggregate平均值替代逐文件line gate。

### 7.4 README decision

- `dayu/fins/README.md`已在accepted implementation commit中更新为current contract：opaque identity mapping、persisted revision、stable snapshot、resource-aware cache/borrow/citation。
- `tests/README.md`已同步owner-level测试职责：opaque round-trip、snapshot并发/损坏、resource cleanup、same-snapshot citation/non-leak。
- 根`README.md`无安装、初始化、CLI/Web/WeChat入口、命令、输出、日志、workspace或最终用户工作流变化，因此无diff。
- `dayu/README.md`分层/装配关系未变，因此无diff。
- `docs/fins/design.md`stable truth未变；本completion gate不机械同步README/design/control。

## 8. Residual owner / destination 与明确未越界范围

| residual / future work | classification | unique owner / destination | R07 disposition |
| --- | --- | --- | --- |
| financial/XBRL producer contract与LLM质量字段 | next numbered remediation | **R08 / Topic 6.4 plan gate** | R07只保证输入snapshot一致，不改financial业务结果 |
| direct-stream missing/duplicate/event-after-result validator | later remediation | **R09 / Topic 6.5** | 未实施 |
| HKEX cumulative `rowRange`完整性 | later remediation | **R10 / Topic 6.6** | 未实施 |
| upload shell/cmd workflow与placeholder surface | later remediation | **R11 / Topic 7.1/7.2** | 未实施 |
| current-schema init/secret/atomic reset | later remediation | **R12 / Topic 7.3** | 未实施 |
| workspace migration/future assets | existing deferred Issues | **Issue 142 / 151** | fresh schema，不迁移、不增加assets能力 |
| Fins long-operation process isolation | existing deferred Issue | **Issue 175** | 只完成read process target snapshot cleanup，不实现kill/escalation |
| output continuation/TruncationManager | existing deferred Issue | **Issue 177** | 未接通 |
| credential storage-state lifecycle | existing deferred Issue | **Issue 178** | 未触碰 |
| unified tool authorization | explicit no-current-authorization scope | **未来独立design/user authorization** | 未创建新WU/framework/policy/capability |
| 连续两次filesystem cleanup都失败后的bounded temp orphan | accepted bounded failure contract | **external temp hygiene / operations** | primary outcome与path-free diagnostic保留；不承诺OS自动回收，不授权第三次/无限/configurable retry |
| formal suite三项inherited failure | inherited ledger | **Runtime logging / Service config fixture / Service import boundary owners** | 未修、未豁免、未扩散 |
| full Ruff 150 | inherited repository debt | **各原文件owner** | R07 scoped Ruff为0；不顺手清理 |
| `edgar`三条deprecation warning | external dependency | **dependency maintenance owner** | 不阻塞R07 completion |
| non-CPython weak-ref GC回收可能延迟 | bounded implementation note | **read-runtime lifecycle owner** | 不影响same-key mutual exclusion或正确性，不形成open finding |

所有residual都有明确owner/destination；没有unclassified residual、needs-more-evidence或需要在R07内新建Issue的事项。deferred Issues与统一authorization没有被implementation、测试夹具、README或completion文本伪装成已完成能力。

## 9. Control state、completion commit 与R08 next entry

本 gate开始时，`docs/host/issues-implementation-control.md`的当前状态为：

- active work unit：既有`WU-SEMANTIC-OWNERSHIP-01`；
- gate：`R07 accepted implementation commit`；
- next entry point：先形成exact-scope accepted implementation commit，再做独立completion evidence/Controller validation与completion commit；R08只能在真实R07 completion commit SHA记录后开始；
- no authorization：R08—R12 implementation、Issue 142/151/175/177/178、统一authorization、push或PR。

accepted implementation commit `64dbfbaf...` 已真实存在，但commit内control无法自引用其未来SHA。本artifact因此记录真实commit lineage与completion evidence；用户明确禁止本agent修改control，当前control由Controller在下一gate拥有。

严格下一顺序只有：

```text
Controller validation of this R07 completion artifact
  -> exact-scope R07 completion-state local commit
  -> record the real completion commit SHA in Controller state
  -> R08 independent plan entry
```

- **R08 next entry不是R08 implementation授权**；必须先完成R08独立plan、review/fix/re-review与accepted-plan gate。
- completion-state commit的exact scope由Controller裁决，只应包含本artifact、Controller completion validation与Controller control transition；不得重新混入product/test/README或R08内容。
- 当前不得push、PR、umbrella aggregate deepreview或umbrella closeout。

## 10. Completion author self-check

- 已读取`AGENTS.md`、accepted R07 plan、全部plan review/fix/re-review/Controller链、全部S1/S2/S3 implementation/review/fix/re-review/Controller artifacts及control当前状态。
- accepted plan commit、plan blob SHA、transition commit、accepted implementation commit、唯一parent、tree hash、exact 60 paths与diff stat均从Git object直接核验。
- accepted implementation commit前后`git diff --check`通过；completion artifact创建前staged为空、worktree clean、HEAD精确为accepted implementation commit。
- 本gate独立复验7 owner nodes、累计8测试文件、full pyright、scoped/full Ruff、formal directory suite与inherited三节点隔离；结果与最终accepted evidence一致。
- security、opaque identity、snapshot/revision/citation/non-leak、resource lifecycle、composition close、formal inherited ledger与deferred boundary均有owner-level evidence；没有用间接日志或展示结果替代root-cause contract。
- 本gate唯一新增path为`docs/reviews/wu-semantic-ownership-01-r07-completion-codex.md`；没有修改其它文件，也没有stage/commit/push/PR。

## R07_COMPLETE / READY_FOR_CONTROLLER_VALIDATION
