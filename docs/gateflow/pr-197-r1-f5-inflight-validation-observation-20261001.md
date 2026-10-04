# F5 在途验证观察（root）

时间：2026-10-01T22:04:23.718995+08:00。唯一产品 writer Sol97574 仍在实施；本记录不接受代码，不重开计划或新增业务要求。

## F5-IV01：官方 Raw 回归的可移交输入边界

- 状态：needs-more-evidence，当前源码候选仍在写；交付后确认是否已由作者闭合。owner 为 tests/官方输入交付，不是业务财期算法。
- root 直接观察：`tests/fins/test_f5_storage_calendar.py` 当前 SHA `db751f311652f19a017bfec5ace2cbc0db3f8f500981fc833fa18340c118e7c9`，`_CAPTURE` 指向 `workspace/tmp/pr197-controller-collection-20261001/f5-official-raw-capture`，该测试无条件读取两份 `.body/.json`。`git check-ignore` 两路径均 exit0，正式提交/新 checkout 不会包含输入。
- 在当前机器跑绿只能证明本机 ignored capture 存在；若最终保持此引用，新 checkout/CI 将在读取时 FileNotFoundError。不能用跳过或补默认数据把 Raw owner 回归变绿。
- 依据：accepted F5 plan §9 官方 Raw 运输/stock-scope/显式Q3回归必须有真实字节与hash，项目要求修改测试可验证。允许最小承载方案为精确原始响应与provenance/hash一起进入正式测试资产（或在正式测试内保留同字节）。原采集/失败证据保持，不新抓取冒充旧Raw、不伪造官方未知反例。
- 原body实际大小年度1446字节/季度658字节，合2104，非大资源依赖；已冻结原hash及官方source envelope。若需要新增fixtures白名单，root在租约结束后集中必要fix一次允许；不能自行绕过旧冻结输入。
- 下一步：97574实际完整交付后核最新测试路径及正式资产；若仍存在，裁为同S1必要fix并纳入集中fix/同版双审；若已闭合，以精确字节/追踪证明关闭，不另开metadata/nit fixloop。

## 当前验证（不是通过票）

中间回归1669passed/3failed；23modified生产文件中间coverage均>=80%；最新owner小组46passed；types-03仍2errors，尚须最终版pytest/fullpyright及source身份核。所有结果均在实施途中，不能代替终态真实交付、review或最终完整CLI CI。

## F5-IV02：CLI 取消分支漏投影已确认/未知下载事实

- root 已直接复核为 accepted／未修复，同一个 F5-S1 必要修复，不是新业务目标。owner=`dayu/cli/output.py` typed terminal 机械投影。
- 最新 owner-06 真实 Fs/实际adapter/observed wait 测试 `test_actual_adapter_observation_wait_and_cli_keep_a_and_unknown[True]`：A确实发布，B未知，取消终态的 typed result.download 与 wait JSON仍保全；CLI `print_fins_direct_event` 却在 CANCELLED 分支只打印通用 `Fins cancelled...` 即 return，未调用 `_print_terminal_business_summary`。stdout 丢失 uncertain=1/source_id=B，直接断言失败（1failed/6passed）。
- accepted plan §7–8/用户binding要求已确认A保全、B单列；取消结果在运行时仍有非零业务事实，CLI只消费现有typed summary，不重算財期。
- 最小修复：在取消print owner机械消费其已有 download typed summary，并保持原cancel提示/exit130/输出通道合同；无download仍原取消行为。更新该真实链回归、CLI取消有/无摘要及无需猜测的字段断言。不要以删除断言或清空typed结果让测试变绿。
- 修复路径暂被用户指定Sol容量失败阻塞；已记录到三controller。可以在固定partial上做只读诊断，不能跳过完整implementation交付或由总控改产品。
