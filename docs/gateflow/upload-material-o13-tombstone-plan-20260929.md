# UM-O13-F01：重复 delete tombstone 幂等实施计划

- Gate：`plan review -> fix` 后的修订候选；依据 `docs/gateflow/upload-material-o13-tombstone-goal-20260929.md` 的已确认目标，以及 `docs/gateflow/upload-material-o13-plan-review-adjudication-20260929.md` 对 MiMo F1–F5、O13-PR2-F1/F2 的裁决。只修订计划，未实施；修订后仍待 Kimi/MiMo 有效双路复审。
- 工作区：`/private/tmp/dayu-upload-o13`；分支：`codex/upload-material-o13`；读取时已有未跟踪 goal 文档，不属于本计划的改动。
- 裁决来源：主工作区只读 `/Users/leo/workspace/dayu-agent-r/docs/reviews/upload-material-um-o13-oracle-adjudication.md`。其中 A07 是首次删除证据，A08 是缺陷证据，A09 只证明同内容 auto 恢复。冻结证据不是当前 checkout 的运行结果。

## 目标、动机、成功信号

已存在 active source 首次删除时，仓储将 `is_deleted` 置真，记录本次转换的 `deleted_at` 并更新 `updated_at`，由同一份 source meta 更新对应 manifest；保留 document ID、内容版本与原资产。已删除 source 在同一 tombstone 周期再次 delete，仍可得到成功的已删除结果，但 `deleted_at`、`updated_at`、仓储 revision、source meta 原始字节、对应 manifest 原始字节及原资产字节不变。恢复清除 tombstone；随后再次删除是新周期，产生新的 `deleted_at`。Material 与 filing 共享相同 source-document 转换语义。

动机成立，严重性限于持久 source 状态：`dayu/fins/storage/_fs_source_document_core.py:1862-1884` 目前每次 delete 均重写 `deleted_at`/`updated_at`，调用 `_prepare_complete_source_meta` 产生新 `_published_source_revision`，再写 meta 与 manifest；`dayu/fins/storage/_fs_storage_infra.py:2738-2742` 的 manifest upsert 另写顶层 `updated_at`。A08 的两处时间与文件字节变化由这条直接路径解释。这里不把 CLI 固定文案、mtime 或 inode 当业务合同。

## 语义 owner 与直接调用链

1. `dayu/fins/storage/_fs_source_document_core.py:_toggle_source_deleted` 是 source `is_deleted/deleted_at/updated_at` 转换和持久化的唯一修改点。`delete_material`、`delete_filing` 都调用它，恢复方法也调用它；`dayu/fins/storage/fs_source_document_repository.py` 仅按 `SourceKind` 派发。`DocumentHandle` 的字段由该方法读取的同一份 meta 生成，不由 CLI 或 manifest 反推。
2. `dayu/fins/domain/document_models.py` 中 `FilingManifestItem.from_source_meta` 与 `MaterialManifestItem.from_source_meta` 从 source meta 投影 tombstone；`_fs_storage_infra.py:_upsert_manifest_items` 会改 manifest 时间并落盘。因此重删应在 `_toggle_source_deleted` 跳过 **meta 规范化/写入及 manifest upsert 整段**，不能只保留 `deleted_at` 后继续调用 writer。
3. `dayu/fins/pipelines/docling_upload_service.py:447-453,583-603,858-888` 的 delete plan 调用公共 `delete_source_document` 后生成 `status="deleted"`、`stored_file_count=0`；它不需要 delete 返回 handle。filing/material workflow 和 CLI 继续消费这一结果，不能各自重判 tombstone 时间。
4. `dayu/fins/storage/_fs_storage_infra.py:417-488,533-565,676-710` 的 batch 把已发布 ticker tree 拷入 staging，commit 校验后目录交换。即使 source owner 跳过写入，重复 delete 的 batch 仍可能更换物理目录、inode 与 mtime；**本合同是 source meta、manifest、资产内容的业务字节幂等，不承诺物理文件系统事件为零**。`_validate_complete_source_tree` 只读核验两种 source 的 canonical meta/manifest；它不要求对相同状态再次写入。

## 精确状态与返回值合同

