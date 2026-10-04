# F6 临时探针派发 setup 错误与恢复

旧 label `pr197-f6-probe-type-fix-sol-20261001-01` preflight 成功，但总控手抄实际 runner 命令时将 last-message 父目录中的 `jc4x180` 错写为 `jcx180`。runner 在准备目录阶段报 Permission denied / cannot create directory，外层 exit2；没有启动模型，没有 output/stderr/last-message 文件，旧 run_dir 仅存在 prompt 与随机读取凭据。托管外层退出与原目录实读已登记 active-runners.json。

```yaml
setup_status: fail
agent_status: not_started
tool_evidence: no
tool_trace: not_required
required_evidence: not_assessed
canary_status: not_run
result_status: not_assessed
warnings: []
evidence_gaps: []
retry_class: setup
```

这是 **controller setup error**，不计 provider 重试、不代表模型额度失败。旧目录 `sub-agents.vACqsB` 保全，没有重用输出。总控重新生成唯一 `-02` label 的 prompt/输出目录 `sub-agents.1hPDPT`，再次 preflight setup_status=ok；直接使用预检完整 command，显式绝对 workspace、独立 output/stderr/last-message、no-persist，独立 require_escalated 派发。当前托管句柄 31175 在途，不能填写 completed/accepted。

F6-PV01 业务证据修复状态仍以 `pr-197-r1-f6-probe-type-evidence-adjudication-20261001.md` 为准。未改产品源码、仓库类型配置或旧探针证据；不得用后续成功覆盖本次 setup 错误。
