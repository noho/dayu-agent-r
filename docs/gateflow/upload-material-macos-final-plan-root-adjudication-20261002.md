# macOS 最终计划收尾总控核收

Gate：plan completion，尚未进入正式 plan review。唯一分支 `codex/upload-material-oracle`，HEAD `619d092ab4278645203c7ebe08515f7697d92b71`。

## 已结束派发

`codex/gpt-6-sol`，label `upload-material-macos-final-plan-sol-20261002-01`；托管 session 18876 返回 outer exit 0，完整 JSONL 108 events、明确 turn.completed。独立 output / stderr / last-message 在该轮 run_dir；全部逐调用审计及非零原件在 `workspace/tmp/upload-material-macos-final-plan-sol-20261002-01/root-runner-audit.json`。实际工具读取与最终消息的本轮校验值均匹配，stderr 空，实际模型未暴露，记 unknown。

15 artifact 和 10 input 哈希现场核对；2883 保护项与 15 source 首末逐项核对，S1/S2 不变。定位失败、历史资源原型错误 API、原型类型错误均已保留并由后续同版校验恢复，不是 provider 故障。外层命令正常不能代替内部票据；产品没有实施，不能称完整方案验收通过。

```yaml
setup_status: ok
agent_status: blocked
tool_evidence: yes
tool_trace: complete
required_evidence: partial
canary_status: match
result_status: partial
warnings:
  - 必要定位与原型非零保全，后续恢复；详私有逐调用审计及作者报告
evidence_gaps:
  - 最终隔离矩阵未通过，计划仍 generation-ready=false
retry_class: task
```

## 父层直接验证与成立修复登记

总控按作者最终精确 argv 执行新 `parent-run-20261002-01`，session 36794 返回 outer exit 1。新 collector 已正常保存实际子进程终态、双流、首末输入与失败清单。startup 和实际文件/网络边界成功；`spawn-queue-boundary` 失败。

受控 spawn child PID 91312 在 apply policy 后已实际拒绝根外文件、穿越和 symlink 读取、原件写入与网络连接。随后 `Queue.put` 的 `_sem.acquire` EPERM；父层收到 Empty 并实际 join child exit 1。总控只读取精确自建 PID 的内核记录，明确 `ipc-posix-sem-wait /mp-tgb50ceh` 被拒。这不是 Docling 缺包或财务抽取错误。

**P0-R08 accepted / 未修复**：现有 multiprocessing Queue 的信号量操作未列入中立运行时策略。与 P0-R03/P0-R07 的工作目录和运行库路径一起集中收尾，不新增 slice。owner 为层中立运行时强制策略及其直接调用方的既有 IPC 配置；允许现有 IPC 必需权限不能放宽用户私有文件或出站网络。

实际动态库目录只读已由总控 `root-controlled-runtime-library-01` 对照证明真实 Stream 转换成功；最终作者仍只列单文件别名，集中纳入精确依赖目录名单，禁止整个 Homebrew/工作区许可。

P0-R04 按用户最新运行库边界为 rejected-with-reason，历史反例原件保留；禁止恢复资源解析器方案。Linux/Windows 依用户明确授权延期。标准产品安装、真实 CLI→manifest、产品测试与覆盖率属于 S3 实施验收，不再前置为计划阶段重复原型要求。

下一入口：一次集中 gpt-6-sol 修订运行时必要 IPC 与已证目录规则、计划精确契约；总控执行必要同版矩阵并核证后进入 MiMo / ds-flash 同版正式 plan review。完整 CLI CI 与 registry 仍在修复 WU closeout 后。