| 仓储入口状态 | 请求 | owner 动作 | 结果与必须保持的事实 |
| --- | --- | --- | --- |
| 文档不存在 | delete | 保留现有 `FileNotFoundError` | 不在本项改变 target-missing 的 public/typed 投影，归 O14/O15。 |
| `is_deleted is False` | delete | 在同一 staging meta 中写 `True`，记录本周期 `deleted_at` 并更新 `updated_at`，规范化完整 source meta 并 upsert 对应 manifest | 已删除成功；版本、文件、身份不变；meta/manifest 同源；revision 随真实转换翻新；不要求首次删除两个时间戳逐字相等或只调用一次时钟。 |
| `is_deleted is True` | delete | 只读取现有 staging meta；跳过所有业务写入与 `_prepare_complete_source_meta` | 已删除成功；当前周期 `deleted_at`、`updated_at`、revision、meta/manifest/资产字节完全相同；不生成新的 tombstone 事实。 |
| `is_deleted` 缺失或非布尔值 | delete | 经 `require_source_meta_is_deleted(...)` 拒绝损坏 meta；不进入 no-op 或真实转换写入 | fail closed；不新造 tombstone 时间，不改 source meta/manifest/资产业务字节。 |
| `is_deleted` 缺失或非布尔值 | restore | 同样先经 `require_source_meta_is_deleted(...)` 拒绝损坏 meta；不以 `False` 覆写修复 | fail closed；不清除或新造 tombstone 事实，不改 source meta/manifest/资产业务字节。 |
| `is_deleted is True` | restore 或已测同内容 auto | 保留现有真实恢复路径 | `is_deleted=False`、`deleted_at=None`，active 状态与 manifest 一致；revision 随真实转换翻新；同内容 auto 保持原 ID 和内容版本。 |
| 恢复后 `is_deleted is False` | delete | 再走 active→deleted | 新 `deleted_at`，revision 再次翻新，版本与资产仍不变。 |

实现时在现有 `meta_path` 存在性检查及 `_read_json_object` 之后，**delete 与 restore 均无条件先用** `dayu.fins.storage.source_meta_contract.require_source_meta_is_deleted(meta)` 取得精确布尔状态，校验成功后才允许对 meta 赋值或判断 no-op；字段缺失透传 `KeyError`，非布尔值透传 `ValueError`，沿既有 batch rollback 路径 fail closed，不将损坏值覆写为正常 tombstone 或 active 状态。仅当请求 `deleted is True` 且读得当前状态为 `True` 时走 no-op。该 helper 与 `dayu/fins/README.md` 的统一读者合同同源，不增设 raw-field 判定。将现有内部 `DocumentHandle(...)` 构造留在共同尾部，供 restore 返回值使用；公开 delete 仍返回 `None`，测试从仓储 locator、source meta 和 manifest 观察其效果。不要返回空 handle、复制另一套解析、改变公共签名或加入兼容 facade；不为迁就旧 Raises 文档把 core 的 `KeyError` 改写成 `ValueError`。

首次删除记录本周期 `deleted_at` 并更新 `updated_at`；恢复维持 `deleted_at=None` 且更新 `updated_at`；新周期再次取得新的 `deleted_at`。首次删除两字段逐字相等及单次取时均非验收合同，现有两次取时实现可保持。`_prepare_complete_source_meta` 仅在真实转换时调用：首删、恢复、新周期删除各自翻新 opaque revision，同周期重删保持原 revision，不固定 UUID 或其格式。现有 canonical manifest 投影不变。no-op 仍须通过常规 batch commit 的完整 source/manifest 校验；损坏状态不得被成功掩盖。若直接测试证明正常 tombstone 的同周期 no-op 无法同时维持这些业务字节与现有成功返回，停止实施并重新裁决 source owner 与 batch 的合同；不得在 CLI、workflow 或 manifest writer 增加补偿。

## 实施切片与白名单

仅一片 `O13-S1`：完成可观察的首删→重删→恢复→再删闭环。按共享 source owner 与真实仓储状态转换组织测试，并覆盖同一 owner 中未覆盖的 filing update/restore 路径；不按模块机械拆片，不修改 schema、公有接口、CLI 文案、LLM-facing 文本或其它业务层。

实施文件白名单（一个行为修改文件、两个测试文件、一份必需 README、三个仅限指定方法 Raises docstring 的契约文件）：

