# upload_material G2：主原件选择与角色发布 preparation proposal

- 任务 `pr197-g2g3-plan-preparation-sol-20261001-01`；**仅 preparation，非 accepted plan、非 gate pass、非实现或测试通过**。
- 唯一 workspace `/Users/leo/workspace/dayu-agent-r`；branch `codex/upload-material-oracle`；PR197 用户手工 merge，main 不动。
- 产品和 binding docs 仅取 `3a836a463aab3eeffb050facd592e614801d6ca9`，简称 pin；没有读取当前 F5 writer90509 产品或在途报告。
- 证据根 `workspace/tmp/pr197-g2g3-plan-preparation-sol-20261001-01/`；freeze SHA256 `14a696de1eb6ac568adf91dcb8f4b56fd637427a415ab17e31ec6c41d7898c47`，40 件逐件匹配 exact Git bytes；absent 原样记录。
- G1 preparation 副本 SHA256 `71f6a639a2b76974816999f54b7c553aaf16ef397c34ff986489be761f4f4e05`，**其 identity/action 新类型尚非 accepted 接口，不视为存在**。
- 必要补源只用 `git show <pin>:<path>` 写独占 supplemental；hash/index 和读取范围见证据根 `evidence/`。无 clone/worktree、网络、运行产品或修改旧文件。

## 1. goal 映射与一个行为增量

动机成立：pin 的 material 转换取首项 Docling 为 primary，而指纹按原件名排序；用户主文件意图缺失，顺序变化还可能被 skip 吞掉。影响跨命令默认读取，修复应在选择/资产 owner，不在 read 或 CLI 猜测。
唯一增量 **G2-S1：公开 exact 主原件选择贯通角色指纹、发布和读取**，不按 action/module/旧 review 再切 slice。

| binding 文件（相对路径） | 必须保持的合同 |
| --- | --- |
| `docs/reviews/upload-material-um-o25-oracle-adjudication.md:32–46` | 多原件必须 exact 唯一 primary；单原件省略时默认唯一；所有原件仍 Docling；同角色同指纹，不同角色改变指纹，稳定 material ID 不变 |
| `docs/gateflow/upload-material-o25-primary-goal-20260929.md` | 四 selector 错误转换前 typed；CLI/tool/Service/独立市场同源；source/meta/manifest/read 一致；process_material 验实际主源 |
| `docs/gateflow/upload-material-o25-plan-review-adjudication-20260929.md` | PR1-F1–F5 内容候选已修；有效 MiMo 一路不等于正式双审或 accepted plan；实施前重绑 O16/O04/O23 与共同准入次序 |
| `docs/gateflow/upload-material-remaining-work-batching-preparation-20261001.md` G2/G3 | 本组独立完整角色验收；G3 版本与 amended 消费 G2 最终角色指纹；batchproposal 不代替 gate |

四 reason：`MISSING_MULTI_FILE_PRIMARY`、`MULTIPLE_PRIMARY_SELECTORS`、`PRIMARY_NOT_IN_FILES`、`PRIMARY_NOT_ALLOWED_FOR_DELETE`。业务文案分别为“多文件必须指定一个主文件”“主文件只能指定一次”“主文件路径必须精确匹配本次上传文件路径之一”“删除时不得指定主文件”；不向 tool 输出 CLI flag。

## 2. pin 实际 owner / caller 与最小 API

R=`dayu/fins/ingestion_runtime.py`，A=`dayu/fins/upload_asset_plan.py`，D=`dayu/fins/pipelines/docling_upload_service.py`，U=`dayu/fins/upload_usage_contract.py`；行号均 pin。

