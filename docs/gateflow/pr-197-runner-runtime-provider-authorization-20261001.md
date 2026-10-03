# PR197 runner 派发授权补记

用户最新明确授权：**“授权使用 $sub-agents 派发所有runtime和所有provider”**。该授权适用于既有任务内的 runner 子进程派发，后续不重复询问 runtime/provider 派发权限。

已有具体分工与选择继续有效：gpt-6-sol 负责 plan / implement / fix；MiMo/Kimi 同时独立审查，Kimi 真实额度失败时 ds-flash 备份；root 总控核查结构化结果和实际证据，自行裁决。用户对 Sol 连续服务路由超时的具体选择是保留 gpt-6-sol、等待恢复；泛化派发授权不自动改写这一实现路由选择。

所有调用仍显式使用 `/Users/leo/workspace/dayu-agent-r`，唯一开发分支 `codex/upload-material-oracle`，独立 output/stderr、唯一标识和新路径、no-persist/canary/首末冻结身份。授权不扩大业务范围，不豁免 Gateflow，不批准 merge、main 开发、新工作树，也不允许绕过工具自动权限审核。前两次 ds-flash 派发因审核 deadline 超时，均未启动 Agent；用户另明确授权再试一次，第三次托管句柄43581已成功启动。

本补记是授权记录，不是源码实现、审查通过或最终 CI 验收。
