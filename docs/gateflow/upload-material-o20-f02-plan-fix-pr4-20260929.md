# UM-O20-F02：PR4-F1/R1 P0 计划修订记录

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol-2be2f6c6
CANARY=gpt-6-sol-2be2f6c6

- 工作区：`/private/tmp/dayu-upload-o20-f02`。绑定且未修改的 goal：`docs/gateflow/upload-material-o20-xbrl-runtime-goal-20260929.md`，SHA-256 `e604d595085a5d03ec52ae705c2b719d4190e01b14b4518a665a55d1ef34d3a5`；其用户受控 XBRL 支持目标和非目标仍为边界。
- 冻结且未修改的 E01：`docs/gateflow/upload-material-o20-e01-evidence-20260929.md`，SHA-256 `f75a0c9b20e8ad152d5d0f24964b11f4baf87ffb8f11a313671fa69b6fe0401c`。
- 修订对象：`docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md`，修订前 SHA-256 `69307018eea754b523cc81fd1055c0e7e427008276a3977edca0267af61bb7c0`，修订后 SHA-256 `7a496dcc97df5c922e39e0390055ea39ebbd15e45ff1951216a9e5e707d17252`。裁决来源为 `docs/reviews/plan-review-20260929-130919.md` 与 `docs/gateflow/upload-material-o20-xbrl-runtime-plan-review-adjudication-20260929.md` 末节；两者未修改。

## 动机、直接证据与修复映射

动机成立，严重性限于 P0 执行规格：原 §5 的“每个向量”在句法上只覆盖两个绝对入口，混合引用图可能跳过合法性前置门槛；绝对 `linkbaseRef` 未写宿主，可能构造出无效 instance 并误归因给 Docling/catalog。仓库 `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.xsd:17-22` 直接显示 `link:linkbaseRef` 位于 `xs:annotation/xs:appinfo`；已存 Arelle `ModelDocument.py:1020-1025` 对错位元素报 `xbrl.5.1.2.linkbaseRefLocation`。因此明确合法 XSD 宿主与逐输入门槛，不扩大产品设计。

| 裁决项 | 计划修订位置与内容 | 验证边界 |
| --- | --- | --- |
| PR4-F1 | §5 P0-B 明指混合引用图、绝对 `schemaRef`、绝对 `linkbaseRef` 三个合成输入**各自**先经 Arelle 离线 package 加载、`--validate --validationExitCode` exit 0 且无验证错误，留原始 argv/双流/exit/验证记录后才分别运行 Docling Path/Stream；逐份保留 Arelle 在前、Docling 在后的时间序原始证据。②绝对 `linkbaseRef` 放合法 XSD 的 `xs:annotation/xs:appinfo`，不放 instance。任一输入未过合法性门槛先修合成样本，不据其 Docling 输出判组合布局或产品能力。 | 只定后续 P0-B 步骤，未安装依赖、加载 taxonomy 或运行探针。 |
| PR4-R1 | §5 P0 证据归档清单须写主仓 `workspace/evidence/upload-material-o20-f02/` 与 `output/evidence-backup/upload-material-o20-f02/` 同仓同盘；整仓删除、`git clean -fdx`、磁盘故障会共同毁损。两份只验证独立于 `/private/tmp` 和不同清理目录下的定向清理，不宣称独立灾备；若要抗整仓失效，管理员指定仓外持久第二落点再复审。 | 未建立主档/第二份，也未声称真实重启回读。受限原件仍只归管理员受控归档。 |

## 验证与残余

- 修改前两份指定 SHA 与用户给定值一致；修改后重算计划 SHA 如上，E01、goal、review 和裁决的 SHA 均未变化。文本核查覆盖三输入逐份门槛、合法 XSD 宿主、时间序证据、同仓同盘共同失效与非灾备口径。
- 本次仅改计划 Markdown 并新增本记录；没有代码修改，受影响产品测试与 pyright 不适用，README 触发未命中。未执行 P0-A/B/C，未安装依赖、加载 taxonomy、发外部 issue、commit/push/PR/merge 或派发子 Agent。
- 残余：三份合成输入的 Arelle/Docling 实跑、zip+catalog 可用性、P0 证据迁移与回读、真实重启抽查、三平台依赖及强制隔离、真实有效财报 CLI 成功均未证。主仓两份仍有共同失效；S1 的受信根/workspace 边界与 provenance owner 接口仍按原计划硬停，Docling #4437 仍是上游跟踪，用户受控支持目标未变。下一 gate 仍为同一最终 SHA 的 Kimi/MiMo plan review；本记录不自称 plan pass 或产品能力完成。
- 失败命令：本次 shell 探索、编辑和核验命令无非零退出。辅助 `get_goal` 工具返回原文 `Goal tools require a persistent thread.`；故绑定以已确认 goal artifact 的原文与 SHA 为准，未修改 goal。
