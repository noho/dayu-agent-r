# macOS XBRL 计划补证：总控核收

## 范围与身份

统一修复 WU 的 plan completion，非产品实现、review 或 accepted plan。workspace `/Users/leo/workspace/dayu-agent-r`，branch `codex/upload-material-oracle`；HEAD `619d092ab4278645203c7ebe08515f7697d92b71`，main `fac32ecbff9bfe792b63ee9667c8697826b631f4`。

```yaml
setup_status: ok
agent_status: blocked
tool_evidence: yes
tool_trace: complete
required_evidence: partial
canary_status: match
result_status: partial
warnings:
  - 公开下载定位、合法性布局、profiler与原型类型错误均保留并恢复，见下文
  - websocket TLS diagnostic后取得turn.completed与外层exit0，不认定provider任务失败
evidence_gaps:
  - 父层必要强制策略/继承与边界核证尚未成立，整份计划generation-ready=false
retry_class: task
```

runtime Codex / provider gpt-6-sol / actual model unknown；label `upload-material-macos-plan-completion-sol-20261002-01`。managed session23463 已收外层 exit0，172 条 JSONL，最后 turn.completed，78 次完成命令；实际 item_1 工具读取与 final 身份比对一致。子任务按停止条件交父层执行，记录 blocked，不能因进程 exit0 写 accepted。

stream/stderr/last-message：临时 run 根 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.EhyhWU/` 中本 label 三份独立输出；完整私有核收在 `workspace/tmp/upload-material-unified-repair-20261002/macos-completion-root-receipt.json`。公开有界票据 `evidence/upload-material-unified-repair-20261002/macos-completion-root-receipt.json`。不把完整工具输出或许可限制输入写入 PR。

## 总控实际独立核验

- 交付清单所有声明文件 SHA 匹配；886 件受保护源码/测试/README/依赖/控制与准备报告首末 SHA 无变化。S1/S2 保留原计划，产品未实现、未 commit/push。
- pip check exit0；缓存权限 warning 导致禁用 pip cache，不是依赖失败。完整候选安装、锁回读仅支持设计组合可行，不冒最终产品标准安装。
- Arelle MLAC 离线 closure validation XML 只有 info，无 error/warning。真实 instance 与 source/hash 已冻结。
- v4 Path/Stream 都为 SUCCESS/errors=[]，输入 SHA `04a015790c25d5a5371117bc64100335e65bfe1b3acdb71b4f2240c97e09cdf1`，两个实际 document SHA 同为 `c81acb63752a68a342cb1e1e6f01483e9f10f784720fd7c413d2e55d4445d95c`；每次 2211 load call、32 ZIP read call及普通值快照。原 unload 一次后 closed=true，profiler 恢复，原方法身份不变。
- SimplePipeline 的原 _unload 是 no-op；本次 P0 显式卸载不能冒实际生产生命周期已实现。函数调用票据不等于 OS 全访问 trace，不增加财务内容量或准确率门槛。
- 首次父层执行的 inputs/policy 首末 SHA 一致；driver exit1 和三独立启动对照 exit -6 原样保全。原策略未通过，不能将转换成功外推为强制边界通过。

## 非零事件与恢复

- item_8：zsh URL 未引号 glob exit1；后续精确引号获取恢复。两次 tree payload/receipt 命名碰撞由独立 refetch 恢复，首轮原 body 缺失如实列局限，不补造。
- item_28：MLAC XSD 不同目录 validation exit3；相同 instance bytes 修布局后 closure exit0/XML 无 error/warning。
- item_33、item_47：probe profiler 错把 ZipExtFile.read 当 ZipFile.read，造成自身 KeyError 后干扰转换；保原脚本、diagnostic、非零票据。无 hook 及精确函数身份的 v4 两路恢复。归原型错误，不向上游误报。
- item_59：原型 metadata 路径类型错误 exit1，明确 str(path) 后恢复。
- item_75：取消 handler 的 FrameType 签名错误 exit1，补准确签名后恢复；最终显式 include 原型文件的 pyright exit0。早期被根 exclude 排除的零结果不作为覆盖证明。
- wrapper 保存的 sandbox-start exit71 是嵌套 sandbox_apply Operation not permitted；不重复同调用，不认为 macOS 无机制。
- 父层 P0-R02：长 profile 被 Path.is_file 当文件名导致 ENAMETOOLONG，未持久化实际首个 child exit。driver 原双流/首末 hash 保存，不能把空双流猜成功。
- 随后总控用同策略在新 `root-startup-diagnosis-01` 分别核 native true / sandbox-exec Python / direct sandbox_init Python，实际 child 都 -6、双流空；仅认定该策略不可用，根因仍需直接核证。

## 裁决与下一入口

部分采纳依赖/真实 positive/同次函数调用取证及具体设计候选；不接受整份计划 ready。P0-R01 脚本协议已修改，外层未走到清理验证，最终状态仍部分修复；P0-R02 accepted / 未修复，已即时登记 `upload-material-macos-probe-root-observations-20261002.md`。

下一入口：gpt-6-sol 集中修正一次有界父层 harness、收敛最小 runtime 策略与准确 spawn/import/IPC 边界；总控执行、独立核证后才进入正式 MiMo/ds-flash 同版 planreview。没有 provider retry/switch。Linux/Windows 用户授权延期；typed 分支归既有 Docling #4437；真实生产 CLI/最终标准安装归 S3 实施；完整 CLI campaign/registry 归 WU 后阶段。所有未覆盖 owner/destination 保持原 control，不新增 slice。
