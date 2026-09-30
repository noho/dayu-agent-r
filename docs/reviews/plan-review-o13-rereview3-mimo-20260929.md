# Plan Review（三轮独立复审 rereview3）：UM-O13-F01 重复 delete tombstone 幂等实施计划

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-3182bdce

- Review 类型：`$planreview` adversarial plan review（独立反例核查，不实施、不改 plan）。本 artifact 文件名按任务指定的 gateflow 命名 `plan-review-o13-rereview3-mimo-20260929.md`。
- Review target：`docs/gateflow/upload-material-o13-tombstone-plan-20260929.md`（Sol PR2 计划修订候选）。
- Target SHA-256：`5b02d9e62362a2dd88006a25dffab76803983bfcb2cb488aa5bea34add7c5d58`（实测 `shasum -a 256` 与任务锁定值逐字一致，预检通过）。
- 输入核验：`AGENTS.md` 实测 SHA-256 `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e`；goal `docs/gateflow/upload-material-o13-tombstone-goal-20260929.md` 实测 `32b754b501b5fb4610852a92005650fd813562634fc496cb767041955bc9bf30`；锁定哈希绑定对象为计划文件本身（唯一与 `5b02d9e6…` 一致的文件）。
- Binding scope contract：`docs/gateflow/upload-material-o13-tombstone-goal-20260929.md`（goal confirmation；基线 HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`）。
- 裁决真源：`docs/gateflow/upload-material-o13-plan-review-adjudication-20260929.md`（MiMo F1–F5 + PR2-F1/F2 裁决、Sol PR2 修订核验）。
- 前序 review：`docs/reviews/plan-review-20260929-043830.md`（MiMo 首轮，fail）、`docs/reviews/plan-review-o13-rereview2-mimo-20260929.md`（MiMo 二轮，pass-with-risks，2 条低 finding）。
- Sol PR2 修复记录：`docs/gateflow/upload-material-o13-plan-fix-pr2-20260929.md`（输入 SHA `fd7fef70…` → 输出 SHA `5b02d9e6…`）。
- 冻结证据真源：主工作区只读 `/Users/leo/workspace/dayu-agent-r/docs/reviews/upload-material-um-o13-oracle-adjudication.md`（已实读：A07 首删、A08 缺陷、A09 同内容 auto 恢复、UM-O13-F01 授权）。
- 证据基线：本 checkout `/private/tmp/dayu-upload-o13`，分支 `codex/upload-material-o13`，HEAD 实测 `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，与 goal 基线锁一致；`git status` 仅 6 个 untracked O13 文档，产品/测试/README 未动。本机时钟 2026-09-29 12:42:26 +0800。
- 本轮为只读复审：未安装依赖、未运行测试/coverage/pyright、未派发子 Agent、未使用 `ps`/`pgrep`、未改任何既有文件；唯一写入为本 artifact。

## 一、结论

**pass-with-risks**（PR2-F1/F2 修复经直接代码证据确认成立，计划可按现文交给 implementation agent；余下 2 条低严重度 docstring 规格缝隙建议实施前小幅收紧，或由总控明示留给实施 review 兜底）。

核心判定：rereview2 的两条 finding 在修订计划中已按裁决要求收口，且与真实 owner 代码逐项吻合——delete 与 restore 在任何赋值/no-op 判定前无条件调用 canonical `require_source_meta_is_deleted`，损坏 meta 双向 fail closed（缺字段 `KeyError`、非布尔 `ValueError`），不以覆写治愈；仓储/协议两文件以 doc-only Raises 同步进入白名单。旧 F1–F5、no-op revision 语义、真实仓储测试/单文件覆盖率门、O14/O15/O18/O33 边界全部保留且本轮未发现漂移。剩余问题集中在 PR2-F2 的 docstring 同步规格本身：(1) 服务层 delete 发布边界的公开 Raises 未列入白名单，实施期会重现“白名单外修改先回裁决”的夹层；(2) 第 5/6 项“缺失 `is_deleted` 的 `KeyError`”措辞会固化不完整异常契约。两者均为文档契约层低危缝隙，不动摇 owner 边界与状态机设计。

## 二、预检与锁核对

