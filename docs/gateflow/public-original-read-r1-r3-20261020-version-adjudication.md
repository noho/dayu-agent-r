# PR206 0.1.5 增量审核裁决

## 当前审核状态

被审HEAD 090eb4f566fd94a57d9b758f5dd67cf30f814141；base f854a6e6ff3e3a1cee24745eaae96148843d6401。MiMo会话50841已实际退出，外层/runtime0/0、success、1322.974396秒，完整final及报告[164952](../reviews/code-review-20261020-164952.md)已读；DS会话9817已实际退出，外层/runtime0/0、success、459.052969秒，完整final及报告[163643](../reviews/code-review-20261020-163643.md)已读。原生unrecognized_model诊断按原日志保留，不改实际退出或代替业务裁决。

## V1：测试版本来源错配

裁决 `accepted / 未修复`，owner为真实CLI provenance测试。本轮新增helper将baseline源码声明当成当前安装distribution版本期望，baseline无独立metadata，却运行于同一.venv；升级后观察0.1.5并不代表baseline代码来自错误来源，源码身份应由既有code_root/producer hashes/download_version核定。current默认metadata查询又可能先命中ignored源码egg-info，不能代表实际安装记录。DS用真实observer/helper/editable backend在不安装的前提下闭合反例。主控独立无安装探针亦观察baseline源码与0.1.5 metadata同时存在，回执workspace/tmp/public-original-read-r1-r3-20261020/version-root-baseline-metadata.json及双通道可取回；此为路径规则验证，不是实际安装成功证据。

根因是主控最小计划对测试owner判断错误（把源码和安装包版本当同一事实），并非原R1–R3问题。实际安装版本验收属于已授权sync后自身环境核对；不能为业务下载测试新增安装验收框架。修复方向采用最小必要职责：移除本次新增错误helper与历史固定包版本断言，保留实际metadata观测（只说明解析所得版本，不代表baseline源码版本或安装成功）；既有源码路径/七个生产owner指纹/download_version断言完整保留。wheel测试继续核发行声明，实际安装包版本留给sync后验证。同步tests README，原实施报告作为历史保留并追加纠正回执。此方向改变错误的内部测试方案，不改变用户目标/安装成功标准，不新增当前安装或业务回归门槛。两路审核收齐后再派writer，避免在途审查对象漂移。

## 非阻塞风险与范围

手工隔离构建输入清单当前已由DS与tracked HEAD全树wheel的484条目逐字节验证，writer亦核478个package文件，当前无缺件直接反例；未来外部构建输入扩展维护属于assigned to later work unit，owner为CLI packaging test维护者，destination后续实际构建配置变更时同步验证，不为假设扩展本增量。安装检查covered by later approved slice，等待portfolio-manager核收增量并明确通知。原S1由Provider/Engine和portfolio-manager安排调用方后续补验，保持既有非阻塞defer。

## 双路收齐后的终裁与修复入口

两路均完成独立版本/构建核验，版本声明与wheel同源无争议。MiMo建议accept，但其residual risk第3项自己明确安装后baseline将解析0.1.5而拒绝0.1.4；不能把本次目标“升级后不误拒正确版本”的已知失败转交后续新增metadata影子机制，且用户没有授权给baseline另建metadata框架。因此不采用MiMo该项非阻塞解释，也不采用其“无ownership drift”的总体结论；保留其真实构建/文件完整性/pyright等有效证据，V1仍accepted/未修复。DS建议的具体metadata扫描框架不是修复必选项；主控选择移除错误的业务测试版本比较，将安装版本核对归还sync owner，保持已授权目标最小方案。该裁决不重开R1–R3，也不要求网络验收。下一gate为fix，完成受影响验证后双路窄复审核销V1。
