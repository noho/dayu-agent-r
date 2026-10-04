# 统一修复 WU：aggregate findings 登记

## 当前身份与 gate

唯一开发 workspace `/Users/leo/workspace/dayu-agent-r`，分支 `codex/upload-material-oracle`。
冻结 HEAD `ec54351e58e66cd5d00b009c862589b109064ade`；selected base `619d092ab4278645203c7ebe08515f7697d92b71`。
三个 accepted slices 已完成；两路原审与集中fix外层均已结束并被总控核收，当前aggregate双复审/总控已通过，下一accepteddeepreviewcheckpoint。
本登记是总控治理文件，不宣称 aggregate pass。四项已一次集中 gpt-6-sol fix；671tests/type0/Raw无损核收，不新增slice。最终状态已由同版双复审与总控验证回写。

## Findings

| ID | 来源 | 总控裁决 | 修复状态 | owner / 边界与验收 |
| --- | --- | --- | --- | --- |
| UA-R01 | DS 报告 finding 1 | accepted，低 | 已修复（同版双复审+总控验证） | CLI 命令归属投影。`commands/fins.py` 捕获 shared `FinsUploadPrevalidationError` 时日志和 stderr 硬编码 upload_filing；材料准入确实会抛出该类型。改为实际命令名，不修改 typed failure owner/message/exit。补材料损坏目标 CLI 反例，保 filing 前缀及零生命周期写入断言。 |
| UA-R02 | DS 报告 finding 2 | accepted，低 | 已修复（同版双复审+总控验证） | `ingestion_runtime.py` 未使用的私有旧失败常量；全源码只有定义，no-runner 已由共享失败 owner 产生并持久化。移除废弃定义，不恢复旧消息，不改变任何运行时语义。与集中 fix 的受影响 runtime tests/type 合并验证。 |
| UA-R03 | DS 报告 finding 3 | accepted，低 | 已修复（同版双复审+总控验证） | 测试隔离 owner。缺身份测试把历史 Agent 目录写进 state repository root。当前 constructor 默认不创建目录，缺身份在状态读取前拒绝，未造成现存产品 I/O。仅用 tmp_path 取代历史目录，完整保留错误 code/早拒绝断言；不得据此重排产品校验或新增 fallback。 |
| UA-E01 | 已批准 Raw EOF 收口项 | accepted | 已修复（同版双复审+总控验证） | 历史证据 owner。原 final-pyright.log 191 bytes / SHA 70a0f3577f8953319fd286c94822becc2dd8c6ec2ba6d76e8bc67172b4e12691 无损包装为 base64 carrier，原 log 变明确非原 stdout 的 ASCII 引导。同步 change_manifest files[21]、validation pyright/log、change_manifest files[24] 的 validation 新 size/hash。保留其他历史 facts，解码逐字节等于原件，全 PR diff-check 0。 |

总控直接证据：`commands/fins.py:209–212`、`service_runtime.py:106–112`、`ingestion_runtime.py:1485–1486`；常量定义 701 行及全库引用搜索；缺身份测试完整实现及 `FsMaterialUploadStateRepository.__init__` 的 create_directories=False。
DS source report：`docs/reviews/code-review-20261003-101044.md`，SHA e4d87c72c879f82feba67f3f537f38e844559872f17406f93095650156520398。
DS/MiMo外层actual0及完整轨迹均已root核；原实际覆盖缺口登记并由本轮复审补证，不能沿用两报告自述全覆盖。

## Residual 分类

- Raw EOF：fixed in current slice；已无损实施并经双复审与总控核验闭合。
- Linux/Windows 部署边界：assigned to later work unit；用户已授权延期，owner Documents runtime / 平台部署。
- Docling抽取问题：tracked by existing issue Docling #4437，owner Docling上游；第三方版本升级/private backend维护：assigned to later work unit，owner Documents依赖维护者，当前不扩大职责。
- 完整 upload_material CLI CI / oracle 和 scenario：assigned to later work unit；用户明确为修复 WU 后独立阶段，本总控继续执行，尚未开始。
- 必要 begin_batch 拷贝、每次 otool 闭包：既定 owner 机制，当前无实测性能缺陷；未来有真实规模压力时 assigned to later work unit，owner Fins storage / Documents runtime，不改当前授权边界。
- C 级 list.append 绕过只读快照：不属于当前无对抗同进程模型；assigned to later work unit，owner immutable storage contract，仅有新的实际需求时评估，不新增序列化框架。
- 缺公司早返回 MISSING：已决 published-state 准入与登记/最终 guard 共同约束，不是未分类缺陷，不重新裁决。

## 下一入口

两路全部终态/真实scope/工具失败均root核收，四项全部已修复；aggregate pass见 `upload-material-unified-aggregate-final-root-adjudication-20261003.md`。下一accepteddeepreviewcheckpoint→普通push已有draft197→正式PRreview。不是WUcloseout/CLIpass。