| 项 | 期望 | 实测 | 结果 |
| --- | --- | --- | --- |
| 计划 SHA-256 | `5b02d9e6…d58` | `5b02d9e62362a2dd88006a25dffab76803983bfcb2cb488aa5bea34add7c5d58` | 一致，停止条件未触发 |
| HEAD 锁（goal 基线） | `8d8d494fbbce…` | `8d8d494fbbce0052372fb1b42097c9f7222cfa28` | 一致 |
| 工作区状态 | 仅既有 untracked O13 文档 | 6 个 untracked docs，无产品/测试/README 改动 | 一致 |
| Canary | 预检 canary.txt | `mimo-3182bdce` | 已逐字记录 |
| 冻结证据可读 | oracle adjudication | `/Users/leo/workspace/dayu-agent-r/docs/reviews/upload-material-um-o13-oracle-adjudication.md` 实读成功 | 一致 |

## 三、PR2-F1/F2 修复复核（本轮重点）

### PR2-F1（损坏 `is_deleted` 双向 fail closed）——修复成立

- 状态表新增第 5 行（`is_deleted` 缺失/非布尔 × restore → 经 helper 拒绝，不以 `False` 覆写修复），与第 4 行 delete 行对称（计划 `:27-28`）。
- 实现段落（计划 `:32`）明确“**delete 与 restore 均无条件先用** `require_source_meta_is_deleted(meta)` 取得精确布尔状态，校验成功后才允许对 meta 赋值或判断 no-op”，并固定次序：`meta_path` 存在性检查（`FileNotFoundError` 保留，归 O14/O15）→ `_read_json_object` → helper（缺字段 `KeyError` / 非布尔 `ValueError` 透传）→ 才允许赋值或 no-op。rereview2 指出的行为分叉（按状态表收窄 vs 按实现段落无条件）已消除，两段一致。
- 与真源吻合：`source_meta_contract.py:13-32` 的 helper 对缺 key 抛 `KeyError`、非 bool 抛 `ValueError`；`dayu/fins/README.md`（storage 段）现行合同“字段缺失或非布尔值均视为损坏并 fail closed，不使用默认值或 loose truthiness”；`_fs_source_document_core.py:1862-1865` 现状 restore/delete 直接 `meta["is_deleted"] = deleted` 覆写，正是要消灭的行为。
- 测试规格覆盖两方向（计划 `:43`）：staging meta `is_deleted` 缺失/非布尔 × delete/restore 参数化，断言真实异常类型、调用前后 staging 业务字节不变、rollback 后已发布业务字节与 revision 不变。可执行性已核实：`tests/fins/test_fins_storage_atomicity.py` 已有直接写 meta 文件与 `repository_set.core._source_meta_path(..., state)` / `state.staging_ticker_dir` 观察 staging 的先例（`:1676-1696`、`:1898-1939`）；`rollback_batch` 对 `BaseException` 一律回滚（`docling_upload_service.py:1393-1434`、`_fs_storage_infra.py:1379`），`KeyError` 与 `ValueError` 同路径 fail closed，“沿既有 batch rollback 路径”的断言有据。
- 无消费方破坏：`restore_source_document`/`restore_material`/`restore_filing` 在 `dayu/` 内无生产调用方（实测 0 命中，auto 恢复走 update 路径），fail-closed 只拒绝真实损坏态；owner 创建的 meta 经 `_upsert_source_document` 的 `setdefault("is_deleted", False)`（`:1775`）保证字段存在，正常文档不受影响。
- README 白名单第 4 项要求“核对现有严格读者描述是否应列入 toggle owner”（现行 README 读者清单只列 storage snapshot 与上传 skip 判定），与 rereview2 建议一致。
- **无遗留 blocker。**

### PR2-F2（仓储/协议公开 Raises docstring 仅文档白名单）——方向成立，收口不完整（见 finding 1、2）

- 白名单增列第 5、6 项（`fs_source_document_repository.py`、`repository_protocols.py`），仅同步 `delete_source_document`/`restore_source_document` 的 Raises docstring，明确“不修改签名、派发或异常处理”“不为迁就旧文档翻译 core 异常”，与裁决“生产行为仍只在 `_fs_source_document_core.py` owner”一致。
- 缺口事实核实：`fs_source_document_repository.py:405-408`（delete）与 `:507-510`（restore）、`repository_protocols.py:959-962` 与 `:1037-1040` 的 Raises 均只列 `FileNotFoundError/ValueError/OSError`，确无 `KeyError`——计划所指缺口属实。
- 覆盖率影响不受污染：docstring 修改不增加可执行语句，单文件 `--fail-under=80` 门仍只对 core（计划 `:76` 表述准确）。
- 但同步范围与措辞两处留有低规格缝隙，见 findings。

