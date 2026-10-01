# F3 aggregate 输入冻结：并行 README 边界纠正

## 直接证据与登记

**F3-AG-PV01：低／accepted／已修复候选，等待审查输入重绑定确认。** owner 是 root 的 aggregate 冻结清单生产步骤，属于取证配置问题，不是产品代码缺陷。旧清单沿用 989 项共同输入时，把根 `README.md` 复制为 live readonly；任务正文同时明确 F6 8prod／10tests／3README 在 F3 内容 scope 外，且允许并行 F6 实施。两者存在配置冲突。

root 首次独立校验因 README SHA 不一致 assertion1，未写成“1117 live 通过”。随后逐件定位：**仅 README 改变**，1116 live 与 1117 originals 仍逐件匹配，五 utils 均未漂移。实际 `git diff -- README.md` 只有 F6 下载两种安全 reason／恢复动作及失败摘要守恒的一行用户说明；不触及 F3 开发分析入口、安装或样本定位规则。F6 对 README 的修改属于已批准写入白名单，不能回滚、覆盖或归咎给只读 reviewer。

## 同版输入重绑定

旧 freeze／originals／两路原始报告和失败记录保持原字节。新配置在 `workspace/tmp/pr197-f3-aggregate-readme-rebind-20261001/freeze.json`：

- 保留同一个 accepted slice `03e8b9b013a30298ba3055b900368102db05e22c`、同一个 selected base、同五源码 SHA、其它 1116 live input。
- 根 README 以该 accepted slice 的 `git show <OID>:README.md` 取得，SHA 精确匹配旧 freeze 与旧 original，写入独占 `pinned/README.md`，明确 logical path、commit、physical path 和 SHA。
- 新 current／originals 均为 1117 项；current 根／Fins／tests README 是并行 F6 可写内容，不再作为 F3 live readonly 冻结文件。没有重新定义 F3 产品语义、没有接受 F6 未审产品变更。
- root 独立身份与原始失败定位保 `workspace/tmp/pr197-controller-collection-20261001/f3-aggregate-ds-receipt/readme-boundary-identity.json`。新清单是 owner 处输入边界纠正，不改旧清单掩盖失败，不做下游 fallback。

## DS 交付取证核收（暂部分采纳）

DS65682 outer0／77 turns／JSON success／is_error=false，actual modelUsage=`deepseek-flash[1m]`；报告独立 token 与预检一致，stderr 仅精确 unrecognized_model warning。报告 `docs/reviews/code-review-20261001-133956.md` SHA=`7354ca715cf7aef85ab32dd158ceb2522cfd92393ecc7304c2c46ce0bedc3f40` 已完整阅读；root 读取其探针关键 owner／完整 CLI 构造／真实独立流及退出，并独立复跑显式 type：**6 files／0 errors／exit0**。

报告两项统计叙述被 root 驳回并纠正：实际九 CLI 是 **5×exit0、4×exit2**（c9 是合法 positive），不是 4×0／5×2；实际具名 PASS 为 **54**，不是 60+。原报告不改写，不为统计错误新增产品修复。其“执行期 RuntimeError 任意路径均不可能重新分类”也只能采为“不会被输入 resolve／argparse 边界错归”：原 worker 仍按已批准规则折叠分析异常，不能据一句话否定它。54 命名检查和九 CLI 原件确可复核，default whole pyright／旧矩阵未重跑的限制保留。

DS 自己首末 1117 校验原流／exit0 是 README 后续变更前的历史窗口证据，不能声称 root 当前 live1117 不变。新的 snapshot 重绑定必须明确核实；MiMo50118 仍在途，不凭 DS 无 finding 就判 aggregate pass。

下一入口：收 MiMo 终态、核源码和其首末输入范围；验证新冻结的 README snapshot／五源码／其它输入同版性，再总控裁 PV01 最终状态及 aggregate gate。若缺少必要同版意见，派外部 runner 窄复审输入重绑定，保旧失败，不重跑已完成业务裁决。F669038 实施继续；根 README 和当前 F6 候选保持不提交。