1. `dayu/fins/storage/_fs_source_document_core.py`：在 delete 与 restore 共用 `_toggle_source_deleted` owner 中先接入 canonical `is_deleted` reader、仅对确认的 tombstone 重删跳过写入，保持真实转换与内部 handle 构造的共同路径，补齐中文 docstring/必要注释。同步 `_toggle_source_deleted` 及同文件四个直调入口 `delete_material`、`restore_material`、`delete_filing`、`restore_filing` 的 Raises docstring：`KeyError` 覆盖 source meta 缺少必需字段（含 `is_deleted` 与 provenance 字段），`ValueError` 覆盖 `is_deleted` 非布尔值及其它非法值；保留各入口既有 `FileNotFoundError`/`OSError` 及其它已列异常。不为配合旧文档翻译异常，不改四入口行为或签名。
2. `tests/fins/test_fins_storage_atomicity.py`：新增参数化 filing/material 真实 `Fs*Repository` 与 batch 的 owner 状态链测试，覆盖首删→重删→直接恢复→再删；使用步骤间可区分的受控时间，断言首次 tombstone、重删两时戳及 revision/业务字节不变、恢复清除 tombstone、新周期时间不同；断言首删/恢复/新周期 revision 各自翻新而不固定 token 值。delete 从 locator、source meta、manifest 和原资产断言，`DocumentHandle` 字段只在 restore 返回值断言。另覆盖 filing create→update→delete→restore 的真实状态转换及版本/manifest 一致性，使当前未覆盖的 filing update/restore 路径获得有意义的 owner 级断言；现有 `test_source_owner_material_update_delete_restore_replace_and_reset` 保持其语义。对 staging meta 的 `is_deleted` 缺失/非布尔值 × delete/restore 两方向，以真实仓储与 batch 参数化损坏测试：分别断言缺失透传 `KeyError`、非布尔透传 `ValueError`，调用前后 staging source meta/manifest/资产原始字节不变，rollback 后已发布 source meta/manifest/资产原始字节与 revision 不变；不以 fake 或损坏数据自动修复为预期。
3. `tests/fins/test_docling_upload_service.py`：在真实仓储的 `_execute_upload` 测试路径，参数化 material/filing，执行 create→delete→delete→同内容 auto 对应 update→delete；断言两次 delete 的 `status=deleted`、零 stored files、两时戳/revision/source/manifest 字节相同，auto 恢复原 ID/版本并清 tombstone、revision 翻新，末次 delete 产生新周期时间及新 revision。复用已有 fake converter 仅模拟外部转换，不以 fake 仓储决定状态。
4. `dayu/fins/README.md`：允许且必需的实施文档。仅在产品状态转换实现后，先核对已实现代码，再按该 README 的 `Agent更新约束【必须遵守】`，同步修正 storage 状态/公共契约：同周期重复 delete 是 tombstone no-op，`deleted_at`、`updated_at` 和 published revision 不变；首删、恢复及新周期删除等真实状态转换才翻新 revision；缺失或非布尔 `is_deleted` 在 delete/restore 均经 canonical reader 失败关闭，不被覆写修复；核对现有严格读者描述是否应列入 toggle owner。不提前写入未实现的行为或实施过程记录。
5. `dayu/fins/storage/fs_source_document_repository.py`：**仅**同步 `delete_source_document` 与 `restore_source_document` 的 Raises docstring：`KeyError` 覆盖 source meta 缺少必需字段（含 `is_deleted` 与 provenance 字段），`ValueError` 覆盖 `is_deleted` 非布尔值及其它非法值；保留既有 `FileNotFoundError`/`OSError`。不修改签名、派发或异常处理。
6. `dayu/fins/storage/repository_protocols.py`：**仅**同步同名 delete/restore 方法的 Raises docstring：`KeyError` 覆盖 source meta 缺少必需字段（含 `is_deleted` 与 provenance 字段），`ValueError` 覆盖 `is_deleted` 非布尔值及其它非法值；保留既有 `FileNotFoundError`/`OSError`。不修改协议签名或运行行为。
7. `dayu/fins/pipelines/docling_upload_service.py`：**仅**同步 `publish_prepared_upload` 与 `_delete_source_document` 两处 Raises docstring，写明可公开冒出的 `KeyError`（source meta 缺少必需字段，含 `is_deleted` 与 provenance 字段）和 `ValueError`（`is_deleted` 非布尔值及其它非法值）；`publish_prepared_upload` 同时补列既有的 `FileNotFoundError`，其异常原因使用通用描述，不限定为 delete 路径；`_delete_source_document` 保留既有 `FileNotFoundError`，并保留两处其它既有异常说明。不修改服务行为、签名或异常处理。