## 四、旧 F1–F5 与边界复核（本轮抽查结果）

- **F1（venv/CLI 身份，高）**：计划 `:55-63` 保留独立 Python 3.11 venv、锁文件 editable 安装本 checkout、每步真实 CLI 前重断言 HEAD/`sys.executable`/`dayu.__file__`/`direct_url.json`/console script shebang 与入口 `dayu.cli.__main__:exit_module`、禁借主工作区 venv。保留完好。
- **F2（单文件覆盖率，中）**：计划 `:51,76` 保留 473 statements / 97 misses / 79% 基线、逐文件 `--fail-under=80`、不达标只补同一 owner 有意义用例、不降低门槛。rereview2 已独立复测该基线且算术可达（`379/473≈80.1%` 薄上沿）；本轮核实产品代码自基线 HEAD 未改动，基线仍有效。保留完好。
- **F3（canonical reader）**：已由 PR2-F1 全面落实并扩展至双向。保留完好。
- **F4（delete 无 handle/时间合同）**：计划 `:32-34` 保留“公开 delete 仍返回 `None`、`DocumentHandle` 只在 restore 返回值断言、首删两时间戳逐字相等非验收、同周期重删不取新时间”。与 `delete_source_document -> None`（`:390-395`）签名一致。保留完好。
- **F5（fins README 白名单）**：白名单第 4 项保留“允许且必需、实现后按 README 更新约束同步、不提前写入”。保留完好。
- **no-op revision**：同周期重删跳过 `_prepare_complete_source_meta`（`:1898-1932` pop 后写新 `uuid4`，仅真实转换调用）保持原 revision；首删/恢复/新周期各自翻新、不固定 token——与裁决 Q3 一致，且计划 README 修正项覆盖现行 README“每次 delete/restore 均翻新”的表述更新。
- **O14/O15/O18/O33 边界**：计划 `:93-95` 逐项保留（target precondition/typed 拒绝归 O14/O15；amended 事实独立、合流核对 no-op 不擦写 O18 投影；并发 auto/identity 归 O33，只声明顺序语义）。与 goal 边界一致，无目标漂移。
- **状态机闭环**：状态表 7 行覆盖不存在/首删/同周期重删/损坏×delete/损坏×restore/恢复/新周期，与 goal 成功信号 1–3 一一映射；no-op 仍过 commit 完整校验、损坏不得被成功掩盖，附“直接测试证伪则停止实施并重新裁决”停止条件。未发现反例。
- **测试可执行性**：五文件测试集与锚点实测存在（`test_source_owner_material_update_delete_restore_replace_and_reset` `:2180`、`_set_upload_clock` `:283`、`test_upload_filing_auto_after_delete_republishes_active_source` `:1598`）；计划引用的行号（core `:1862-1884`、service `:447-453,583-603,858-888`、infra manifest upsert 末尾、batch `:417-488,533-565,676-710`）与实读一致。

## 五、Findings

