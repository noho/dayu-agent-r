# UM-O16-F01：material action/files 共享前置契约 goal confirmation

- Gate：`goal confirmation pass`；work unit：`UM-O16-F01`；日期：2026-09-28；workspace：`/private/tmp/dayu-upload-o16`，分支 `codex/upload-material-o16`，基线 `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- 用户确认：`docs/reviews/upload-material-um-o16-oracle-adjudication.md` 登记用户接受此修复方向；本轮用户另明确要求按 Gateflow 修复全部清单并把闭环代码放入 PR #197。此前 oracle 文件“不代表产品修复获授权”的历史状态由后续授权取代。本 goal 只收敛已接受的 O16-F01，不扩大到其它身份、状态或格式修复。

## 动机与直接证据

动机成立，严重性是用户输入被迟报为 `unexpected_runtime`，或带文件 delete 成功而忽略传入文件并发布 tombstone；冻结 S13～S17 有有效既有目标前置、CLI 双流与持久化快照，不能以混杂的 UM-053～056 单独归因。当前 HEAD 的 `FinsUploadMaterialFiles.from_upsert_paths(())` 抛普通 `ValueError`；`SecPipeline` 与 `CnPipeline` 的 material delete 分支直接构造 `for_delete()`，绕过原始文件 tuple。`FinsIngestionRuntime.upload()` 与 `start_upload()` 均先调用 `_validate_runtime_upload_request()`；material 分支目前仅调用 `_normalize_upload_request()`，它规范化 action 而没有检查 action/files 组合。CLI `_upload_material_stream()` 对缺失 `--files` 构造空 selection、对带文件 delete 则传文件给 Service；Fins 请求中仍保有原始 tuple。因此共享前置输入边界确实存在，且可在 lifecycle/业务持久化前拒绝。

## 目标与成功信号

在 Fins material 请求的共同 admission owner，对规范化 action 与原始文件 tuple 建立封闭规则：`auto/create/update` 必须至少一文件；`delete` 必须零文件。非法组合产生字段/动作明确、用户可修正的 typed usage failure；direct、job 与非 CLI 入口复用同一事实，在上传开始事件、job record、公司/材料业务持久化之前拒绝。目标缺失等后续状态错误不能遮蔽非法 action/files；合法带文件 upsert 和合法无文件 delete 的既有业务状态与文件事实保持一致。CLI/tool 只投影 owner 的 typed 失败，不各自重算组合；请求摘要、结果与持久化事实不得报告“请求一文件但静默删除”。

实施后用 owner 级单元测试、direct/job/Service 或 tool 消费测试、隔离真实 CLI 补跑 fresh 与已有目标上的四种非法组合和合法基线，核对 exit/双流、事件/记录、公司与 material meta/manifest、文件树以及无残留进程；受影响 pytest、pyright、单文件覆盖率与 README 职责检查按 AGENTS.md 执行。真实 CLI 证据是当前 checkout 的新证据，不改冻结记录。

## 边界与非目标

- 唯一 owner 应在 Fins material 请求规范化/typed selection 的直接上游；具体函数/API 由 plan 在读完整调用链后确定。若 SEC/CN/HK workflow 能被作为独立公开入口绕过该 admission，plan 须给出同源调用方式，不能复制规则或下游 fallback。CLI argparse 的 `--files` 后缺值已由 parser 处理，不写兼容分支。
- 不改变 action 的四个允许值、目标存在性（UM-O14/O15）、身份/日期/form/name、文件格式能力、Docling 转换、删除 tombstone 本身、仓储 schema/发布协议。错误具体措辞与尚未补跑的 exit code 不从冻结事故倒推；typed usage 通过既有 CLI 投影确定可用输出。
- 不把 UM-O13/O14/O15、O07/O09 或其它 upload 修复混入本 work unit。未确认的 pipeline 直接调用可达性、错误投影路径与必要测试落点由 plan 以代码证据解决；若发现需要新的公开 schema、改变既定产品语义或无法确定唯一 owner，停止并重新确认目标。
- PR #197 仅在本 work unit 全 gate 闭环后汇入；用户手工 merge。无外部 issue 评论授权。

当前/下一 gate：`plan`；由 gpt-6-sol 形成可直接实施的最小 plan，再由 Kimi/MiMo 两路 plan review、总控裁决。
