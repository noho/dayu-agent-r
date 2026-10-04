# Plan Review（二轮独立复审 rereview2）：UM-O13-F01 重复 delete tombstone 幂等实施计划

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-1455ffb9

- Review 类型：`$planreview` adversarial plan review（独立反例核查，不实施、不改 plan）。本 artifact 文件名按总控指定的 gateflow 命名 `plan-review-o13-rereview2-mimo-20260929.md`。
- Review target：`docs/gateflow/upload-material-o13-tombstone-plan-20260929.md`（`plan review -> fix` 修订候选）。
- Target SHA-256：`fd7fef7080f48a6b208d12d0ecfad10009157618f05cf854186ceaf539690396`（实测 `shasum -a 256` 与总控锁定值一致）。
- Binding scope contract：`docs/gateflow/upload-material-o13-tombstone-goal-20260929.md`（goal confirmation；基线 HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`）。
- 裁决真源：`docs/gateflow/upload-material-o13-plan-review-adjudication-20260929.md`（MiMo F1–F4 + 追加 F5 裁决、Q3 裁决、二次 fix 候选 SHA 核对）。
- 前一轮 review：`docs/reviews/plan-review-20260929-043830.md`（MiMo 首轮，fail）。
- 证据基线：本 checkout `/private/tmp/dayu-upload-o13`，分支 `codex/upload-material-o13`，HEAD 实测 `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，与 goal 基线锁一致，预检通过。
- 本次 review 的实测证据（只读；覆盖率数据与缓存写在 `$TMPDIR`，`PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider`，未写入 checkout；未安装任何依赖）：
  - 计划五文件测试集独立复测：`407 passed, 3 warnings in 22.58s`。
  - `_fs_source_document_core.py` 覆盖率独立复测：`473 stmts / 97 miss / 79%`，与计划记录的 MiMo 基线逐字一致。
  - 缺口按函数归类实测（AST 归属）：`get_source_document_provenance 18`、`_list_document_ids_unguarded 14`、`has_source_storage_root 14`、`_list_documents_unguarded 13`、`_get_primary_file_unguarded 13`、`get_source_by_filename 13`、`has_staged_filing_xbrl_instance 11`、…、`update_filing 2`、`restore_filing 2`、`_toggle_source_deleted 1`（`FileNotFoundError` 分支，`:1860`）、`_prepare_complete_source_meta 1`（`ingest_complete` 拒绝分支，`:1923`）。
  - 工具链前置实测：checkout 无 `.venv`；`python3.11` 存在（`/opt/homebrew/bin/python3.11`，3.11.15）；`constraints/lock-macos-arm64-py311.txt` 存在；`pyproject.toml` 的 `dayu-cli = "dayu.cli.__main__:exit_module"` 与 `dayu/cli/__main__.py:27 def exit_module` 存在；extras `test/dev/browser` 存在；根 `README.md:34-44` 的安装配方与计划一致。

## 一、结论

**pass-with-risks**（可按现文交给 implementation agent；建议按下述 2 个低严重度 findings 在实施前做小幅规格收紧，残余风险按登记去向跟踪）。

核心判定：首轮 review 的 fail 点已全部正确修复，总控 F1–F5 裁决在修订计划中逐项落实且与代码事实一致。`_toggle_source_deleted` 对已确认 tombstone 的重复 delete 跳过 meta 规范化/写入与 manifest upsert 整段，仍是唯一正确 owner 边界；状态表、业务字节与物理事件的界限、filing/material 共用 owner、auto 同内容恢复路径、A08 冻结证据的性质界定均经本次独立实读/实测核实成立。剩余问题不是结构性缺陷，而是两处规格缝隙：损坏 `is_deleted` 的 fail-closed 作用面未覆盖 restore 方向；fail-closed 新增的 `KeyError` 错误面与白名单冻结的仓储/协议 docstring 无法同时自洽。

## 二、预检与锁核对