### 1-未修复-[低]-PR2-F2 的 doc-only 白名单未覆盖服务层 delete 发布边界的公开 Raises，实施期将重现“白名单外修改先回裁决”夹层
- **位置**: 「实施切片与白名单」第 5、6 项与“白名单外修改先回裁决”条款（计划 `:46-47,49`）；对照 `docling_upload_service.py:559-603`（`publish_prepared_upload`）、`:858-889`（`_delete_source_document`）。
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: 计划把 docstring 同步范围收口为“两个仅限 Raises docstring 的公开契约文件”（storage 仓储+协议），服务层文件不在白名单，且明文要求白名单外修改先回 goal/plan 裁决。
- **反例/失败场景**: 服务层 `prepare_upload` 的 delete 分支（`:447-453`）直接返回 `_PreparedDeleteMutation`，完全不读 `is_deleted`——fail-closed 后 `KeyError/ValueError` 的**首个公开暴露点**是 `publish_prepared_upload` 的 delete 分支（`:585-591`）经 `_delete_source_document` 冒出。该方法 Raises（`:576-580`）只列 `FinsUploadFailureError/OSError/ValueError/RuntimeError`，无 `KeyError`（连既有 delete 缺文档的 `FileNotFoundError` 也未列，`:877-879` 仅列两类）。实施 agent 二选一都被计划夹住：同步该 docstring → 白名单外修改、须回裁决、gate 回环；不同步 → 公开方法异常文档与真实错误面不符，违反编码硬约束“docstring 至少包含参数、返回值、异常”，implementation review/deepreview 将按 PR2-F2 同一标准再次抓出文档漂移。注意 `prepare_upload:406-407` 的 KeyError 文档只覆盖 prepare 阶段读取（`_can_skip_upload` 路径），**不覆盖** delete 发布路径。
- **为什么有问题**: PR2-F2 的裁决动机是“fail-closed 新增错误面必须与公开文档自洽”，同一动机在服务层公开边界同样成立；计划以“仅”字宣称 doc-only 白名单已完整，实际缺一层，属于 rereview2 finding 2 的同类夹层未被彻底关闭。
- **直接证据**: `docling_upload_service.py:447-453`（delete 分支无 meta 读取）、`:576-580`（Raises 无 KeyError）、`:858-889`（`_delete_source_document` 直连 `delete_source_document`，Raises 仅 FileNotFoundError/OSError）、`:406-407`（KeyError 文档仅在 prepare）；计划 `:40`（“两个仅限 Raises docstring 的公开契约文件”）、`:49`（白名单外先回裁决）。
- **影响**: 实施 gate 回环（再裁决一次）或公共契约文档失真进入 review/deepreview；O14/O15 建 typed 拒绝时可能基于不完整错误面建模。
- **建议改法和验证点**: 二选一写死：(a) 白名单增列 `docling_upload_service.py` 的 `publish_prepared_upload` 与 `_delete_source_document` 两处 **仅 Raises docstring**（无行为变更，连同补齐既有 `FileNotFoundError` 遗漏）；(b) 计划明文把服务层 Raises 完整性登记为既有残债并给跟踪去向，声明本项只同步 storage 契约、实施 review 不得把服务层 docstring 当白名单违约。验证点：delete+损坏 meta 的服务路径上，各公开边界（仓储/协议/service）的文档化异常集合与测试断言的 `KeyError/ValueError` 一致，无一处需白名单外改动。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-[低]-白名单第 5/6 项“列明缺失 `is_deleted` 的 `KeyError`”措辞会固化不完整异常契约
- **位置**: 「实施切片与白名单」第 5、6 项（计划 `:46-47`）；对照 `_fs_source_document_core.py:1916-1918`、`document_models.py:152-176`。
- **问题类型**: 契约缺失
- **当前写法**: 第 5 项要求仓储 docstring“列明缺失 `is_deleted` 的 `KeyError` 与非布尔值的 `ValueError`”，第 6 项同。
- **反例/失败场景**: `KeyError` 的触发面不止 `is_deleted`：`_toggle_source_deleted` 的真实转换路径经 `_prepare_complete_source_meta` → `SourceDocumentProvenance.from_meta`（`document_models.py:172-176` 用 `meta["ingest_method"]`/`meta["source_provider"]` 下标）对**缺失 provenance 字段**同样抛 `KeyError`，该异常今天就沿 `delete_source_document`/`restore_source_document` 传播（core `_prepare_complete_source_meta` docstring `:1917` 已承诺）。实施 agent 按字面只写“KeyError: source meta 缺少 is_deleted 时抛出”，则同步后的 Raises 对同一异常类型的既有触发原因仍然漏列——PR2-F2“文档与真实错误面自洽”只完成一半，下一个 reviewer 按完整契约标准仍会开同类 finding。
- **为什么有问题**: Raises 是异常**类型**契约；同一类型多个触发原因只列新因不列旧因，文档依旧失真。项目编码硬约束要求 docstring 异常完整。
- **直接证据**: 计划 `:46`（“列明缺失 `is_deleted` 的 `KeyError`”）；`_fs_source_document_core.py:1916-1918`（“KeyError: meta 缺少必需 provenance 字段时抛出”）；`document_models.py:168,172-176`（缺溯源字段 `KeyError`）；二者与 helper 的 `KeyError` 同类型、同传播路径。
- **影响**: doc-only 同步完成后公开契约仍不完整；实施 review 二次返工或被迫再裁决。
- **建议改法和验证点**: 第 5/6 项措辞改为“列明 `KeyError`（source meta 缺少必需字段，含 `is_deleted` 与 provenance 字段）与 `ValueError`（`is_deleted` 非布尔值等 meta 值非法）”，或改为“按 core 实际 Raises 全集同步”。验证点：仓储/协议 docstring 的文档化异常集合 ⊇ 测试断言异常 ∪ 既有可冒出类型（`KeyError`/`ValueError`/`FileNotFoundError`/`OSError`）。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 六、Open Questions

