# macOS 计划原型：总控执行前观察

这是当前 plan-completion 的必要取证约束，不是新增业务目标/产品 slice。脚本仍由 gpt-6-sol 维护；总控尚未执行其 parent probe，不将本观察记为完整结果验收。

## P0-R01：父级探针需符合过程和证据协议

目标：`workspace/tmp/upload-material-macos-plan-completion-sol-20261002-01/sandbox_parent_probe.py` 的当前候选。直接代码已读；子 Agent 的 `sandbox-start.stderr` 是 `sandbox_apply: Operation not permitted`，而总控独立沙箱外启动 /usr/bin/true 成功。这是嵌套执行边界差异，不能说 macOS 机制不存在。

在总控执行前需要同一任务集中补齐：

- 当前 parent 输出固定为 ROOT 下 `parent-*.stdout/.stderr/.json`，重跑会覆盖原票据。应显式接收全新独立 evidence/output 目录，每次执行必须新建；输入脚本/公开 instance/taxonomy 与策略 SHA 在首末冻结。不能改写首次失败以重试绿字替代。
- 当前取消尾部用 `os.killpg(pid, 0)` 宣称 group_gone。$sub-agents 禁止靠 kill-0 类查询裁定生命周期；改用自己启动的受管父/子句柄、实际 wait/退出记录等直接证据。不得用进程列表，不将 parent 等待代替所有 child 清理证明，不改全局信号/外部 Agent。
- 不以 HOME/common script variables 充当任务目录；运行目录和缓存配置使用明确的任务参数及库支持的配置，禁止改全局用户配置。若原型为缓存隔离改变子进程环境，必须说明真实语义/范围，不能将该原型 recipe 直接当产品机制。

裁决：accepted / 未修复，owner gpt-6-sol / 当前 macOS plan-completion；根总控保留外层执行权。输出隔离与生命周期真实性属于既有证据验收的必要条件，不为这些脚本项另建 WU/slice 或逐项微循环。

## 尚未形成业务 finding 的观察

真实 MLAC/GRVE 已由作者取得 Arelle 合法性对照，Docling 第一次路径转换 exit1 仍待作者归因。不得从该失败直接猜上游缺陷，也不得以原型 hook 自身异常造成失败来否定真实转换。给出原始 cause、无 hook 对照/修正后同次采集与准确范围后才裁决。

Dayu 不评判抽取的财务准确性；原型统计只用于依赖、合法输入、taxonomy 引用、受控边界和同次身份核证，不得增加生产端“财务内容量/准确率”阈值。强制边界是否生效应以真实文件/网络访问与控制对照证明，不能只看第三方转换 exit。完整 upload_material CLI CI/registry 仍在修复 WU 后执行。

## P0-R02：父层原型执行首次失败（accepted / 未修复）

总控require_escalated实际执行parent-run-20261002-01，driver exit1。run()对每个argv猜Path并is_file，将sandbox profile长文本当文件名导致ENAMETOOLONG，child已实际执行但其exit尚未持久化。独立stdout/stderr空不能猜child成功；证据根保存root-driver-receipt及首末inputs/policySHA一致。必须先明确哪些argv是路径、运行票据优先保存实际exit，失败也完整留证；owner gpt-6-sol，当前集中计划补证，不新增slice。总控将用原策略做有界启动诊断，提供直接childexit，再集中交Sol修正/冻结可实施策略。