| 项 | 期望 | 实测 | 结果 |
| --- | --- | --- | --- |
| 计划 SHA-256 | `fd7fef70…396` | `fd7fef7080f48a6b208d12d0ecfad10009157618f05cf854186ceaf539690396` | 一致 |
| HEAD 锁（goal 基线） | `8d8d494fbbce…` | `8d8d494fbbce0052372fb1b42097c9f7222cfa28` | 一致 |
| 工作区状态 | 仅 4 个既有 untracked 文档 | 仅 4 个既有 untracked 文档（本次只新增本 artifact） | 一致 |
| Canary | 预检 canary.txt | `mimo-1455ffb9` | 已逐字记录 |

## 三、假设清单（逐项证伪结果）

| # | 计划假设 | 证伪结果 | 直接证据 |
| --- | --- | --- | --- |
| A1 | 重复 delete 的时间/字节漂移源于 `_toggle_source_deleted` 每次无条件重写 | 成立 | `_fs_source_document_core.py:1862-1884`：`meta["is_deleted"]=deleted`、`deleted_at=now_iso8601() if deleted else None`、`updated_at=now_iso8601()`、`_prepare_complete_source_meta`（`:1923` 附近每次 `pop` revision 后写新 `uuid4`）、`_write_json` 与 manifest upsert，全部无条件执行 |
| A2 | manifest 顶层 `updated_at` 由 upsert 每次改写 | 成立 | `_fs_storage_infra.py:2711-2742`：`_upsert_manifest_items` 末尾 `manifest["updated_at"] = now_iso8601()` 后 `_write_json`；跳过 upsert 整段即保 manifest 字节 |
| A3 | 跳过写入整段即可保业务字节幂等；batch 只影响物理层 | 成立 | `begin_batch` 对已发布 tree `shutil.copytree`（`_fs_storage_infra.py:417-490`）；`commit_batch` 先 `_validate_complete_source_tree`（`:565`，只读）再 `_replace_directory` 目录交换（`:676-710`）；无其它 source meta/manifest writer 介入 delete 路径 |
| A4 | no-op 仍过常规 commit 完整校验，损坏状态不得被成功掩盖 | 成立 | 同上 `commit_batch` 对 staging 完整校验后才 swap；no-op 的 staging 与已发布内容一致时通过，manifest/source 损坏则 ValueError → `_rollback_precommit_batch` |
| A5 | auto 同内容恢复走真实 update 路径清 tombstone、保 ID/版本 | 成立 | `_can_skip_upload` 对 `require_source_meta_is_deleted` 为真直接不 skip（`docling_upload_service.py:1643-1644`）；`_build_upsert_meta` 置 `is_deleted=False`、`deleted_at=None`（`:329-330`）；`resolve_upload_action` 显式动作原样返回、不看先前状态（`:1895-1911`） |
| A6 | delete 不需要返回 handle，服务层投影 `status=deleted`、`stored_file_count=0` | 成立 | `_PreparedDeleteMutation`（`:447-453`）→ `publish_prepared_upload`（`:583-603`）→ `_delete_source_document`（`:858-888`）→ `delete_source_document -> None`（`fs_source_document_repository.py:390-421`） |
| A7 | filing/material 共用同一 source 转换 owner | 成立 | `delete_material/restore_material/delete_filing/restore_filing` 全部调用 `_toggle_source_deleted`（`_fs_source_document_core.py:205,235,311,341`）；仓储仅按 `SourceKind` 派发 |
| A8 | `is_deleted` 精确读取有唯一 owner helper | 成立 | `source_meta_contract.py:13-34`（缺 key→`KeyError`，非 bool→`ValueError`）；`dayu/fins/README.md:97,101` 统一读者与 fail-closed 合同 |
| A9 | 测试断言面可观察 | 成立 | `get_source_meta`（`fs_source_document_repository.py:524`）、`get_source_document_locator`（`:628`）、`get_source_handle`（`:778`）；`restore_source_document -> DocumentHandle`（`:492-522`）；既有 `_set_upload_clock`（`test_docling_upload_service.py:283`）与 `test_source_owner_material_update_delete_restore_replace_and_reset`（`test_fins_storage_atomicity.py:2180`）存在 |
| A10 | 覆盖率基线 473/97/79%，≥80 门槛经真实 owner 测试可达 | 成立（算术核实） | 独立复测与计划逐字一致；缺口含 `update_filing` 2 条、`restore_filing` 2 条（`:291-292`、`:340-341`）；即使修复新增 0 条语句，仅 filing create→update→delete→restore 链覆盖这两处即 `379/473 = 80.1%`，新增被测语句只会抬高比率；失败边界（`:1860`、`:1923`）构成同一 owner 的真实后备空间 |
| A11 | CLI 验证的工具链身份前提可建立 | 成立（可建立） | 无 `.venv`（实测 0 命中）；`python3.11` 可用；锁文件/extras/entry point/README 配方齐备；计划的身份断言链（editable `direct_url.json`、shebang、`dayu.__file__`、清 `PYTHONPATH`、隔离 cwd）覆盖首轮 F1 的全部错误取证路径 |
| A12 | 裁决与旧证据的性质界定一致 | 成立 | 计划 `:5`（冻结证据非本 checkout 运行结果）、`:11`（A08 由直接路径解释、不把 CLI 文案/mtime 当合同）、`:94`（A08 是 bug 证据不是预期）与裁决/goal 的“不把旧 A08 时间改写变为合同”一致 |