- **Q1（沿登记）**：`document_models.py:1002,1081` 的 `from_source_meta` 仍用 `meta.get("is_deleted") is True` raw 读取投影 tombstone，与唯一 reader 并存（本轮实读确认未变）。已由总控登记独立 follow-up `fins-source-meta-is-deleted-reader-contract`，O13 不扩；白名单第 4 项 README 更新时核对读者清单即可。
- **Q2（沿登记）**：corrupt meta 的 `KeyError/ValueError` 经 `fins_upload_failure_from_exception`（`upload_failure.py:214`）的 public failure 投影形态未锁定，归 O14/O15 typed 拒绝建模；O13 只承诺 fail-closed 与字节不变。
- **Q3（本轮新增）**：`publish_prepared_upload` docstring 的既有 `FileNotFoundError` 遗漏（delete 缺文档路径今天已可冒出）说明该处异常文档属存量欠账；finding 1 的修法 (b) 若被采纳，需明确该欠账的跟踪去向（建议随 O14/O15 typed 目标前置一并整饬服务层错误面文档）。

## 七、Residual Risks 与跟踪去向

- **R1**：重复 restore-on-active 非幂等（每次重写 meta/翻新 revision/刷 manifest 时间）——goal 明确不覆盖，登记 `fins-source-restore-active-idempotency`。跟踪去向：该 follow-up / O14/O15 动作前置。
- **R2**：覆盖率 ≥80% 为薄上沿（`379/473≈80.1%`），依赖真实 `Fs*Repository`+batch 状态链测试落地且不被 mock 化；fail-closed 新增语句会被新测试覆盖，分母同幅增长。跟踪去向：implementation review gate。
- **R3**：并发重复 delete/auto 未定义（O33）；canary 顺序执行不外推并发。跟踪去向：O33。
- **R4**：重复 delete 的 batch 仍 copytree+目录交换，inode/mtime 变化；下游若以 mtime 做缓存失效会误判（当前无此类消费者证据）。跟踪去向：PR #197 合流 / O33。
- **R5**：O18 amended 投影与 no-op 分支交互；合流时确认 O18 投影不被 O13 no-op 擦写。跟踪去向：O18 / PR #197 合流。
- **R6**：CLI canary 两步落在同一时钟分辨率内导致新周期 `deleted_at` 相等——计划已有等待跨分辨率重跑 + owner 受控时钟兜底。跟踪去向：实施验证记录。
- **R7**：`pip install -e ".[test,dev,browser]" -c constraints/lock-macos-arm64-py311.txt` 需可达 PyPI；失败按计划停验证 gate。跟踪去向：实施验证记录。
- **R8**：`from_source_meta` raw 读取与统一读者合同并存（Q1）。跟踪去向：`fins-source-meta-is-deleted-reader-contract`。
- **R9（本轮新增）**：同周期 no-op 跳过 `_prepare_complete_source_meta` 后，meta 中 provenance 等非 `is_deleted` 字段的重校验窗口收窄（现状每次 delete 都会重校验）；计划已用“no-op 仍须通过常规 batch commit 的完整 source/manifest 校验；损坏状态不得被成功掩盖”及停止条件兜底（commit validator 拒绝缺失/非法 provenance，README 有据），但该兜底是 commit 层而非 owner 层。跟踪去向：实施期 no-op 测试若证伪业务字节与成功返回不能同时维持，按计划停止并重新裁决。

## 八、最终结论

**pass-with-risks**。PR2-F1 双向 fail closed 与 PR2-F2 doc-only 白名单的修复方向经直接代码证据确认成立，旧 F1–F5、no-op revision、真实仓储测试/单文件覆盖率门、O14/O15/O18/O33 边界无漂移；未发现语义 owner 漂移或不可执行的状态机/切片设计。建议实施前按 finding 1、2 各做一处计划文本收紧（改动仅限计划措辞或白名单条目），或由总控明示该两处留给实施 review 兜底；残余风险按第七节去向跟踪。

## 九、非目标遵守声明

本次 review 未修改 plan、goal、裁决、产品代码、测试、README 或任何其它 artifact；未实施 O13/O14/O15/O33；未安装依赖；未向外发送消息；未 commit/push/PR/merge；未派发子 Agent；未使用 `ps`/`pgrep` 判活。唯一写入为本 review artifact：`/private/tmp/dayu-upload-o13/docs/reviews/plan-review-o13-rereview3-mimo-20260929.md`。
