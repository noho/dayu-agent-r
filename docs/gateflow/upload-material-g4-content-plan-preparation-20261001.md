RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-f9861bfd

# G4：O21/O22 内容失败同源传播准备计划

任务：`pr197-g4g5-plan-preparation-sol-20261001-01`。状态：**preparation proposal；非 accepted plan、非 gate pass、未实施**。
第三列精确模型无可读取遥测，不能从路由或 canary 推断；本轮 canary 已从指定文件实读。
唯一主树 `dayu-agent-r`、指定 branch `codex/upload-material-oracle`；产品 writer 为 F5 Sol97574，本轮只新增本 proposal、G5 proposal 和独占证据。
用户本轮已确认目标与批准 WU 的后续授权；本准备任务到交付即停，不重新请求 O21/O22 裁决。

## 1. 版本、goal 映射与动机

- 唯一源码基线：`3a836a463aab3eeffb050facd592e614801d6ca9`。未读取当前可变产品、其它在途报告、私有原件或旧隔离树。
- 证据根：`workspace/tmp/pr197-g4g5-plan-preparation-sol-20261001-01/`；`freeze.json` SHA-256=`9ae2c95cdd86b6ba7402b5547d063a6df7e98523d5ef77d2e4a578cf16b25838`。
- 40 件 pinned 字节逐项匹配；freeze `absent=[]`。必要补源仅 `git show <上述 OID>:<路径>` 到 `supplemental/`，hash/blob/缺件记录见 `supplemental-index.json`，不冒充 freeze 清单成员。
- 正式 binding：`docs/gateflow/upload-material-content-failure-goal-20260929.md`；O21/O22 oracle 分别为 `docs/reviews/upload-material-um-o21-oracle-adjudication.md`、`upload-material-um-o22-oracle-adjudication.md`。
- 旧候选与最新必要裁决：`upload-material-content-failure-plan-20260929.md`、`upload-material-content-plan-review-adjudication-20260929.md`。历史 workspace/venv/隔离树安排已废止；本轮主树约束优先。
- O21：逐文件失败指出实际原件，沿现有 `content/docling_converter_execution` 传播，材料整体不发布。
- O22：相同 0-byte filing/material 在共同读字节边界生成现有 `content/empty_input_file`、安全有界当前标签和可行动提示。
- 两项合为 **唯一 S1：从原件 owner 到所有终态的一条完整失败传播 slice**。只有 owner 修复而 tool 仍截断，或只修显示却丢持久事实，都不是完整增量。
- 动机成立，严重性是错误分类与定位失真；旧 F16–F19/S18 未证明任意 commit 故障原子性，也未证明公司零副作用，不扩大目标。

## 2. pinned 真实函数、callers 与唯一 owner

| 事实 / owner | 精确基线直接证据 | 后续最小决定 |
| --- | --- | --- |
| 原件字节 / `DoclingUploadService._build_original_assets` | `docling_upload_service.py:904–912` 读 `pair.path`，只有 filing 的空字节生成 typed reason | 对两类原件统一 `raw_data == b""` 判定；仍先完成资产/路径准入 |
| 当前转换文件 / `_build_pending_assets` | `:966–1001` 当前 `pair.path` 已知，material `DoclingConversionError` 直接 rethrow | 在此 canonicalize `file_path.name`，包装已有 reason，保留原 cause |
| 安全公开标签 / `direct_events.canonicalize_fins_public_file_label` | `direct_events.py:1100` 已有唯一 canonicalizer，240 上界及隐藏规则 | 直接复用；不得用仓储资产名、stem、输入序号或异常文本替代原件 |
| reason / `upload_failure.fins_upload_failure_from_exception` | `upload_failure.py:228` 无 `FinsUploadFailureError` 透传，material 外层传 `file_label=None` | 首分支返回 `error.failure` 对象本身；不重分类/覆盖 label |
| tool 路径形状 / `_validate_upload_file_path` | `upload_tools.py:531–534` 在 is_file 后仍 `st_size <= 0` 提前 invalid_argument | 仅删除大小判定，保留存在/普通文件路径约束与对应中文 docstring |
| 资产命名 / `UploadAssetPlan`、`plan_upload_assets`、`docling_storage_name` | `upload_asset_plan.py:75–171,267,379` 已在 PR；material converter_pairs 等于全部 ordered_pairs | 消费既有 plan；不重造派生名 helper，不缩减 material 全原件 Docling |

