# UM-O20-F02：PR6-F1/F2 P0 计划修订记录

- 日期：2026-09-29。工作区：`/private/tmp/dayu-upload-o20-f02`。本次只修 P0 计划的 §5 P0-B；本记录不是 P0 执行结果、implementation handoff 或 plan gate pass。
- 绑定 goal：`docs/gateflow/upload-material-o20-xbrl-runtime-goal-20260929.md`，SHA-256 `e604d595085a5d03ec52ae705c2b719d4190e01b14b4518a665a55d1ef34d3a5`。
- 冻结 E01：`docs/gateflow/upload-material-o20-e01-evidence-20260929.md`，SHA-256 `f75a0c9b20e8ad152d5d0f24964b11f4baf87ffb8f11a313671fa69b6fe0401c`，未修改。
- 被修计划：`docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md`，修前 SHA-256 `904ec0f2d1a97f8fce0a77d2ae886bb347470b6ea435fe8e4163678bb27adae7`；修后 SHA-256 `720cf5027420e6b1f2badf679179871ee1e30154a6ff26608013027c204f1f99`。
- 依据：MiMo `docs/reviews/plan-review-20260929-135825.md`，SHA-256 `5d5ca92778dcfd61c5b094553d07c7cc60055318c5a658b49220a0817de69edd`，finding 1 与 OQ5；总控 `docs/gateflow/upload-material-o20-xbrl-runtime-plan-review-adjudication-20260929.md` 末节 PR6-F1/F2，SHA-256 `1ebe5a7d24fe2d8297735f9a2dabe7af9898d39916aefef2ad3fc8846fd913aa`。

## 动机与修复映射

两项缺口成立，均为低严重度的证据规格问题。Docling 2.127.0 的控制器日志只列 zip，转换后不外传加载模型；现有 probe 的 `taxonomy_docs` 来自独立 Arelle 检查。旧计划虽要求 Docling Path/Stream 的“实际读取/映射目标”，却没有限定当次采集来源。真实无 typed 样本旧句仅列 Arelle validation 和 Docling 输出，未规定先确认样本合规。修订位于证据产生与验收边界，不在产品下游补偿。

| 裁决项 | §5 P0-B 修订 | 判据与停止出口 |
| --- | --- | --- |
| PR6-F1 | 每条 Docling Path/Stream 记录标明当次进程内加载/映射记录，或绑定该次进程及子进程、时间窗、输入的 OS 文件访问 trace；记录版本、配置、输入哈希及实际引用目标关系。独立 Arelle 重放另列，核对版本、配置、instance 与 taxonomy/package 哈希及差异。 | OS trace 只证明其中可见的文件访问；逐条映射无法由当次证据核对时，该向量该路记 `blocked: run evidence unavailable`。重放或预期布局不得冒充当次记录；不造 hook 或产品代码。 |
| PR6-F2 | 真实无 typed 合规样本先以该 instance、完整 taxonomy、离线配置运行 Arelle `--validate --validationExitCode`，确认 exit 0 且无验证错误，留原始 argv、双流、exit 和验证记录；随后才用同一 instance 跑 Docling Path/Stream。 | 不合规或无合规原始证据的样本不能计正样本，不能凭其 Docling 失败归因产品；两路 Docling 仍服从 PR6-F1 的当次证据规则。 |

## 验证与残余

- 修改前逐字读取 AGENTS.md、goal、E01、计划、MiMo review 和总控末节，核 SHA 后才落笔。修改后按字节复算计划、E01、goal、review、裁决 SHA；E01/goal/review/裁决与修前一致。仅文档改动，无产品代码、测试、依赖或 README 触发；未运行产品测试或 pyright，也未执行 P0、安装依赖、加载 taxonomy、对外发 issue、commit/push/PR/merge 或派发子 Agent。
- 本轮记忆索引 `rg -n 'UM-O20|E01|F1|F2|PR6|Docling|Arelle' /Users/leo/.codex/memories/MEMORY.md` 无匹配并返回 exit 1；它不是工作区验证结果，其余已完成检查命令 exit 0。
- 当次映射证据的可获取性仍待 P0-B 实测；OS 文件 trace 若不能把某引用与目标关联，须按修订判据 blocked。真实无 typed 合规财报、完整 taxonomy、跨平台依赖与强制隔离、真实 CLI/manifest 成功均未取得。双路同最终 SHA 的 plan review 尚未完成，受控 XBRL 产品能力仍 blocked。
