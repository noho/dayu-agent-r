# US3-E01：CLI 退出码误归属于转换 worker

## 直接证据与裁决

`workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/production_acceptance.py` 的 execute 先从独占 CLI Popen.child.wait 得到 code，receipt.pid 为 CLI PID。随后 actual-child.json 用 profile.pid 替换 pid，并仍写 exit=code；这不能证明同一 worker 的实际 wait/exit，尤其取消时 CLI130 不等于 worker 的进程终态。root 已读完整产生路径，而非从输出摘要推断。

成立的验收证据缺陷，不是新增业务目标或产品行为修复。owner 是本轮临时技术采集器；CLI actual_wait/exit 保持原义，worker 实际等待/退出必须从现有 InterruptibleProcessHandle 公共结果同源观察，或准确记 unknown 并标明依赖证据缺口；不能把 CLI receipt.pid 换成 worker PID 形成伪同一生命周期。可在独占 collector 观察真实 public wait 结果，保原返回/异常/策略不改变；不新增生产遥测、IPC状态机或借私有进程查询猜终态。

现有所有失败/成功原票据不覆盖。旧 loader verdict 中使用 CLI wait 的边界需如实注明；worker loader PID/profile绑定保持有效，但 child lifecycle 不得冒通过。取消的现有 public terminal/cleanup 证据同源核真实 wait/join，不从父 exit130推出子 exit。

- 状态：accepted，未修复，S3 验收前须闭合；分类 fixed in current slice 的 required fix。
- 原采集器 source SHA：fcb68337a75392ee44e6c8d2a7d1a9b268336a844f965a626ef84247560b9b2d
- scope：implementation S3；不修改已接受计划/用户裁决，不新slice，不提前正式PRreview。