调用链：CLI `_prevalidate_upload_material_request` → Service `FinsDirectCommandService.upload_material` → runtime/production runner → SEC `run_upload_material_stream` 或 CN/HK `CnPipeline.upload_material_stream` → `prepare_upload` → 两个内容 owner。
独立 pipeline 也消费同一资产准入；SEC `sec_upload_workflow.py:584–613`、CN `cn_pipeline.py:1230` 的外层 catch 只投影 resolver 返回的 reason。
runtime `FinsUploadPipelineResult.from_pipeline_json` 严格解析五字段 → `FinsUploadResultSummary.failure_reason` → `_upload_result_details` → direct/CLI/observation；不从 `FinsResultSummary.failure` 猜 reason。
真正 job 的 `_run_upload_job:5098–5107` 从同一 summary 写两摘要，使用 active-only 保存；其它 no-runner/泛异常修复归 G3/O12，不在 G4 重做。

## 3. 最小 proposed API 与允许改动

**无新增 public API/schema/code/kind**。拟改变现存函数的行为合同，签名优先保持：

- `_build_original_assets(pairs: tuple[UploadAssetPair, ...], *, source_kind: SourceKind) -> list[_PendingFileAsset]`：filing/material 空原件都抛现有 `FinsUploadFailureError`。
- `_build_pending_assets(preparation: UploadAssetPlan, original_assets: list[_PendingFileAsset], *, source_kind: SourceKind, cancellation: CancellationToken | None) -> tuple[list[_PendingFileAsset], list[UploadFileEventPayload], str]`：同一逐文件 catch 包装 reason；取消异常仍独立传播。
- `fins_upload_failure_from_exception(error: Exception, *, file_label: str | None) -> FinsUploadFailureReason`：typed error 原对象透传先于所有分类；普通异常既有映射保持。
- `_validate_upload_file_path(candidate: Path) -> None`：只拥有路径形状；空内容由实际 read owner 判定，stat/read 之间变化不猜测。
- `fins_upload_empty_input_failure` 与上述函数中文 docstring 同步 filing/material 范围；共享日志的两处 `Filing upload` 改为中立上传描述，这是已有 accepted finding 的同 owner 修复，不另造日志 WU。

S1 产品白名单仅 `dayu/fins/pipelines/docling_upload_service.py`、`dayu/fins/upload_failure.py`、`dayu/fins/tools/upload_tools.py`。
测试白名单：`tests/fins/test_docling_upload_service.py`、`test_upload_failure.py`、`test_sec_pipeline_upload_material_stream.py`、`test_cn_pipeline.py`、`test_fins_ingestion_runtime.py`、`test_fins_ingestion_tools.py`、`test_sec_pipeline_upload_filing_stream.py`、`tests/cli/test_fins_commands.py`；共享仓储取消/提交回归用既有 `test_fins_storage_atomicity.py`。
市场、runtime、Service、CLI、storage、planner 产品默认不改；若真实同源链不能保持 reason，向 root 提交 owner 反例并重绑白名单，禁止 adapter fallback。

## 4. 完整时序、失败与取消边界