## 四、裁决 F1–F5 复核（本轮重点挑战结果）

- **F1（隔离 `.venv` 与 CLI 身份，高→已裁决）**：计划 `:52-60` 现在要求在本 checkout 用 Python 3.11 建独立 `.venv`、以平台锁 editable 安装本 checkout、每步真实 CLI 前重断言 HEAD/解释器/`dayu.__file__`/editable `direct_url.json`/console script shebang 与入口，且明文禁止借用主工作区 venv。与根 README 安装真源、pyproject entry point 逐项吻合；机器前置（`python3.11`、锁文件）实测满足。**修复成立，无遗留 blocker**；离线装不上时按计划停验证 gate（见残余风险 R7）。
- **F2（单文件覆盖率，中→已裁决）**：计划 `:48,73` 明记 473/97/79% 基线、逐文件 `--fail-under=80`、不达标只补同一 owner 有意义测试。本轮独立复测数字逐字复现；缺口归类与算术证明门槛可达（A10）。**修复成立**；薄边际的真实前提是“真实 `Fs*Repository` 状态链测试”不被 mock 化（见残余风险 R2）。
- **F3（损坏 `is_deleted` fail closed，中→已裁决）**：计划 `:27,31` 改用 `require_source_meta_is_deleted` 并 fail closed，与 `README.md:101` 读者合同同源，损坏测试断言无业务字节变更。方向正确；**但作用面规格留有 restore 方向的缝隙，见 finding 1**。
- **F4（delete 无 handle、重删不改时间，低→已裁决）**：计划 `:31,42` 现在只从 locator/source meta/manifest/原资产断言 delete，`DocumentHandle` 仅在 restore 返回值断言，并删除“首删两时间戳逐字相等/单次取时”的验收。与仓储签名（A6、A9）一致，验收断言面全部可观察。**修复成立**。
- **F5（fins README 白名单/合同，追加→已裁决）**：计划 `:44,86` 将 `dayu/fins/README.md` 列为允许且必需的第 4 项实施文档，仅在产品状态转换落地后按该 README 的 `Agent更新约束【必须遵守】`（实读 `:16-25`：只写已实现、先核对代码）同步修正 no-op/revision/损坏 fail-closed 契约；本轮不改 README 正文。与 README 更新约束的“不写未来计划”一致。**修复成立**。
- **no-op revision**：同周期重删保持 `_published_source_revision`、真实转换（首删/恢复/新周期）经 `_prepare_complete_source_meta` 翻新（`:1898-1932`，pop 后写新 `uuid4`），测试断言语义不固定 token——与裁决 Q3 一致，且与 `README.md:103` 现行“每次 delete/restore 均翻新”的表述需要由白名单第 4 项修正的计划吻合。
- **旧 source 事实（A07/A08/A09）**：计划仅将其作为动机与参数面参考，canary 全部在全新隔离目录重取证，明确不外推并发/不同内容恢复（`:75,82,94`）。无把 bug 证据合同化的痕迹。
- **O14/O15、O33 边界**：`:90-92` 把 target precondition、typed target-missing 拒绝、amended、并发 auto 分别留给 O14/O15、O18、O33，并设合流核对点；O13 只对已存在且确认 tombstone 的 source no-op。切分与 goal 边界一致，未见目标漂移。