| 实际证据 | 判断 / proposed 增量（不是现存 symbol） |
| --- | --- |
| R:885 `_project_fins_upload_filing_selection`；1154–1187 filing 准入 | exact projection 已有，不能再写 material 选主算法。**proposed**：将该纯算法和 closed selection failure 迁入 A，公开 `project_upload_primary_selection(files: tuple[Path,...], primary_selectors: tuple[Path,...])`，返回小型 immutable primary/companions projection 或 closed failure；R 的 filing 构造/错误映射仍在原边界，无旧 alias/wrapper |
| A:85–173 `UploadAssetPlan`；379–465 `plan_upload_assets` | 当前只有 `filing_primary_original_name`，material 明确禁止角色。**proposed**：替换为 `primary_original_name: str | None`；upsert 必须 exact 命中一个 pair，delete 必为 None；filing converter_pairs 仅 primary，material converter_pairs 仍全部 ordered_pairs |
| A:174/202/267 path identity、`docling_storage_name` | 不改变规范路径语义；exact 指规范后 path identity，不是 basename/stem 匹配。material planner 接显式 `material_primary_selectors: tuple[Path,...]`，同一规范路径 owner→上述 projection→一次 pair/role plan；不引入第二派生名函数 |
| R:1419/1460/1526/1566 request/handoff/admission | **proposed** raw material request 加 `primary_selectors: tuple[Path,...]=()`；保留 occurrence；既有 handoff carry 同一 asset_plan，构造/validate 防 request/plan 角色漂移。不假设 G1 proposed identity 已集成 |
| D:462/932–1028/1595–1698 | 当前 material 无 role 指纹且首转换项 primary。消费 plan 的唯一 primary pair，primary_document 取该 pair.docling_name；指纹入参改为中性 primary_original_name，material role payload 含选中 descriptor 与排序 companions；filing 序列化字节、安全性规则保持 |
| D:1560/1690 `_can_skip_upload`/`_resolve_document_version` | material `identical_skip_safe` 仍 true：原件名唯一，descriptor 可区分角色；不造不可达 unsafe-material 例外。只有角色/内容指纹变化升版，same-role 逆序不变 |
| D:548/623/1030；storage `_fs_source_snapshot.py:733–829/463` | publish 只用准备好的 primary，source meta 真源；stable snapshot 校验并物化同版 meta/revision/primary/files，read 不重选 |
| `domain/document_models.py:1029–1110` MaterialManifestItem | pin 没有 primary 字段。**proposed** 增 required `primary_document: str`，由 source meta 严格读取且与 files exact 对应；同源 manifest 摘要不从指纹反推角色，不补默认值 |
| `tools/read_runtime.py:3020`；R:5879 | `_create_processor_from_snapshot` 与 preprocess 已消费 snapshot.get_primary_source；正常无需改选主逻辑，只用真实 snapshot/processor contract 验默认源 |

实际入口：CLI `arg_parsing.py:_register_upload_material_command`→`commands/fins.py:_prevalidate_upload_material_request`→`service/fins_direct.py:upload_material`；tool `upload_tools.py:_upload_request_from_arguments` 当前拒 material primary；`service_runtime.py:ProductionFinsUploadRunner._run_material_upload`→SEC/CN validated façade→SEC workflow:417 / CN:1065→D。SEC raw façade:805/832 与 CN:985/1012 必须可表达 selector，同步/异步同源。
CLI 复用已有 `ParsedCliArgs.primary`/append 机制（pin 只有 filing 注册 flag），新增 material `--primary`；tool 继续单值 string/null `primary`，机械转 tuple，去掉 material 拒绝分支。tool 的重复输入不伪造 JSON duplicate-key 合同，重复 reason 在 CLI/raw owner 测；Service 传同一个 request/handoff，不装进 extra payload。

## 3. 连贯副作用时序与发布边界

1. F5 最终交付闭环、G1 accepted+integrated 后重新绑定真实完整受理；action/files 先于 selector：delete+files+primary 必须先 O16 files reason，合法零文件 delete+primary 才 selector reason。G1 各入口词法/字段首错保持，不发明跨入口全序；joint-invalid 按实际共同 owner 锁定。
2. 原件数/路径/整批名称/format 仍由既有 A owner 判定；在同一 material planner 合入 primary projection，保持已裁名称与格式首错。四 selector 错误最迟在 lifecycle/公司提交/原件 bytes 读取/Docling 前拒绝。missing/重复 selector 不被 normalize/deduplicate 掩盖；delete 不读取 selector 对应文件。
3. 合法 plan 保序全部转换，选中非首项不改变转换数；所有转换完成后准备一个文档 mutation。ID 只来自 G1 最终身份 owner，primary/amended 不参与 request document ID 或内部 ID seed。
4. 角色同源进入 fingerprint→skip/version→source primary_document→manifest→stable read snapshot；A→B→B（最后原件逆序、同 B）在真实新库为 v1→v2→v2，末次 skipped，全部 document/internal ID 不变。
5. 共享 `commit_prepared_upload_batch`（D:1360）仍是 publication 生命周期 owner；stage 完整 manifest 不等于 durable 成功。commit 正常返回才报告本次发布；取消 linearization、capability 转移及 commit 后不回滚保持。
6. 本组不宣称关闭材料同版状态/skip stale 窗口；G3 将消费最终角色 plan 并完成 guard。G2 本身不得用当前 FileExistsError/I/O 失败变 skip；O33 authority retry/并发策略单独 later 组。
7. `_fs_storage_infra.py:533–607/676–735` 已允许 COMMITTED 后 release 抛错；它不证明未提交。保留 durable 事实与主异常，不自行改公共成功 contract；certainty 缺口与 G3 同列 source rebind 停点，不能用 read adapter 重读伪造成功。