1. G1 静态准入及现存资产 plan 在读字节前完成；tool 路径存在/普通文件仍在正常 owner 前置。非法路径、身份、资产名不被内容失败吞并。
2. 市场 workflow 独立提交合法公司事实后，`prepare_upload` 检查取消及动作前置条件，再读取全部原件。公司阶段失败不冒充内容失败。
3. 任一原件为空：共同 owner 立即产生 `content/empty_input_file`；不启动 Docling、不创建材料 mutation batch。有效文件在前、空文件在后也 stored=0。
4. 所有字节合法后按现存 selection 转换；material 全原件均 Docling。每次转换前检查取消；任一当前原件 conversion error 包装同一 typed reason、保留 cause；已转换的内存资产全部丢弃，不发布 source/meta/manifest。
5. `DoclingConversionCancelledError` 与既有取消检查走取消终态，不能转 content failure。保留 F6 当前取消优先级/线性化，不添加新轮询或调整 race 规则。
6. 全部成功才形成 prepared mutation；`commit_prepared_upload_batch` 负责 staging、最终取消 checkpoint、rollback 与 capability 转交。G4 不移动此 guard：commit 开始前取消回滚，进入 `commit_batch` 后 caller 不再取消/rollback。
7. 市场 failed event/result 的五字段来自同一 `failure.to_json()`；direct/CLI/tool 只投影；读 I/O、storage 异常不因 content 修复改类。
8. 材料失败/取消后，已合法公司 commit 按 O34 保留；不能称整工作区零 diff，不逆向删除公司，也不引入公司+材料共同事务。

**observation 与 job 必须分开验收**：tool `prepare_observed_upload` 的 execution context 为 `job_record=None`，先 `ToolAwaitingOutcome`，激活后 poll FAILED，检查 `result.details/error_message`；durable 查询为 queried-but-absent。
另用 `start_upload` 真正创建 job、production runner 返回内容失败，读取 `result_summary.failure` 与 `failure_summary`，两者等于同一 owner JSON；active-only 终态不得覆盖已落盘取消/完成。

## 5. 旧 accepted findings 闭合映射

| 必要 finding | S1 对应闭合证据（均待实施，not-run） |
| --- | --- |
| O21-F01 / O22-F01 | owner typed kind/code/当前 safe label、材料无部分发布、全入口五字段一致 |
| content 首轮 MiMo F1：tool st_size 截胡 | 迁移实际 `_validate_upload_file_path`；空文件进入 observation；missing/目录仍前置拒绝 |
| 旧 nth-conversion `file_label=None` / 原样异常断言 | `test_prepare_material_nth_conversion_failure_discards_partial_work`、SEC 同名终态测试断言 damaged 原件 label 与 cause |
| 第二轮 F1：observation/job 混淆 | 分开 tool 无 job 与 start_upload 真 job 的双摘要；不依赖通用 summary.failure |
| 第二轮 F2：operator log 误标 Filing | 同两处 owner 日志中立化；公开 reason 不泄露路径/异常文本 |
| O04/O23 集成 | 既有 plan/派生名 helper 直接消费，原件 label 来自 pair.path.name，保留 planner 优先级 |

补迁移 pinned 新测试 `test_upload_tool_material_keeps_file_state_precheck_after_admission` 的 empty 参数格；保留 missing/directory 格。
旧 content plan 两 slice 合并为本 S1；旧单路 pass 不能作本计划门禁票，不改旧报告元数据或另立 nit 工作。

## 6. owner 测试矩阵与最终 campaign

| 矩阵 | 必须断言 |
| --- | --- |
| material/filing 单空、有效+空、空+有效 | typed reason 五字段与实际当前 label；空多文件在 converter 前失败；材料 source/blob/meta/manifest 无发布 |
| 单损坏 PDF/DOCX、有效+损坏、调换损坏位置 | 已有 converter-execution 类别、损坏原件 label、原 cause；不能用序号猜标签 |
| 长 basename、控制字符/需隐藏名称 | canonical 隐藏规则/上界、无绝对路径；直接非法 label 仍被 reason 校验拒绝 |
| typed resolver + 普通异常/其它 Docling kind | `resolver(error, file_label=None) is error.failure`；既有 closed 分类穷尽不漂移 |
| SEC/CN/HK material、filing 回归 | event failure JSON/result/error 与 owner 相等，requested/stored 正确；公司独立合法事实如实保留 |
| tool/direct/真 job | observation 五字段/details/error_message；无 job；另 job 两摘要同源及 active-only 取消保护 |
| 真实 FS + barrier | 临时 Fs 仓储冻结转换中/第二文件前：取消不发布材料；成功提交后的晚取消不覆写；公司 commit 后内容失败保留公司 |

