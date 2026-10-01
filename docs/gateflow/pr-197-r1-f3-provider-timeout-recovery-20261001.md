# F3 输入路径修复派发：服务超时及唯一恢复性重试

`codex/gpt-6-sol/pr197-f3-s1-input-loop-fix-sol-20261001-01` 托管1929 outer exit1，runner表示没有生成常规最终消息文件。14条合法JSONL无turn.completed、末条turn.failed；错误为 **workspace routing discovery timed out**，WebSockets→HTTPS切换未恢复。stderr另有模型列表刷新timeout及MCP transport closed。没有 command_execution/mcp_tool_call、没有产品读写；root重算39当前+39原件全部匹配，源码零改变。

```yaml
setup_status: ok
agent_status: failed
tool_evidence: no
tool_trace: missing
required_evidence: missing
canary_status: not_run
result_status: rejected
warnings: []
evidence_gaps:
  - service routing timeout before task tools and final response
retry_class: provider
```

全量输出/stderr在 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.dWOtEM/`，前缀为旧label。JSONL第3–6、8–13行error及第7行item_0 error、第14行turn.failed均为此未恢复服务连接问题，不套metadata warning豁免。不是已证实额度/模型capacity问题，也不是本地绝对workspace不存在；actual model unknown，不能靠路由标签推断。

按Sub Agents协议只允许一次有原因的同provider恢复性重试：新label `pr197-f3-s1-input-loop-fix-sol-20261001-02`，全新run/output/stderr/last-message/随机读取凭据；冻结原件复制至新独占目录，旧失败字节保全，不抹原评分/诊断。仍由gpt-6-sol执行同一已裁F3-CR1-A1，source范围不扩大；未切provider、未默认换实现模型。若再次失败，再按已授权路由边界报告原因并继续可独立任务，禁止无限重试。

当前重试尚未启动，不能填写成功。F4双路readonly继续，本失败不使它们无效，也不证明F3修复或CI通过。

## 新-02 终态（历史上段不改写）

新label托管4394已outer exit1，同样没有最终消息文件；完整JSONL末条turn.failed，workspace routing discovery timed out，stderr模型列表刷新timeout与MCP transport closed。没有工具执行；root复算39current+39originals全匹配，未改变源码。

```yaml
setup_status: ok
agent_status: failed
tool_evidence: no
tool_trace: missing
required_evidence: missing
canary_status: not_run
result_status: rejected
warnings: []
evidence_gaps:
  - repeated service routing timeout before task tools and final response
retry_class: provider
```

旧失败和新失败均保全。新output/stderr在 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.C7dOcO/`，唯一前缀-02。唯一同provider恢复性重试已用完，不继续重派。用户明确指定Sol负责实现，Kimi额度不足才ds备份的授权不涵盖将实现角色改为ds；已异步请求用户选择保留Sol等待恢复或明确允许ds临时负责plan/implement/fix。此时当前F3 fix受服务与路由选择阻塞，不因源代码未变丢掉已裁finding。F4只读双审继续；F6计划审查可独立推进，不停止整项任务。

用户已明确选择 **保留gpt-6-sol，等待服务恢复**。路由问题已回答，不再写pending，也不切ds或其它模型执行实现。两个失败仍保全，当前实施受服务阻塞；恢复需实际可用信号，不凭时间流逝声称恢复或无限派相同失败任务。独立审查继续。