## 4. 后续允许源码 / 测试 / 文档

| 仓库相对路径 | 允许的必要变更 |
| --- | --- |
| `dayu/fins/upload_asset_plan.py`、`upload_format_contract.py`、`upload_usage_contract.py` | 迁唯一选择 projection、required role plan、通道自足 help/schema；删除旧 material-primary 拒绝文本/字段；U 唯一 selector code/message，不建 runtime 副本 |
| `dayu/fins/ingestion_runtime.py`、`pipelines/docling_upload_service.py` | raw selector/handoff 校验；filing projection caller 机械迁移；同源 primary/fingerprint/skip/version，不改 G1 身份规则 |
| `dayu/fins/pipelines/sec_pipeline.py`、`sec_upload_workflow.py`、`cn_pipeline.py` | raw façade 参数与 validated 消费；两个市场不得各自规划 primary |
| `dayu/cli/arg_parsing.py`、`commands/fins.py`、`dayu/fins/tools/upload_tools.py` | append occurrence 与字段透传、help/schema、共同 error 投影 |
| `dayu/fins/domain/document_models.py` | MaterialManifestItem 严格 primary 投影；触及签名改为可严格检查的 JsonValue 返回，不扩 filing schema |
| `dayu/fins/service_runtime.py`、`dayu/service/fins_direct.py` | 仅实际 request/handoff annotations/透传与必要 summary；纯透传可零 diff，不造 wrapper |
| `tests/fins/test_upload_asset_plan.py`、`test_upload_usage_contract.py`、`test_upload_format_contract.py`、`test_upload_failure.py` | selector/命名/角色与共享 filing 文案/错误回归 |
| `tests/fins/test_docling_upload_service.py`、`test_fins_storage_atomicity.py`、`test_filing_upload_publication.py`、`test_fins_read_runtime.py` | 真实 storage/fake converter 的完整角色发布/read；filing 单转换/角色 fingerprint 回归 |
| `tests/fins/test_fins_ingestion_runtime.py`、`test_fins_ingestion_tools.py`、`test_fins_service_runtime.py`、`test_sec_pipeline_upload_material_stream.py`、`test_cn_pipeline.py` | 真 owner/handoff/市场入口，重复 occurrence 与副作用边界 |
| `tests/cli/test_fins_commands.py`、`tests/service/test_fins_direct.py` | CLI/parser/tool public surfaces 与同 request 消费 |
| `README.md`、`dayu/fins/README.md`、`tests/README.md` | 实施后按已读边界：根写用户 primary 操作；Fins 写稳定 role contract；tests 写实际测试职责。层关系无变时不改 dayu README |

storage/read 正常选主算法零 diff；若严格 primary 校验发现其 owner 必须修改，先在最终 rebind 明确最小文件/API 后双审，不在 read 层 fallback。以上是后续白名单，本轮只新增此 proposal/另一 proposal/独占证据。

## 5. owner 验证矩阵与旧 reviewfix 映射