使用真实临时 FS 检查全部业务文件、source meta、manifest 与 hash；受控 converter 只注入 typed 转换 outcome，不让 fake 仓储证明发布语义。barrier 使用 bounded Event/Barrier，finally 解锁并收集线程/进程，禁止挂起测试。
最终 aggregate campaign 才跑真实 Docling 与普通/debug CLI：离线公开合成 empty.txt、corrupt.pdf、corrupt.docx、有效 probe.txt+损坏文件；全部记录输入 bytes/hash 与新 lineage。
按最终 G1/G2 请求 CLI 重新绑定 argv；参考已批准 `upload_material --base <fresh-base> --ticker AAPL --action auto --forms MATERIAL_OTHER --material-name <独立名称> --company-name 'Apple Inc.' --files <输入>`；debug 组加 `--debug --log-file <独立日志>`。
锁定主树 `.venv` Python3.11、`sys.executable/dayu.__file__/CLI`；每 run 保存 command、双流、exit/timeout、summary、before/after/diff、公司/source/manifest/资产 hash、durable 查询及最终进程树。普通/debug 同 reason/label，stored=0；旧 F16–F19/S18 不覆盖。

## 7. 实施后验证与 README 触发（本轮全部 not-run）

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_docling_upload_service.py tests/fins/test_upload_failure.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_fins_storage_atomicity.py tests/cli/test_fins_commands.py -q
python -m pyright dayu/ tests/ utils/
```

full pyright 使用最终配置覆盖整 `dayu/tests/utils`，不能只检查三文件或排除新增错误。受影响 tests 再加 pytest-cov 输出 JSON 到实施者独占证据目录；逐个实际修改生产 `.py` 的 `summary.percent_covered >=80`，不能用总覆盖率代替；低于门槛补 owner 测试。
已读 pinned 根 README 的用户手册约束、Fins README 的已实现架构/契约约束及 tests README 的当前测试职责。实施时检查 Fins 失败 owner 说明、根 README 的空/损坏文件排障、tests 的稳定矩阵是否需更新；只有职责内新增事实才写。本轮不改 README；无分层改变，不机械更新其它 README。

## 8. classified residual、实际 source rebind 与交付停止

| 分类 / owner / destination | 处置 |
| --- | --- |
| fixed in current slice（拟，未修）/ G4 | O21/O22、st_size、typed resolver、同 owner 日志与测试迁移；实施/复审证明后才能标已修 |
| covered by later approved slice / G1–G3 | 最终准入、primary/fingerprint、公司/目标/amended 状态与 O12 job 泛异常/no-runner 双摘要；G4 不复制其实现 |
| assigned to later work unit / storage | 任意 commit 中途与 post-commit 不确定性；G4 不作新成功承诺，G5 按 owner 重绑 |
| assigned to later work unit / Docling runtime | 抽取质量、格式 capability/XBRL 部署与 OCR；不吸入 G4 |

实施前 root 在最终明确 OID 重绑：①G1 validated material handoff/路径优先级；②资产 plan/pair/converter_pairs/helper 真源及 G2 primary 接线，所有 material 原件仍 Docling；③G3 独立公司 commit、content failure 保留语义；④F6 cancellation 与 `commit_prepared_upload_batch` capability 边界；⑤tool 实际路径校验函数；⑥市场 catch→runtime strict parser→direct/details→observation；⑦start_upload active-only 两摘要；⑧上述旧断言的新位置与 README 当前职责。
G4 可独立准备，无证据要求 G2/G3 先 accepted 才能形成此 proposal；正式实施前重叠源码须串行重新核 diff，禁止覆盖唯一产品 writer。
若 reason 无法同源穿透、必须新增公开分类/schema，或内容/取消 owner 不清，携精确代码与最小反例交 root，停止实施，不让用户重述既有裁决。
本轮只完成 preparation、冻结核验与补源索引；pytest/pyright/cov/CLI/转换/OCR/review/commit/push/PR 均 **not-run**。交付后停止；下一入口由 root 决定正式 source rebind 和 plan review。