只读回归：`tests/fins/test_sec_pipeline_upload_filing_stream.py` 的 filing auto-after-delete、`tests/fins/test_sec_pipeline_upload_material_stream.py`、`tests/fins/test_cn_pipeline.py` 以及上述文件既有测试。若 review 发现白名单外修改确属正确 owner 所必需，先回到 goal/plan 裁决，不擅自扩展。

MiMo 按本计划的五文件测试集实测 `_fs_source_document_core.py` 基线为 **473 statements / 97 misses / 79%**，虽然测试为 407 passed，单文件 `--fail-under=80` 已失败。实施前在本 checkout 的锁定环境用同一清单重测并记录基线；上述新增测试须以真实转换覆盖现有未测的 filing update/restore 等 owner 路径，实施后该文件须达到 ≥80%。若未达标，只补同一状态 owner 的有意义转换或失败边界测试，重新 review 测试选择，不降低门槛、不写实现镜像测试。

## 验证与真实 CLI canary

环境预检与安装先于实施验证。本 checkout 当前无 `.venv`；`README.md` 的 Python 3.11 与平台锁文件是安装真源。实施 agent 在 `/private/tmp/dayu-upload-o13` 建立独立环境，以当前 macOS Apple Silicon 锁文件 editable 安装 **本 checkout**：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test,dev,browser]" -c constraints/lock-macos-arm64-py311.txt
```

若执行平台与本 checkout README 的锁文件不一致，按 README 所列平台锁文件替换，并记录平台与命令。安装失败、解释器不是 Python 3.11，或 editable import/CLI 身份不能指向本 checkout 时，验证 gate 停止；不得借用主工作区 `.venv`、`dayu-cli` 或仅靠当前工作目录推定导入身份。安装成功后记录 `git rev-parse HEAD`、`sys.executable`、`sys.version`、`dayu.__file__`、`command -v dayu-cli` 与 `.venv/bin/dayu-cli` console script 的 shebang/入口；检查 editable 安装的 distribution `direct_url.json` 指向本 checkout。从隔离 CLI 执行目录、清除外部 `PYTHONPATH` 后，用本 checkout `.venv/bin/python` 实测 `dayu.__file__` 解析为本 checkout `dayu/__init__.py`，并核对 CLI 脚本 shebang 指向同一 `.venv` 解释器、入口为 `dayu.cli.__main__:exit_module`。每次真实 CLI 命令前重新断言并随该步证据保存 HEAD、解释器、editable 来源、导入路径和 console script 身份。

实施后的验证次序：

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_fins_storage_atomicity.py tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py -q
python -m pyright dayu/ tests/ utils/
coverage erase
coverage run -m pytest tests/fins/test_fins_storage_atomicity.py tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py -q
coverage report --include='dayu/fins/storage/_fs_source_document_core.py' --fail-under=80
```

覆盖率按 **每个实际行为修改的生产文件单独** 检查 ≥80%；当前行为修改白名单只有 `_fs_source_document_core.py`。第 5–7 项只改指定方法的 Raises docstring，不增加可执行语句；若经重新裁决增加行为修改文件，各文件分别运行 `coverage report --include=... --fail-under=80`，不得用聚合覆盖率掩盖。pyright 应无新增/扩散错误；若触及既有错误须修至受影响范围通过并如实列明。测试应精确比较 bytes 与 owner 时间/版本，不能以仅有 exit 0 代替断言。

真实 CLI 状态链另在 **全新隔离目录** 执行，不能重用或写入主工作区冻结 calibration tree。只调用经上述每步身份断言的本 checkout `.venv/bin/dayu-cli`，固定一份 `probe.txt`，初始化独立 `--base`，用 `AAPL`、`MATERIAL_OTHER`、`Calibration Deck` 构成稳定 identity。参考冻结 `UM-A01/A07/A08/A09` 的 `command.json` 参数面，但所有路径改指本次隔离目录：

