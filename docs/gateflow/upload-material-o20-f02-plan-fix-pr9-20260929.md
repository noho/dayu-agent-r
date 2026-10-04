# UM-O20-F02 PR9-F1：P0 计划原始声明与运行观察边界修订

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-a239e34e

- 工作区：`/private/tmp/dayu-upload-o20-f02`。锁定计划原 SHA-256：`4b4e18a1cf499a05cec293c3afe334aa5afe5c6ba0358ff62a92722a5f8bd545`，写入前 `shasum -a 256` 实测一致；修订后 SHA-256：`9d99f7bdc7bb0feb103bee9f71a7d6097cb10ee0a3a7d782c9fda4b33c58906c`。
- 修订对象仅为 `docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md` 的 P0-B 当次模型证据规格（原第 60、62 行）；本文件是唯一新增 artifact。计划仍为待同版复审的 P0 evidence/probe 规格，不是 P0 pass、implementation handoff 或产品能力声明。

## PR9-F1 直接证据与逐项处置

| 项 | 一手证据（Arelle 2.45.3） | 计划修订 |
| --- | --- | --- |
| 第三集合的 owner 与命名 | `ModelDocument.py:75-80` 的 `load` 按规范化 URI 命中成功/失败缓存后早退；`:139-148` 的失败表按 URI 登记，均非逐元素事件表。`docs/reviews/plan-review-o20-pr8-mimo-20260929.md` finding 1 与总控 PR9-F1 裁决指出原“原始逐引用事件集合”会把静态声明误作执行。 | 改为“原始引用声明清单”，逐条记来源/元素/原始 URI/base/规则和 `attempt_observation=observed|unknown`。只在该次直接事件能与该元素逐项对账时填已观察状态和目标；其余保留候选信息并标 `unknown`。 |
| 重复成功 href 与重复失败 | `ModelDocument.py:1255-1281` 的 `discoverHref` 只在 `doc is not None` 时向 `hrefObjects` 逐元素追加；`:79-80` 的失败缓存早退和 `urlUnloadableDocs` 的 URI key 不能还原重复失败次数。`:1488-1496` 的 `referencesDocument` 按目标合并引用类型，只留首个代表元素。 | 成功 href 仅经同次 `hrefObjects` 对元素才可标 `observed`；失败 href 的静态元素与聚合失败项不能自动逐项标 observed。重复失败缺直接逐事件记录即 `blocked: run evidence unavailable`，聚合摘要不得充当次数或观察真源。 |
| 非 href import/include/schemaLocation | `ModelDocument.py:1065-1105` 的 `importDiscover` 可按 namespace/已加载文档短路，成功只进入聚合 `addDocumentReference`；`:457-469` 的 schemaLocation loader 也未建立通用逐元素事件表。 | 各机制单独列声明并查其同次直接事件；`urlDocs` 命中不等于每个 import/include 都调用 `load`。缺逐边记录的正式向量与 Docling 路径 blocked。新增重复失败 `xs:import` 对与重复失败 `xs:include` 对的小探针，专查缓存/短路与观察缺口。 |
| catalog/zip entry | `FileSource.py:482-492` 明确 `isInArchive(..., checkExistence=False)` 只表示路径映入 archive，不保证 entry 存在；`urlDocs` 的 `filepath` 可保留 archive-entry 形状，却不是具体 entry 读取日志。 | 新增 catalog entry 小探针，分记 catalog 声明、映射形状及同次具体 entry 读取记录。没有逐 entry 运行记录即 blocked；静态 XML、聚合摘要与 OS 对 zip 容器的访问均不得推断 entry 已读。 |

两份同版 PR8 review 都锁定原计划 SHA：Kimi 判断已有 blocked 出口足以交付取证，MiMo 指出“事件”名称仍会误导逐边执行判断。修订采纳后者的具体反例，并保留前者认可的成功目标 `urlDocs`、失败请求 `urlUnloadableDocs`、`referencesDocument` 聚合限度及严格 blocked 出口。`observed` 仅证明该声明有同次直接可对账的尝试/发现事件；具体文件或 zip entry 是否读取另须直接记录。静态 XML 和独立重放仅为声明/辅助证据，不替代当次事件。

## 保持的边界与剩余 blocked

- PR8-F1/F2 的三集合和三条互斥异常采集路径继续存在：pipeline 成功/错误返回 result、`DocumentLoadError` invalid-input result、构造/导入异常无 result；本轮不声称这些路径已正式 P0 实测。
- P0-A 仍需 macOS/Linux/Windows fresh Python 3.11 实装、`pip check` 与证据回读；Linux/Windows runner 未有直接执行证据，生产 pin blocked。P0-C 仍需三平台真实强制文件/网络隔离与 trace，当前 blocked。
- P0-B 的重复失败、非 href import/include/schemaLocation、catalog/zip entry 若无同次逐边或具体 entry 运行记录，均须 `blocked: run evidence unavailable`；新增小探针只是验证采集能力，不能替代正式向量。真实无 typed 合规财报、完整 taxonomy、真实 CLI/manifest 成功仍未证，不缩减正式验收条件。
- 未来公共 capability 及 CLI/help/tool 的声明只可覆盖真实样本和部署条件证实的范围；上游 #4437 仅对应合法 typed 维度在 Docling 导出时的崩溃，不把失验 explicit member 或 taxonomy 问题并入。本轮不发、评、更新 issue。
- owner 不变：Docling/Arelle 负责解析与当次运行事实，Documents runtime 负责产品转换边界与 capability，Fins 负责 workspace/材料提交；本次只修证据计划，不添加下游推断或产品 hook。P0 未执行，所有上述 blocked 状态交后续正式取证与总控裁决。

## 只读核验与命令披露

写前实测计划 SHA 与锁定值一致；已读指定 AGENTS、goal、计划、总控裁决、两份同版 review，并直接核 Arelle 2.45.3 解包源码 `ModelDocument.py` 与 `FileSource.py`。写后以只读 SHA、术语、范围和文件检查验证。此前一次记忆索引 `rg` 无匹配，shell exit 1；这只表示未找到相关记忆条目，未用作项目事实。另一次工具编排 JavaScript 语法错误未执行任何 shell 命令，随后纠正。除该 `rg` 外，已完成的 shell 命令 exit 0；本段最终验证结果以执行记录为准。
