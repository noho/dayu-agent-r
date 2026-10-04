# S3 首轮审查修复项登记

## 身份、当前 gate 与边界

- Workspace：`/Users/leo/workspace/dayu-agent-r`；唯一开发分支：`codex/upload-material-oracle`。
- HEAD：`a514dea14c0ce66722da034502f3af54a54c3238`；main：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。
- 当前 gate：首轮 `code review S3` 已核收，下一入口为一次集中 `fix`。本登记不代表 slice 放行。
- 冻结输入：`workspace/tmp/upload-material-unified-repair-20261002/s3-review-01/frozen/identity.json`，SHA256 `71ba4bf96daa5807b1c6487c203005e5dd5a7a23b52915760595d647b8fe20ac`。
- ds-flash 已取得托管 `write_stdin` outer exit=0，结构化 result success/is_error=false。完整报告及工具轨迹核收另记总控裁决，不能仅据自报认定全部通过。

## US3-R01：内容失败时卸载访问不存在的 backend

- 裁决：**accepted / 未修复 / P2**。
- 来源：`docs/reviews/code-review-20261003-072851.md` finding 1。
- 正确 owner：`dayu/documents/docling_runtime.py:unload_xbrl_conversion` 的实际 backend 生命周期。
- 根因直接证据：现有 helper 在检查 `conversion.input.valid` 前读取 `conversion.input._backend`。实际安装 Docling `InputDocument._init_doc` 在 backend 构造抛 `DocumentLoadError` 时设置 `valid=False` 并提前返回，尚未绑定 `_backend`。
- 同源调用链：真实 XBRL 路由内容失败 → 返回失败 ConversionResult → worker 准备 execution descriptor → finally 访问不存在的 backend 抛 AttributeError → target 异常取代原内容失败。父侧将正常退出的 target failure 投影为 IPC_PROTOCOL，改变原 execution 分类。
- 子路实测：`workspace/tmp/upload-material-unified-s3-review-ds-flash-20261003-01/probe-production-helpers.out` 与 `probe-ixbrl.out`；生产 helper 原样执行，真实 `InputFormat.XML_XBRL` 路由、status=failure、input.valid=false、unload 实抛 AttributeError。总控已读探针、实际第三方源码、生产 helper 与 worker finally；CLI 终局为同路径源码推导，尚不声称有该输入的实际 CLI 票据。
- 最小修复：在 owner 先依据真实有效输入合同决定是否拥有 backend，再访问并卸载；无 backend 不宣称关闭。不在消费者 catch AttributeError、改失败映射或加 getattr/hasattr fallback。
- 验证：修正恒带 `_backend=None` 的旧 fixture，覆盖真实未绑定属性形状；实际 XBRL 路由内容失败的 owner 回归；worker descriptor/父侧失败分类保持 execution；成功 backend 仍恰好卸载一次。受影响测试、变更 owner 覆盖率和全量 pyright；不重装环境或重复完整 OS 矩阵。
- Destination：当前 S3 一次集中 fix 与同版双路 re-review。

## US3-D01：README 原件路径限制表述

- 裁决：**accepted / 未修复 / P2**，保留原登记 `docs/gateflow/upload-material-unified-s3-readme-input-boundary-finding-20261003.md`。
- 修复仅 README 文案：工作区外限制属于管理员 config/taxonomy/manifest；用户原件按上传合同进入请求独占只读副本。不得为了文案新增产品原件路径限制。
- Destination：与 US3-R01 及本轮其他成立 findings 一次集中 fix。

## US3-R02：worker 生命周期缺无外部资源的合同回归

- 裁决：**accepted / 未修复 / P2**。
- 来源：`docs/reviews/code-review-20261003-074930.md` finding 002。
- 语义 owner：Fins worker `_DoclingProcessTarget.__call__` 的 XBRL 单次 dispatch、内容结果分类、export 失败及 finally 释放；修复位于对应 owner tests，不新增生产规则。
- 总控直接核：现有 process 单测 targets 全为 `xbrl_input=None`；外部真实集成在缺 `DAYU_S3_XBRL_RESOURCE` 时 skip。无资源常规回归未断言 XBRL 分支不调用 PDF、failure/errors→execution、export failure→serialization、持有真实转换结果时 unload 恰一次。US3-R01 已实证此缺口能遗漏真实次生失败，故有当前修复动机。
- 最小修复：补 owner 级注入结果的确定性矩阵；明确它只证明 worker 控制流/生命周期，不替代真实 Docling 正例或 CLI 证据。与 R01 的真实缺属性坏内容回归合并设计，避免镜像或重复测试。
- Destination：与 US3-R01/D01 同一次集中 fix、同版双路 re-review；不新 slice。

## ds-flash finding 2：Python 3.11 路径硬编码

- 裁决：**rejected-with-reason（当前 WU 产品缺陷不成立）**。
- 当前已确认验收限定 macOS arm64 / Python 3.11，本机该路径实际存在且运行库已验证；报告亦承认当前平台无实际缺陷。非 3.11 解释器支持不能由 review 扩大既有目标。
- 残余：未来解释器升级时重新验证实际扩展模块布局；owner 为 runtime 平台验证，destination 为后续平台工作。Linux/Windows 实装隔离继续按用户明确裁决延期，不能冒通过。
- MiMo finding 003 是同一未来解释器问题，裁决和去重相同，不采纳其“当前集中 fix 自适应”建议。

## 后续与残余

- 两路均已取得 outer0/result success、canary 匹配并完成完整工具轨迹与冻结 12,123 项零漂移核收，根最终裁决另记。全部 accepted 修复集合为 R01/R02/D01。
- Docling 抽取准确性由上游负责；不新增解析器或准确性门槛。
- 完整 upload_material CLI CI 和正式 oracle/scenario 登记仍在修复 WU final closeout 后独立阶段。

## 后续最终状态（保留以上初轮登记历史）

US3-R01/R02/D01现已修复，经六项同版双复审/root核；US3-T03/T04另外登记的测试迁移亦已修复、同版双复审及最终42并集2841pass/3skip/type0通过。完整裁决/source/验证见 upload-material-unified-s3-final-root-adjudication-20261003.md。没有本S3 accepted未修项。旧未修状态描述初次发现，不作为当前状态。Raw EOF归后续aggregate既批收口；不新slice。
