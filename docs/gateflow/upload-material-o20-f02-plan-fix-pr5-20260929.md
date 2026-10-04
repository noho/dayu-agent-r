# UM-O20-F02：PR5-F1/F2 P0 计划修订记录

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol-abdaeba1
CANARY=gpt-6-sol-abdaeba1

- 工作区：`/private/tmp/dayu-upload-o20-f02`。绑定且未修改的 goal `docs/gateflow/upload-material-o20-xbrl-runtime-goal-20260929.md`，SHA-256 `e604d595085a5d03ec52ae705c2b719d4190e01b14b4518a665a55d1ef34d3a5`。
- 冻结且未修改的 E01 `docs/gateflow/upload-material-o20-e01-evidence-20260929.md`，SHA-256 `f75a0c9b20e8ad152d5d0f24964b11f4baf87ffb8f11a313671fa69b6fe0401c`。指定计划 `docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md` 修订前 SHA-256 `7a496dcc97df5c922e39e0390055ea39ebbd15e45ff1951216a9e5e707d17252`，修订后 SHA-256 `904ec0f2d1a97f8fce0a77d2ae886bb347470b6ea435fe8e4163678bb27adae7`；两份前置 SHA 均在修改前实测匹配。
- 修复依据：MiMo `docs/reviews/plan-review-20260929-133246.md`，SHA-256 `1c07e0e65a6a188f679faaa172798b01736a574e78d15a05b6f7a1060ce053bc`；总控 `docs/gateflow/upload-material-o20-xbrl-runtime-plan-review-adjudication-20260929.md` 末节，SHA-256 `9b52cf8752781b4d781a5852add56645c141fd7589c4afb6db292c341ba72f3d`。既有直接探针 `docs/gateflow/upload-material-o20-f02-probe-20260929.md`，SHA-256 `d87f58d78e005b9ec623d72bc6100b7881b7494fb0c5bd9685643068902c5383`。本轮不重跑探针，不将计划步骤写成已完成结果。

## 动机与修复映射

动机成立且严重性限于 P0 计划规格与未来公开声明。PR5-F1 的根因是②只定义了合法 XSD 中的 `linkbaseRef` 宿主，未定义 Docling 必须读取的 instance 入口及其到 XSD 的路径；MiMo 实读的 Docling `Type.INSTANCE` 检查使“只拿 XSD 当入口”不能验证 catalog 可用性。PR5-F2 的根因是无 typed 真实样本的成功信号尚未约束 capability 声明，可能外推至现版 Docling 已复现崩溃的 typed 输入。修复留在 P0 验收规格和 S1 声明门槛，不在下游加推断或兼容逻辑。

| 裁决项 | 计划 §5 修订 | 验证边界 |
| --- | --- | --- |
| PR5-F1 | ②指定自包含有效 instance 为 Arelle/Docling 共同入口；相对 `schemaRef` 到同根散文件合法 XSD；其 `xs:annotation/xs:appinfo` 中绝对 `linkbaseRef` 经 catalog 到同根顶层 zip 内 linkbase。②与①绝对 `schemaRef` 分开。三个合成输入逐个先 Arelle 离线验证 exit 0 且无错误、留真实入口与映射/加载证据，之后以同一 instance 跑 Docling Path/Stream，记录各路实际入口、逐条引用及映射读取目标、原始双流和时间序。 | 只是后续 P0-B 执行规格；zip/catalog 可用性与②实际转换均未实测。 |
| PR5-F2 | 真实无 typed 合规财报验收须记 instance 的 `schemaRef`、XSD import、`linkbaseRef` 实际形状及解析目标；检查完整原件全部 context 的 `xbrldi:typedMember` 与 Arelle 加载后实际 context 维度值，保存原始证据、范围、版本和哈希。结论只覆盖该 instance 实际使用的 context/维度值及本次引用形状、taxonomy、版本、配置。S1 共享 capability 与 CLI/help/tool 投影不得超过该范围；typed 待 Docling 上游修复并同等合法性、真实上传重测后方可宣称。不能诚实表达时，S1 接口/文案硬停并重新同版双路 plan review。 | 当前没有无 typed 真实合规正样本、真实 CLI/manifest 成功或可公开受控范围的产品接口；这些仍是 blocked，未宣称一般 XBRL 支持。 |

## 验证、残余与停点

- 修改前核对计划和 E01 指定 SHA；修改后重算计划 SHA，并回读 goal/E01 SHA 不变。文本核查涵盖②入口、引用链、逐输入 Arelle→Docling 次序与实际映射记录，以及真实样本的无 typed 证明范围和 S1 公开声明硬停。只修改上述计划 Markdown，新增本记录；未触及代码、测试或 README，产品测试与 pyright 不适用，README 触发未命中。
- 残余：P0-A 三平台实装与 pin、P0-B zip/catalog 和真实正样本、P0-C 文件/网络强制隔离、证据归档回读、Dayu CLI/material manifest 均未完成。typed Docling 缺陷仍由上游 #4437 跟踪；共享 capability 能否表达受控范围须由未来 S1 设计和双路审查验证。两份同仓同盘证据仍有共同失效模式。修订计划仍待相同 SHA 的 Kimi/MiMo 独立复审，不自称 plan pass 或产品能力完成。
- 本轮工具/命令失败披露：首次 `functions.exec` 的 JavaScript 因缺少右括号返回 `SyntaxError: missing ) after argument list`，随即以正确语法重试；一次 `git diff --no-index -- /dev/null <计划>` 返回 exit 1，这是该命令发现文件差异时的退出码，输出已检查，但因计划是 untracked，它显示整文件新增，不能当作仅本次修改的 diff。其余已执行 shell 命令 exit 0；未调用 Goal 工具。
- 本轮未实施 P0、安装依赖、加载 taxonomy、发送外部 issue、commit/push/PR/merge 或派发子 Agent；goal、E01、probe、旧 review/裁决、产品、依赖、锁、测试、README 均未修改。两份指定 artifact 完成后停止。
