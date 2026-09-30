# Issue #198 S2：未知下载异常的安全诊断 goal confirmation

- 工作区：`/private/tmp/dayu-upload-issue198-s2`，分支 `codex/issue198-s2-diagnostics`，基线 `8d8d494fbbce0052372fb1b42097c9f7222cfa28`；preflight 分支非 trunk、工作树干净。此工作单与 S1 typed 来源完整性失败投影分离，实施须在 S1 已接受集成后进行。
- 用户已经要求 #198 与 upload_material 修复清单完整闭环、纳入现有 PR #197，并按 Gateflow 及 Sol/双路审查推进；issue #198 期望「兜底不得静默」直接覆盖本项。没有对外 issue 评论、merge 或 mark ready 授权。

## 动机和直接证据

动机成立。当前 `dayu/fins/ingestion_runtime.py` 的 `_run_direct_stream_producer` 在 download 异常兜底调用 `_download_public_failure_from_exception`、发 FAILURE RESULT，却没有在这一 catch 中记录异常类别或堆栈；普通未知异常得到 `classification=execution`、`下载执行失败` 和「检查运行日志中的脱敏分类」提示，但该入口没有对应日志。现有 `_save_failed_from_exception` 等后台失败收口会把 `str(exc)` 放入 job message，且个别二次落盘失败用 `exc_info=True` 输出完整原始 traceback；一般 job 路径与 direct 不一致。S1 候选代码解决 typed `SourceIntegrityPreflightError` 投影，但未知异常的诊断仍缺。

## 已确认目标和成功信号

1. 对真正未知的 download 异常，唯一 failure/diagnostic owner 在 direct 与 job 适用路径留下可定位的安全运营日志：异常类型与有界调用栈线索足以找到代码发生点；日志不得复制原始异常消息、provider payload、URL、密钥或用户绝对路径。用户公开 failure 保持可行动且不暗示盲目重试能修复未知错误；公开结果不泄漏原始 traceback。
2. 测试在真实 owner 控制流中注入含秘密标记、绝对路径和 URL 的异常，断言运营日志有安全类别/栈线索且这些敏感字节不出现；direct 与后台终态仍可被读取，typed S1 分支不被当成未知异常。验证不会把日志本身当成 source/storage 真源，也不从 traceback 反推出已发布结果。
3. 受影响测试、逐改动生产文件 coverage >=80%、Python 3.11 环境中的 pyright、对应 README 触发判定与真实 CLI/入口诊断证据均达到项目门禁。形成双路 plan/code/deepreview/PR review、裁决和 closeout artifact，集成 PR #197，由用户合并。

## 非目标和边界

- 不重设计 #198 S1 typed 原因映射、storage 发布确定性、其它来源下载守恒、无来源 retry hint，亦不借日志修正 durable summary。
- 不把 raw exception text、完整未脱敏 traceback、provider 响应或物理路径放进 CLI、UI、tool、LLM-facing、trace、job durable message；不做全局日志框架或跨上传/处理操作的泛化重构。非 download 路径的旧诊断面可登记独立风险。
- 不做 issue 评论或手工合并；PR #197 保持 draft，集成顺序遵循 S1 接受提交之后。

## Owner 与开放条件

download runtime 异常收口产生「未知失败」的运营诊断；其 public failure 与 job 终态须从同一封闭失败分类投影，storage/source typed reason 仍由原 owner 提供。plan 必须实读 direct、后台 job 和日志初始化路径，判定最小共同入口与可执行脱敏方式，禁止在 CLI/UI/测试 fake 中补偿。若无法证明日志不泄漏敏感值，或需要改变公开 failure/schema/job 持久状态的语义，先停在 plan review 交总控裁决。S1 尚未接受集成是 implementation 的硬依赖，plan 可先做。
