# UM-O17-F01 PR5-F1 计划修订记录

- 工作区：`/private/tmp/dayu-upload-o17`。本次只修改 `docs/gateflow/upload-material-o17-form-plan-20260929.md` 并新增本记录；未实施、提交或发布。
- 原计划 SHA-256：`7c818f9dbc2a8276b5a47a49918307efb8437823b6c2cb677b3743b1e34eacd8`，写入前按文件字节核验，与任务锁定值一致。
- 修订后计划 SHA-256：`7b37c7279183bf56af2acfe722062f4b768a1f2e868eb96db37721d2578dbe24`。
- 修复对象：总控裁决 `upload-material-o17-plan-review-adjudication-20260929.md` 的 PR5-F1。MiMo 同版复审指出 batch/CLI 独立文本规范化；Kimi 同版未报此项，不作为“该路径不存在”的代码证据。

## 动机及一手证据

动机成立。当前 `dayu/fins/pipelines/docling_upload_service.py:1842` 的 `build_material_ids` 对 material form 做 `strip().upper()`；`dayu/fins/upload_batch.py:799-814` 的 `_validated_material_form` 对 batch override 再做 `strip().upper()`，随后按 `_MATERIAL_FORM_TYPES` 校验；`dayu/cli/commands/fins.py:1193-1208` 的 `_single_batch_material_form` 在解析后再次 `.upper()`。`upload_batch.py:294-310,573-578` 证明 override 或文件名 routing 类别进入 `UploadBatchMaterialEntry.form_type`；`fins.py:413-414` 将这个 typed 值原样置于 `upload_material --forms`。所以 batch override 与单条上传指向同一 material form 文本事实，保留多套文本规则会漂移。

边界也由当前代码直接支持：`upload_batch.py:82-91` 的 routing table 只产三个封闭类别，`_match_material_form` 在 `:500-510` 按文件名匹配，override 仅覆盖已路由 material；这个允许域和路由顺序仍由 batch owner 决定。`docling_upload_service.py` 与 `upload_batch.py` 当前没有相互导入；计划让后者单向复用前者的纯函数，不引入循环。若实施时发现二者实为不同 form 语义或依赖方向出现反例，按原停止条件停下，不添加兼容 shim。

## 计划修订

1. 唯一 `normalize_material_form_type(form_type: str) -> str` 的消费范围增列 batch material form 文本；batch `_validated_material_form` 复用函数后仍校验自己的封闭集合，保持空白/不支持值的 `UploadBatchPlanUsageError` 分类和请求校验时序。文件名路由字面值已是 canonical，不增第二个文本规范化函数。
2. CLI `_single_batch_material_form` 只解析 `--material-forms` 的单值和空白，传唯一原始非空 item；删除独立 `.upper()`。生成命令继续机械使用 batch typed entry 的 canonical `form_type`，regeneration 继续带原始候选供 batch owner 处理。CLI `--forms` 的现有单值/空值解析不扩入本修订。
3. 精确实施白名单增 `dayu/fins/upload_batch.py`、`dayu/cli/commands/fins.py`、`tests/fins/test_upload_batch.py`、`tests/cli/test_fins_commands.py`。owner 级测试要锁 padded/mixed-case override、batch 封闭域和旧错误边界；跨链测试必须断言真实 batch typed entry → 生成 `--forms` → runner material request 同一 canonical 值，不能只断言脚本或 fake service。其余旧白名单及 README 条件规则保留。
4. 原计划的 O09 `build_material_ids` before-seed 串行点、PR4-F2 真实事件/result JSON 字段断言、O05 `None`/空白失败时序、历史 raw 独立处置、真实 CLI 跨命令读回、逐实际改动生产文件 `>=80%` coverage、pyright 和 README 职责边界均保留。batch/CLI 新生产文件也受逐文件覆盖率门槛约束。

## 验证与命令披露

- 已读取任务指定的 AGENTS、goal、原计划、总控裁决、Kimi/MiMo PR4 review 与三个指定生产文件，并核对 batch typed entry、CLI argv 和单条 material 入口代码。对修订计划检索旧“第 8 项”引用、PR4/O05/O09/历史/coverage/README 条款及新增白名单，旧引用已改为“第 11 项”；新旧 SHA 均由 `sha256sum` 按文件字节计算。
- 本次只有计划文档变更，无产品或测试代码变更；未运行受影响测试、coverage 或 pyright，实施 gate 仍须按计划执行。未修改 goal、旧 review、总控裁决、产品、测试或 README；未派发子 Agent，未 commit/push/PR/merge。
- 非零命令：初次 `rg -n 'UM-O17|upload-material-o17|material form' /Users/leo/.codex/memories/MEMORY.md` 退出码 1，表示记忆索引无匹配；未用于任何代码、语义或计划结论。其余已回读的 shell 命令退出码均为 0；三次计划 `apply_patch` 与本文件新增成功。

结论：PR5-F1 的计划遗漏已补，停止条件未触发；此记录只证明计划一致性，不构成实施验收。