## 五、Findings

### 1-未修复-[低]-损坏 `is_deleted` 的 fail-closed 作用面未覆盖 restore 方向，状态表与实现段落不一致
- **位置**: 「精确状态与返回值合同」状态表第 4 行（“`is_deleted` 缺失或非布尔值 | **delete**”）与实现段落（“在现有 `meta_path` 存在性检查及 `_read_json_object` 之后，先用 `require_source_meta_is_deleted(meta)` 取得精确布尔状态”）；对照裁决 F3 与 `dayu/fins/README.md:101`。
- **问题类型**: 契约缺失 / 语义所有权
- **当前写法**: 状态表把损坏 `is_deleted` 的 fail-closed 行限定在 delete 请求；实现段落的 helper 调用写在“读 meta 之后、no-op 判定之前”，读作无条件执行（delete 与 restore 共用 `_toggle_source_deleted`）。损坏测试（白名单第 2 项）也只在 delete 流程描述。
- **反例/失败场景**: 实施 agent 按状态表把 helper 调用收窄到 `deleted is True` 分支，则 restore+损坏 meta 保留现状“治愈”行为（`:1863-1865` 直接 `meta["is_deleted"]=False` 覆写损坏值并翻新 revision）——直接违反裁决 F3“先调用该 helper…不走覆写修复”在 restore 方向的语义，owner 内留下半套 fail-closed。反之按实现段落无条件调用，restore+损坏改为抛错 fail closed——这是状态表未列、测试未锁、goal 未显式确认的行为分叉；两种结局取决于 agent 读了哪一段，且现有测试两种都测不出。
- **为什么有问题**: `is_deleted` 是 README 明文治理的唯一语义字段，裁决 F3 的措辞（“`_toggle_source_deleted` 读取 meta 后先调用该 helper”）本身是无方向限定的；计划作为 code-generation-ready 合同必须把作用面写死，不能把行为分叉留给实施 agent 现场裁量。这与首轮 F3 是同一类“第二套读取习惯”风险的残留形态。
- **直接证据**: 计划 `:27`（损坏行“请求：delete”）与 `:31`（无条件 helper 读取）的交叉；裁决 F3 行“读取 meta 后先调用该 helper；缺失或非 bool fail closed…不走覆写修复”；`_fs_source_document_core.py:1862-1865`（现状 restore 直接覆写）；`README.md:101`（“统一通过 `require_source_meta_is_deleted(...)` 读取…均视为损坏并 fail closed”）。
- **影响**: 要么损坏值仍被 restore 静默治愈并伪造转换事实，要么产生未经裁决/未测试锁定的行为变更；两种情况都让 F3 的验收（“损坏值 owner 测试断言无 source/meta/manifest 业务更改”）只覆盖一半作用面。
- **建议改法和验证点**: 二选一写死并补测试：(i) 与裁决 F3 措辞对齐——helper 无条件读取，状态表补一行“`is_deleted` 缺失或非布尔值 | restore | 拒绝损坏 meta，fail closed，不覆写修复”，损坏测试参数化 delete/restore 两方向；(ii) 明确 helper 仅在 delete 请求调用，并写明 restore 保留覆写处置的理由及其与 README fail-closed 合同的差异（该差异需重新裁决）。同步把 `README.md:101` 读者清单（现列“storage snapshot 与上传 skip 判定”）是否扩列 toggle owner 写入白名单第 4 项的更新要点。验证点：restore+损坏 meta 的测试锁定选定行为；实现只存在一套 `is_deleted` 读取语义。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-[低]-fail-closed 新增 `KeyError` 错误面与白名单冻结的仓储/协议 docstring 无法同时自洽
- **位置**: 「实施切片与白名单」第 1 项（仅 `_fs_source_document_core.py` 一个产品文件）与“白名单外修改先回裁决”条款；对照 `fs_source_document_repository.py:390-421`、`repository_protocols.py:944-962` 的 Raises 契约。
- **问题类型**: 不可直接实施 / 契约缺失
- **当前写法**: 计划规定损坏 meta 经 helper 抛 `KeyError`（缺字段）/`ValueError`（非布尔）沿 batch rollback 路径 fail closed，公开 delete 签名不变。但 `delete_source_document` 的 docstring Raises 只承诺 `FileNotFoundError/ValueError/OSError`，`restore_source_document` 同样；这两个文件不在白名单内，而计划明文“白名单外修改属正确 owner 所必需，先回到 goal/plan 裁决”。
- **反例/失败场景**: 实施 agent 落地 fail-closed 后发现 `KeyError` 穿过公共仓储入口而其异常清单未列，二选一都被计划卡死：改仓储/协议 docstring → 触发计划外再裁决；不改 → 公共签名文档与真实错误面不符，违反编码硬约束“docstring 至少包含参数、返回值、异常”。另一种走法是在 core 层把 `KeyError` 翻译成 `ValueError`（core 现 docstring 恰承诺“source meta 不合法时抛出 ValueError”）——但这又与 helper 的 canonical 异常语义和计划 `:31`“字段缺失抛 `KeyError`”冲突，同样是计划未裁决的分叉。
- **为什么有问题**: 计划同时冻结了白名单和错误面语义，两者不能同时满足；这正是首轮 review 所指“迫使 implementation agent 现场即兴发明”的同类形态，只是从环境层移到了契约层。
- **直接证据**: `source_meta_contract.py:20-22`（缺 key→`KeyError`）；`fs_source_document_repository.py:412-416` 与 `repository_protocols.py:959-962`（Raises 三类，无 `KeyError`）；计划 `:39-41`（产品白名单仅一个文件）、`:46`（白名单外先回裁决）、`:31`（`KeyError` 直接抛出）。旁证：`docling_upload_service.py:406-407` 已把该 helper 的 `KeyError/ValueError` 写入既有公开异常文档，说明异常穿透在服务层是既有惯例。
- **影响**: 实施 gate 被计划自身的两条款夹住，被迫在“计划外改文件”与“签名文档失真/异常翻译分叉”之间选边；后续 O14/O15 做 typed 拒绝时会基于不一致的错误面建模。
- **建议改法和验证点**: 计划内显式收口三选一：(a) 白名单增列 `fs_source_document_repository.py`/`repository_protocols.py` 的 docstring Raises 同步（仅文档、无行为变更）；(b) 裁定 core 层将 helper 缺 key 统一投影为 `ValueError`（与 core 现有“source meta 不合法 → ValueError”承诺一致），并写明与 helper 原生 `KeyError` 的翻译理由；(c) 声明公开契约以 helper 原生异常为准，上述两文件 docstring 改动按既有“正确 owner 所必需”路径即时放行。验证点：任选其一后，`delete_source_document`/`restore_source_document` 的文档化异常集合与测试断言的异常类型一致。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 六、Open Questions

