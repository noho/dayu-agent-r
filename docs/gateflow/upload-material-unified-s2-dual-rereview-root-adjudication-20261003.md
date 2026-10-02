# S2 集中修复同版双路复审：总控最终裁决

## 身份与核收

HEAD `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`，branch `codex/upload-material-oracle`，main `fac32ecbff9bfe792b63ee9667c8697826b631f4` 未改。MiMo83417、ds-flash2004 均托管真实退出0与result.success，完整逐调用轨迹、stderr、实际读取校验token、关键源码及票据已核。归一证据见 `evidence/upload-material-unified-repair-20261002/s2-dual-rereview-root-receipt.json`。9563冻结文件及60候选/副本首末零漂移；全git diff含control，与冻结SHA一致。

## Findings与状态

| 项目 | 裁决 | 最终状态 | 依据 |
|---|---|---|---|
| US2-R02 原件身份规范序 | accepted | 已修复 | constructor唯一规范；真实D→Fs content/meta/skip、非首primary、三轮production双CLI实证 |
| US2-R03 既有常量真源 | accepted | 已修复 | 唯一既有domain/模块owner复用，无wire变更/反向依赖 |
| US2-R04 公司双读窗口 | accepted | 已修复 | 删独立freshread，仅auto非覆盖None只免源条件；公司/alias严格；writer登记/final完整条件不变；实际修前反例与已有公司真实双CLI |
| create-on-tombstone最小回归 | accepted | 已修复 | 真实executor→storage保持拒，业务零写，无新oracle |
| US2-R04-T01 登记非法值错误合同 | accepted | 未修复 | 新测试要求偶然AttributeError违反AGENTS；直接输入owner定义TypeError，详见即时登记文件 |

## 报告裁决

两报告主修复结论采纳，不因一致免总控复核。DS报告其它工具全0措辞驳回：实际9失败及一次自有辅助TaskStop，均逐项恢复分类；错误company-stage返回未消费措辞驳回，实际company final进入writer条件。MiMo3失败工具+1 compound隐藏路径猜测失败已恢复；其owner级断言概括及AttributeError fail-closed措辞对R04-T01驳回。不存在未恢复必需证据；不能据报告无新finding放行尚未修复的T01。

## 验证与边界

主fix真实2017pass/1skip、fullpyright0、7prod>=80%；此前未变21prod宽验证与自身前驱审查按源码SHA继承。DS另真实定向275pass。真实CLI顺序和已有公司轮0/0且ok/skipped、全业务diff{}；同时轮diffnull无中间snapshot，不能冒零差。Docling成功子PID与gpt实际模型未暴露如实unknown；不是新产品目标。Windows/可选PDF按既有延期；S3和UP-RR-T01归后续批准slice；完整CLI campaign/registry归WU后；Raw可逆封装归aggregate收口。

## 下一入口

fix S2：gpt-6-sol一次完成T01最窄owner输入校验/中文异常文档/owner级回归，完整pyright与实际变更prod覆盖；同版MiMo/ds-flash最窄delta复审，继承不变主fix已核证据，不重做宏矩阵。不新slice、业务规则、公开字段或状态。所有accepted已修并复审后才能S2 checkpoint，随后自动S3。main不动。
