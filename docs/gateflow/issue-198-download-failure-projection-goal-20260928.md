# Gateflow goal confirmation：issue #198 download 失败投影与诊断

日期：2026-09-28。Gate：**goal confirmation pass**；下一个 gate：**plan**。目标 PR：现有 draft PR #197；用户明确所有闭环代码进入该 PR，merge 由用户手工完成。当前分支 `codex/upload-material-oracle`，HEAD `97a8eec8`。本文件仅确定本 work unit 边界；当前工作树原有改动尚未经 plan/review 接受。

## 目标、动机与成功信号

目标：修复 issue #198 的两条同源失败链：一是 `SourceIntegrityPreflightError` 的封闭原因在 Fins download public failure、direct terminal 与 CLI 中保真投影为可行动的 storage 拒绝；二是真正未知的 direct download 异常在 operator 日志中留下**脱敏的异常类型与调用栈**，让 CLI 的查看日志提示有实际对应记录。用户可见文本和日志均不得泄漏 URL、token、用户路径或异常原文中的秘密。

动机成立的直接证据：issue #198 记录真实 CNInfo 下载曾把 storage `unsafe_publication` 显示为 `execution / 下载执行失败` 且无诊断日志；当前 `dayu/fins/ingestion_runtime.py:_run_direct_stream_producer` 捕获 `Exception` 后直接生成 RESULT，没有日志调用。当前工作树已在 `_download_public_failure_from_exception` 增加 `SourceIntegrityPreflightError` 分支、在 `FinsPublicFailure` 增加 `reason_code` 并投影到 CLI，但这些是未经本 Gateflow 验证的未提交改动，不能视为已闭环。

成功信号：storage owner 的封闭 reason 经 Fins public failure/summary/CLI 保持一致、提示可操作且不建议盲目重试；未知异常仍保持安全的 generic public failure，但有脱敏且可定位的 operator 诊断；owner 级测试、受影响测试及 pyright 通过，并以隔离工作区真实 CLI 检查 typed 失败。对未知异常的测试须证明敏感异常文本不进入公开流或日志。

## 非目标与 scope boundary

- 不改变 storage 对哪些来源条目可信的判定；当前未提交的点号元数据忽略逻辑及其测试属于另一个 work unit，虽然最终也进入 PR #197。
- 不为 CNInfo 协议响应另建响应内容日志，不做 upload_material 修复、仓储 schema 迁移或旧接口兼容。
- 不把任意 `OSError` 或未知异常猜成 source integrity 原因；public reason 只能由对应 typed owner 提供。
- 不把 raw traceback/exception 字符串直接打印给 CLI/LLM 或写入不受控日志；日志诊断要满足实际脱敏证明。

## Owner 与执行边界

`dayu.fins.storage` 拥有完整性预检原因；download public failure owner 在 Fins runtime/typed contract 统一投影其封闭原因；CLI 只渲染 public failure。direct producer 的异常捕获位置负责生成 operator 诊断，但不得把下游展示层变成分类真源。现有未提交改动中，与本 work unit 相关的候选文件为 `dayu/fins/ingestion_runtime.py`、`dayu/fins/direct_events.py`、`dayu/cli/output.py`、相应测试与读者相关 README；storage inspector 的点号元数据改动、其它校准文档和已有不相关工作均不可混入本 work unit checkpoint。

最小方案只解决 issue #198 的 typed reason 和未知异常日志，不引入通用异常注册框架、第二套存储完整性状态机或跨命令补偿。代码、测试和文档由 plan gate 给出精确文件及验证命令；plan/review/implement/fix 派发依用户要求由 gpt-6-sol 执行，Kimi/MiMo 两路 review 并行，总控逐项检查结构化结果后裁决。

## Gate 状态与风险

Goal confirmation 由用户明确请求修复清单与 issue #198、指定 Gateflow 和 PR #197，并进一步确认全部闭环代码进入该 PR 且本人手工 merge。当前无影响此 work unit 目标的未回答问题。风险：工作树同时含独立 storage inspector 修改；每次 commit 必须只 stage 当前 gate 文件/必要 hunk，不能把它们误并为 issue #198。现有 draft PR #197 已打开，用户指定复用；到 PR gate 时须在该 PR 更新、做新改动的 PR review 并记录 Gateflow 与既有新建 PR 步骤的差异。