- **Q1**：`FilingManifestItem.from_source_meta`/`MaterialManifestItem.from_source_meta`（`document_models.py:1002,1081`）仍用 `meta.get("is_deleted") is True` 的 raw 读取投影 tombstone，而 README:101 的统一读者合同已存在。在 O13 fail-closed 落地后，所有会覆写 meta 的路径都先过 helper，该 loose 读在实践中接触不到损坏值（暴露面反而缩小），但读者语义仍有两套。是否随白名单第 4 项 README 更新把投影读者列入统一合同的后续收敛项（不扩本项白名单）？
- **Q2**：corrupt meta 的 `KeyError/ValueError` 在服务层 `fins_upload_failure_from_exception` 下的具体投影形态（failed upload 的 reason 文案/typed shape）goal 未要求锁定，O14/O15 的 typed 拒绝工作是否会把它一并建模？若会，本项只承诺 fail-closed 与字节不变即可，无需提前设计。

## 七、Residual Risks 与跟踪去向

- **R1**：重复 restore 非幂等（每次 restore 重写 meta/翻新 revision/刷新 manifest 时间）——goal 明确不覆盖，裁决已登记 follow-up `fins-source-restore-active-idempotency`。跟踪去向：该 follow-up / O14/O15 动作前置裁决。
- **R2**：覆盖率门槛的算术成立依赖“真实 `Fs*Repository` + batch 状态链测试”按计划落地（缺口归类显示 `update_filing`/`restore_filing` 尾部各 2 条是最低保证，`379/473≈80.1%` 为薄上沿）；若实施把测试 mock 化或跳过 filing 链，门会重新变红，届时按计划补同一 owner 失败边界测试（`:1860`、`:1923` 等）有真实空间但引入 gate 回环。跟踪去向：implementation review gate。
- **R3**：并发重复 delete/auto 未定义（O33）；canary 顺序执行不外推并发。跟踪去向：O33。
- **R4**：重复 delete 的 batch 仍 copytree + 目录交换，inode/mtime 变化；下游若以 mtime 做缓存失效会误判（当前无此类消费者证据）。跟踪去向：PR #197 合流 / O33。
- **R5**：O18 amended 投影与 no-op 分支的交互（合流时确认 O18 投影不被 O13 no-op 擦写）。跟踪去向：O18 / PR #197 合流。
- **R6**：CLI canary 两步落在同一时钟分辨率内导致新周期 `deleted_at` 相等——计划已有等待跨分辨率重跑 + owner 受控时钟兜底。跟踪去向：实施验证记录。
- **R7**：`pip install -e ".[test,dev,browser]" -c constraints/lock-macos-arm64-py311.txt` 需可达 PyPI；离线/锁文件拉包失败按计划停验证 gate，不借用主工作区 venv。跟踪去向：实施验证记录。
- **R8**：`from_source_meta` 的 raw `is_deleted` 读取与统一读者合同并存（见 Q1），本项不改。跟踪去向：fins 读者合同后续收敛（不阻塞 O13）。

## 八、最终结论

**pass-with-risks**。计划在 owner 边界、状态机、验证次序、证据身份、覆盖率门槛、README 决策与 O14/O15/O18/O33 切分上均已 code-generation-ready；首轮 fail 的三个实质缺陷与 F5 白名单阻断经裁决修复后经本轮独立实测/实读确认成立。建议实施前用 finding 1、finding 2 的改法各收紧一处规格（改动仅限计划文本），并按第七节去向跟踪残余风险；如总控认为两处低严重度缝隙可留给实施 review 兜底，亦可直接放行实施。

## 九、非目标遵守声明

本次 review 未修改 plan、goal、裁决、产品代码、测试、README 或任何其它 artifact；未实施 O13/O14/O15/O33；未安装依赖；未向外发送消息；未 commit/push/PR/merge；未派发子 Agent；未使用 `ps`/`pgrep` 判活。测试与覆盖率测量为只读验证，数据写入 `$TMPDIR`。唯一写入为本 review artifact：`/private/tmp/dayu-upload-o13/docs/reviews/plan-review-o13-rereview2-mimo-20260929.md`。