| owner / 必须验证 | 断言 / 旧修复映射 |
| --- | --- |
| A/R selector | 单原件省略/显式、多原件非首项合法、四错误、同 selector 重复也拒、同 basename 异路径不得误命中；零 started/job/handle/company/material/converter；PR1-F1 |
| A plan | constructor/replace/validate 拒 role 不在 pair、delete 带 role、material converter 不全；同 stem 不同后缀仍唯一 helper，100 原件全部转换；O04/O23 合同 |
| U/CLI/tool | 四 code/message 同源中立、安全/bounded；CLI --primary 与 JSON primary 表面各自自足；filing 只迁这四句既定共享文案，选择/format/计数行为保持；PR1-F2/F5 |
| D/version/storage | A→B→B 且最后逆序：v1/v2/v2、最后无转换/资产发布，role fingerprint 与 meta/manifest/snapshot primary 一致；PR1-F4、OQ-A |
| snapshot/process/read | 新库跨命令 default source 为指定 Docling，旧 snapshot 保旧 revision/源，新 snapshot 见新角色；禁止首项/质量排序重选；PR1-F3 |
| filing 回归 | exact selection、companions 保留、仅 primary 转换、角色不可区分时既有 skip-safe=false、fingerprint 字节与 overwrite/取消契约；OQ-B/C |

迁移 `test_execute_upload_material_converts_every_selected_file`（pin:1946）的首项 primary 断言，同步补显式 selector；保留全部转换/失败无部分发布断言。迁移 `test_material_full_basename_mapping_and_order` 与 plan-source-kind 测试的 material role=None 偶然断言；不以旧 fixture 倒逼兼容。

## 6. 后续验证（本轮禁止且未运行）

```bash
source .venv/bin/activate
python -m pytest -q tests/fins/test_upload_asset_plan.py tests/fins/test_upload_usage_contract.py tests/fins/test_upload_format_contract.py tests/fins/test_upload_failure.py tests/fins/test_docling_upload_service.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_filing_upload_publication.py tests/fins/test_fins_read_runtime.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_service_runtime.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/cli/test_fins_commands.py tests/service/test_fins_direct.py --cov=dayu --cov-report=json:workspace/tmp/pr197-g2-implementation/coverage.json --cov-report=term-missing
pyright
```

最终 implementation 的 Python3.11/解释器/package/HEAD 必须绑定唯一 workspace；上述 affected pytest 一次完整跑，full pyright 无新增/扩散，触及旧错一并修。按实际 production diff 从 coverage JSON 逐改生产文件核 >=80%，不是总覆盖；不足补有意义 owner/入口测试，不降门槛。
最终真实 CLI 由 root 整体修复收口按 `upload-material-repair-scope-and-ci-closeout-20261001.md` 与最终 `docs/cli_ci.md` 重建完整 mandatory evidence：本组贡献合法多原件/四错误/A→B→B/process_material/read 子矩阵，不重复每 label campaign，不借历史 Raw/registry ready 代替。新输入采集、真实转换与完整 CI 均未在本轮执行。

## 7. 分类残余 / 最终重绑清单

| 分类 | 归属与本组处置 |
| --- | --- |
| 本组必要 fix，尚未实施 | O25 + PR1-F1–F5；formal 同版双审/root 裁决，不继承旧单路 pass |
| accepted later 组 | G3 同版 state/guard/amended 与 O33/G5 并发；不把 G2 独立验收当它们已闭环 |
| 独立残余 | 历史 material 角色缺失/指纹迁移、全局 usage 中立化、其它 download certainty；新 schema 起库，不兼容读旧资料 |
| implementation hard stop | F5/G1 最终 owner 尚未核；asset role API/manifest 同源摘要或 selector caller 不能可信表达时列具体 gap 给 root，不创造“现存” symbol |
| 尚待验证 | 受影响 pytest/full pyright/逐文件80%/README/真实 CLI/最终 PR review；本准备无 pass 票 |

root 最终重绑：①F5完成且产品 writer 退出，冻结实际 commit/文件hash；②G1 accepted+integrated 的 identity/action/handoff 与局部首错；③O04/O23 实际 A pair/path/name APIs；④本 G2 proposed projection/role API 与全 caller迁移（包括 filing）；⑤D fingerprint/version/skip 与 MaterialManifestItem schema；⑥stable snapshot/process/read owner；⑦与 G3 source state/guard 和 release certainty 的签名/责任边界；⑧允许文件/pytest/coverage/README 的最终 diff清单；⑨同版正式双审、root 裁决后才能实施。不得据本文件推进 gate。
