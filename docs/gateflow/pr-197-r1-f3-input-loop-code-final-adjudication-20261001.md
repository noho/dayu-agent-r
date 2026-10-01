# PR197 F3-S1 完整候选同版代码复审：总控最终裁决

## 门禁与版本

**code review／re-review：pass。** 下一入口是 accepted slice commit，然后 aggregate deepreview；不是 F3 整项 closeout，也不是最终真实 CLI CI。

唯一工作树 `/Users/leo/workspace/dayu-agent-r`，分支 `codex/upload-material-oracle`。五源码身份仍与 `workspace/tmp/pr197-f3-input-loop-rereview-20261001/freeze.json` 一致；root 独立重算 989 current + 989 originals 共 1978 次 SHA 比较，零缺失、零不一致。非冻结文档 checkpoint 已推进至 `b6fb33f7`；F6 的未提交并行实施不属于本次 F3 scope。

Binding：739 行 accepted plan SHA `2983efa4326cc799565fab27a350d79bf74b40d540beb0143b4dfa90f181a421`、既有 amendment 裁决及输入环 finding；完整候选含五 utils 从原 F3 基线开始的所有变化，不仅审 RuntimeError 小增量。

## 两路交付与总控直接核验

1. MiMo session7898 **outer0**，Claude JSON success／is_error=false／109 turns，实际 modelUsage=`mimo-v2.6-pro[1m]`；canary 原件、结果和报告逐字匹配，stderr 仅精确 `[claude-code:unrecognized_model]` warning。报告 `docs/reviews/code-review-20261001-131651.md` SHA `57a5207fcc4accdc3140e7a8930f08fe0590ba40b2ec2a0db8abcf4e875a004f` 已完整阅读。
2. DS session55704 outer0／121 turns，实际 modelUsage=`deepseek-flash[1m]`，完整报告及取证限制已登记 `pr-197-r1-f3-input-loop-rereview-adjudication-20261001.md`。Kimi quota 原失败及 DS 备份依据保留。DS 交付部分采纳，不因其汇总结构宣称所有中间执行成功。
3. root 读取实际共享解析／身份 owner、四 main 的参数输入到完整预检、缓存／executor／写址消费链和 C01 producer 检查；交叉核验旧完整 Sol 验收（1098 断言／287 真实模块 CLI、default pyright783 files0、temporary11 files0），以及本轮独立 reviewer 的具体探针和失败恢复。没有按两票一致裁决。
4. MiMo 新临时脚本 `review_probe.py`、guard 和冻结核验脚本均实际读取；root 逐件比对 42 条命令记录与各自 stdout／stderr／exit 原件：14×exit0、28×exit2，28 条负例 analysis/conversion guard 激活且无 sentinel、无 Traceback、stdout 空，231 条具名断言记录可核。matrix 构造真实相对双向链接环、完整文件物理快照及原因链／执行期 RuntimeError 原实例断言。仅合成离线输入，不冒称真实 Docling CI。
5. 本轮临时显式类型结果 3 files／0 errors；root 激活项目 venv 后独立再跑同配置仍 3 files／0 errors／exit0。总控记录和独立 type 双流／exit 在 `workspace/tmp/pr197-controller-collection-20261001/f3-code-rereview-receipt/`。

## Findings 最终状态

| Finding | 裁决／状态 | Owner 与修复证据 |
| --- | --- | --- |
| C01 固定 digest 汇总覆盖 | accepted／已修复 | digest producer 私有保留名检查，公共实际身份判据复用；已存在 hardlink／别名及 fresh ASCII 保留名执行前拒绝，非 digest 入口不误伤 |
| C02 跨记录产物身份碰撞 | accepted／已修复 | 公共 identity 与分组预检唯一真源，四入口写址 helper 贯穿预检／执行／回读；跨记录、跨角色拒绝，同记录角色豁免保留 |
| F3-CR1-A1 输入路径链接环 | accepted／已修复 | 唯一 `resolve_analysis_input_path` 仅此次 resolve 的 RuntimeError→中文具名 ValueError from 原异常；root／manifest／PDF／identity／四 out 全复用，执行期错误不重分类 |
| F3-RR-PV01 临时 JSON 出口弱类型 | accepted／已修复 | 新 tmp 副本 JsonValue 与逐键验证，原件保全、11+11／989+989／DS566 逐件身份及 strict2files0 root 独立核收，详专用 receipt |
| 公共 identity helper 自身必须带双方路径 | rejected-with-reason | in-tree caller 已提供双方记录、PDF、实际目标，具名解析失败与原因链完整；不能把文案偏好升级为新增业务修复 |

没有仍为 accepted／未修复、部分修复或证据失效的本门禁 finding。

## 失败、限制与残余

Claude 两路均为汇总结构，不能逐工具观察全部中间错误；没有为其 probe 外层/type 原命令补造退出文件。root 独立核验各 CLI 实际内层退出及必要身份/type，足以支撑本 gate。MiMo 的 diff `/dev/null` 沙箱拒绝、zsh 分隔符错误、长 s 正例错误预期、临时 list 不变性错误均按报告保留并恢复；root 实读首次矩阵失败 stderr、最终 type 和 fresh 长 s 第三次原流。原有 OMP 环境 warning 与执行器 sysconf 沙箱拒绝不重分类成产品缺陷。

以下沿用既有 accepted plan／此前 code adjudication 的 owner、destination 与范围，不扩大当前目标：

- 尚不存在的 Unicode 文件系统别名：requiring new issue or explicit user decision，owner=分析产物命名／文件系统身份；destination=独立 goal。长 s fresh 覆盖反例此前已有，现新增复现保留，不称已修，不加 Unicode 禁令／casefold／写盘探针。
- 外部运行期换链／并发事务、跨运行缓存来源／失败缓存、schema 历史统计差异、执行后 I/O 回滚：requiring new issue or explicit user decision，owner=各 producer，destination=对应独立 goal；本轮按已批准既有行为保全。
- selected-only 汇总与历史 consumer parity：当前 slice 已披露；consumer 适配需独立裁决，owner=consumer／操作者显式输入。命名清理和既有死代码亦非当前 defect。
- utils 永久测试／coverage 按 AGENTS 豁免；本轮无 README 职责触发。历史公开 locator 处置、真实 OCR／跨平台卷行为／性能语料规模未覆盖，需独立范围授权。
- F4/F5/F6/F7 与全部修复后的完整真实 upload_material CI／oracle／scenarios／readiness：assigned to existing work units／总控最终收口，未以本 matrix 替代。

下一入口：只 stage 五 F3 utils、完整复审报告及本裁决和队列文件，创建 accepted slice commit；随后独立双路 aggregate deepreview 全五文件与既有边界。未审 F6 产品候选保持不提交。最终 PR review 必须绑定届时精确 PR head／base，不沿用本专项结论。
