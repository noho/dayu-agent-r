# S2 当前实施的执行纠偏

## 状态与直接证据

当前 runner `upload-material-unified-s2-final-completion-sol-20261003-01`、HEAD `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`、托管 session 32721 在途；本记录不作 runner 完成或 S2 通过裁决。

总控在完整事件流直接观察 item_36、item_40、item_41 使用 `ps -axo` 查询进程，以及 item_42 对测试 PID 32724 发送 INT。该 PID 在实际轨迹对应本轮 evidence.py 的 owner-01 pytest 子进程；没有据此认定外层 runner 退出。进程列表查询违反 sub-agents 的 Sandbox Process Management，必须纠正：后续不使用 ps/pgrep/kill-0 或全局进程列表。item_39 已开始改为启动即保存 owned PID 的票据，这一方向可继续，但不能抹去旧事件。

## 执行要求

本轮独占测试/CLI 探针子进程仅通过自身 Popen 句柄、启动时保存的 owned-process.json、已知 owned PID 和实际 wait 结果管理；明确 bounded timeout/取消探针需要停止时，按最窄已知 owned 子进程处理并 finally wait/reap，不用全局扫描寻找 PID。外层 runner 仍由 root 托管 session 收集，不得自行猜结束或相互 kill。不能仅因慢而中断或重派 Agent。

owner-01 的失败/中断须完整保留 command/stdout/stderr/exit/JUnit（若中断而无完整 JUnit，明确不完整）。它不能计为整组通过；后续修复后用新 label 的真实测试终态恢复必要证据。后续报告列明上述执行违约、停止原因、已知 owned PID、最终退出和恢复验证；不隐去事件，不把测试中断当成功，也不通过弱化业务断言解挂。

这属于既有执行协议纠偏，不是新业务目标、slice/gate 或新验收。当前 C03/C04 已明确授权；继续集中完成全 S2，按约定读取本 root 新记录。正式审查仍在全 S2 完成后。