1. `upload_material --base <isolated> --ticker AAPL --action auto --forms MATERIAL_OTHER --material-name 'Calibration Deck' --files <isolated-input>/probe.txt --company-name 'Apple Inc.'` 创建；记录成功退出码、结果 ID、版本及相关文件快照。
2. 相同 `--base/ticker/forms/material-name`、`--action delete`、不带 `--files` 首删；记录退出码、结果、meta/manifest JSON、原始 bytes/hash、资产 bytes/hash。
3. 完全相同命令重删；断言成功且仍报告已删除；`deleted_at`、`updated_at`、source revision、版本、source meta/manifest 与原资产的 bytes/hash 均等于第 2 步；不要求第 2 步首次删除的两个时间戳逐字相等，不把 `mtime/inode` 当失败信号。
4. 以第 1 步同一文件和 `--action auto` 恢复；断言 ID 与版本保持、`is_deleted=False`、`deleted_at=None`、revision 翻新；随后再次 delete，断言新 `deleted_at` 与第 2 步不同、revision 再翻新、版本和资产 bytes 不变，meta/manifest 的 tombstone 值一致。

每步保存 argv、checkout/venv 身份、退出码、stdout/stderr、结果 JSON（若有）、源 meta/manifest 原始字节摘要及 parsed 关键字段、原资产摘要和步骤间 diff。命令应在独立 workspace 顺序运行；不要以旧 A08 时间、固定终端文案或仅凭 JSON 字段值代替字节证据。若两次操作在时钟分辨率内导致新周期时间相等，用受控时钟的 owner 测试证明转换语义；CLI canary 应等待跨过时间分辨率后重跑新周期观测，不篡改持久文件。

## README 决策

已核对 `dayu/fins/README.md` 的 `Agent更新约束【必须遵守】`：只写当前代码已实现且对开发者稳定有用的 Fins 契约，更新前须核对当前代码。现有 storage 段落写“每次 source ... delete 或 restore”均翻新 published revision；同周期重删 no-op 实现后，应按白名单第 4 项同步修正重复 tombstone/no-op、revision 与 delete/restore 两方向损坏 `is_deleted` 的状态合同，并核对统一严格读者描述。**本轮只修 plan，不修改 README 正文**；实施时在产品状态转换完成后更新该文档。`tests/README.md` 只记录测试层级/运行约定，若本次仍沿用现有 Fins 测试层级与命令则无需修改；根 `README.md` 的用户 CLI 参数/工作流不变，`dayu/README.md` 的分层/装配不变，均按各自触发条件检查。

## 集成边界、风险与下一入口

- O14/O15：其 material action/target precondition 与 target-missing typed 拒绝是另一 owner 工作项。O13 仅对仓储已存在且确认为 tombstone 的 source no-op；不定义 create/overwrite/update/missing 的新策略。集成时先核对 O14/O15 是否仍把重复 delete 交给仓储，而非提前错误化；如冲突，先裁决动作合同。
- O18：amended 是独立发布事实，不从本次 tombstone 时间推断；本项不改 amended、fingerprint、skip 或恢复标记规则。合流时检查新 O18 source meta 投影没有被 O13 no-op 擦写。
- O33：并发 auto/identity 状态串行化另案；本次只验证顺序请求与现有 ticker batch 串行路径，不声称并发重复 delete 或 auto 的结果。
- `begin_batch/commit_batch` 对重复 delete 仍执行物理 tree swap；内容字节相同不等于零 I/O、inode/mtime 不变。material CLI 的 company-meta 阶段可独立执行 batch；本项保证 source meta/manifest/资产合同，不把其它层的 company 更新伪装成 source tombstone 漂移。若实测出现 source 业务字节漂移，直接定位写入 owner 并停止，不在展示层过滤差异。
- 旧冻结 A08 是 bug 证据，不能当预期；新 CLI canary 只证明其隔离环境与输入，不能外推不同内容恢复或并发行为。

本计划完成后下一入口是有效 Kimi/MiMo 双路 `plan review`；本轮明确停在修订候选与双路复审之前，不派发 review、不实施、不提交/推送。完成报告应写明本计划路径、SHA-256、静态检查、直接代码与裁决证据、验证尚未运行的事实及残余风险。
