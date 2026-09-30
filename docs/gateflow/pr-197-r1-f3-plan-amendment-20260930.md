RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6
CANARY=gpt-6-sol-ca1c2675

# PR197-R1/F3：C01 plan amendment 与修订证据

## 身份、授权与本轮终态

- label：`pr197-f3-planamend-sol-20260930-01`；runtime 为 Codex，任务 provider 标识 `gpt-6-sol`，模型按本会话提供的 GPT-6 标识记录为 `gpt-6`。首条 commentary 曾误将模型字段写成 gpt-6-sol，已明确更正；canary 不能用来猜模型身份。
- 本轮指定 canary 文件 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.9dmnBf/canary.txt` 已工具实读，exit0，逐字内容见开头。旧轮 canary 只在原件保留，不作为本轮证明。
- cwd：`/Users/leo/workspace/dayu-agent-r`；唯一 branch `codex/upload-material-oracle`。起始 HEAD `60307c15947e2f89457e03126b1251aeb4264c53`；收尾取证 HEAD `b42bbea1e7ccc58561764c20d873214783283eb2`。
- HEAD 增量已只读核对为总控 `gateflow: preserve repair counterexamples and F7 review evidence` 文档 checkpoint：提交既有 F3 implementation/C01 原件及 F4/F7/治理报告；未提交本轮修改的 plan 或五源码。相关冻结 SHA 均不变，符合允许的 checkpoint，不触发全局 HEAD 停止。
- 当前 gate 是 implementation blocked 后的 **plan amendment 文本修复**；两个授权文档完成，候选 **未 accepted**。C01 仍 **accepted／未修复**；implementation 仍 blocked，不把计划或探针当作源码完成、slice/PR pass。
- 读取 AGENTS、Gateflow、binding goal、原 accepted plan、plan-fix、MiMo 215517 / Kimi 215618 报告、implementation artifact、独立 C01 末节、freeze/originals、真实命名 owner 与相关 callers。以用户现成裁决及 C01 总控末节为权威，未改 upload/download 业务裁决；本项是 task 修订，不是 provider retry。

## 精确写入与冻结身份

持久成果仅：

1. `docs/gateflow/pr-197-r1-f3-plan-20260930.md`：C01 增补及当前 gate/停止边界，保留原 S1/A1～A4。
2. `docs/gateflow/pr-197-r1-f3-plan-amendment-20260930.md`：新增本 artifact。

其余写入仅位于 `workspace/tmp/pr197-f3-planamend-sol-20260930-01/`。旧 plan-fix/implementation/C01/reviews/goal/controller/queue/源码/tests/README 没有本 Agent 写入；未 stage/commit/push/PR/comment/merge、新 branch/worktree、派发子 Agent、升级依赖或读取真实用户素材。已有源码候选未回滚或丢弃。

修订前原 plan SHA-256：`a88dcf8e84ba4371b9081714aa736e043b95fea4395d68a5cacf1250130bb172`。

修订后 plan SHA-256：`68c73f081a66a2457667cbe1d3d0b8ea273d98e862970a74f53318b1bcb4fc9f`。

修订前先重新读取原 SHA、匹配八输入 freeze/originals，并保存本轮 `original-plan.md`；既有 `workspace/tmp/pr197-f3-controller-c01-20260930/{originals,freeze.json}` 原样只读。下表首尾均匹配该冻结，当前 plan 本身是获准改动，不用旧 plan SHA 误判自身失败：

| 只读输入 | SHA-256（本轮首尾一致） |
| --- | --- |
| `utils/analysis_sample_inputs.py` | `021e777e263a87d8389741819f933d61bcca0e2f9762d49b116ed9f36580e296` |
| `utils/build_semantic_digests.py` | `4eab095a838d21fd63dbf7402b7dc872ccc43cf0aa761bccc7f5835c0aa98fd0` |
| `utils/docling_schema_regression.py` | `c6a16716acdcbaf879d2ea2b1276c3eb73f42c8557968e5732cd99e63e95d208` |
| `utils/verify_missing_tokens.py` | `2cf113b92fa7723c24e064eb8f8c8f8ed36743865bc7b7b17b92361f65e3a339` |
| `utils/ab_ocr_compare.py` | `b28ad6f4d6119609290d3cd7f1683fe8de74255a78ddb487ea5695269e98d175` |
| `docs/gateflow/pr-197-r1-f3-goal-20260930.md` | `fcb4d6bc4cf9d34d2163a2b13435537ca305e9f12694c183f617c92246933935` |
| `docs/gateflow/pr-197-r1-f3-implementation-20260930.md` | `41b2f50d57f30e333af3daceb2ad5ed51a84154deaae3d4eca20fea2f7475c1a` |

## C01 修订映射（计划候选，不是代码修复）

| 直接缺口／裁决 | 新 plan 精确落点 | 保持与验收 |
| --- | --- | --- |
| 样本键与固定产物冲突 | C01 小节：digest 模块唯一 `_DIGEST_MANIFEST_NAME: Final[str]`；样本 `_DIGEST_SUFFIX`／`_digest_path`；`_require_distinct_digest_targets` 完整预检 | 固定汇总写址、预检比较同一常量；todo/写盘/统计同一样本路径 helper，不复制保留名魔法字面量 |
| 字面比较漏物理目标 | ASCII 保留名族 + resolve 等价 + 同物理 parent 的 ASCII basename 比较 + 现存 samefile | 本地大小写、双向 symlink、hardlink 直接覆盖证据；dangling 目标设计探针闭合；不扩 Unicode/casefold/全 stem 规范 |
| 拒绝 owner/时点缺失 | 只在 digest main 现有输入 try 块内，完整基线校验后、mkdir/todo/executor/worker/write 前 | 中文含1-based记录/PDF/两个目标，parser.error exit2；后条冲突也整体拒绝，原字节/链接保持；实际检查错误不降级成功 |
| 消费者被误限制的风险 | loader/schema/verify/A-B/diagnose 只读；_build_one 仍只返回分析数据 | 三个无关入口真实全缓存 CLI 的合法 `_manifest` 样本均 exit0、有效 digest 字节保持，无证据要求增加 consumer 限名 |
| 原504断言没覆盖反例 | N1～N7／P1～P4 临时非空矩阵；实际源码修后重测 | 包括不存在out、两次复跑、两个链接方向/硬链接、dangling/环、好前条坏后条、sentinel时点、中文/exit2、全快照与普通正例 |
| 用户授权及原 goal 没有扩张 | C01 对齐正常显式消费、冲突预检和原产物保持 | 不改 binding goal/布局/业务字段/转换默认/缓存续跑；若真的必须越界则列具体取舍停交总控 |

修改后的 docstring/help 要求与 exact caller 写入 C01 小节；只增加 digest 两个私有 helper/两个常量，不引入框架。原 A1 类型块及所有落地规则、共享 loader owner 全节、旧停止及恢复记录已与保存原件逐字比较，assert exit0；A2 selected-only/diagnose 后果、A3 A/B id 唯一及非 A/B 重复 id 允许、A4 数字搬迁、ProcessPool/ThreadPool、Path worker、成功/错误 TypedDict 及旧缓存限制维持。原第1～10项验收不删，仅追加第11项引用C01矩阵；永久 pytest/coverage 豁免不扩大。

## 实际取证、每次失败与恢复

Python/pyright 均先 `source .venv/bin/activate`，实际 Python 3.11.15／pyright 1.1.409。探针与合成目录只在本轮专属 tmp，临时素材自动清理；产品代码全程只读。类型检查是 **设计及取证探针**，不是产品完成证明；未重跑全仓 pytest 或全量 pyright baseline。

验证义务澄清（F3-PA01，`pr197-f3-planqualityfix-sol-20261001-01`）：上段不重复全量 baseline 仅适用于该次计划文本与临时探针取证。后续 C01 真实源码 fix 必须先 `source .venv/bin/activate`，按原 S1／AGENTS 运行受影响验收（含 C01 增量矩阵及受影响临时 harness）与项目默认全量 `pyright`，全量必须 exit0、0 errors；原780文件历史绿不能代替修后结果，也不能只查受影响文件替代全量门禁。临时配置的显式相对 include／`exclude=[]`／真实 `filesAnalyzed` 核验、禁止 suppress/cast 绕过新错误及 `utils/` 永久 pytest/coverage 豁免不变。下表、原 SHA 与旧命令仍是该次历史取证，当前修订身份及验证见 `docs/gateflow/pr-197-r1-f3-plan-validation-fix-20261001.md`；候选仍未 accepted，C01 源码仍未修复。

| 实际操作 | exit／实际子命令 | 结果与恢复 |
| --- | --- | --- |
| canary／AGENTS／Gateflow／指定证据／真实owner读取，branch/status/HEAD | 均0 | canary逐字实读；起始身份符合；相关消费基于源码，不用报告标签投票 |
| 初始八输入＋originals SHA、原 plan 保存 | 0 | `identity-start.json`；修订前匹配，原件未丢失 |
| `PYTHONPATH=. python …/fs_probe.py` 初版 | 0；5个真实digest CLI均0 | `exact/ascii-case/sample-symlink/summary-symlink/hardlink` 全部覆盖 numbers；exit0证明缺陷，非PASS |
| `PYTHONPATH=. python …/target_design_probe.py` | 0 | `target-design-result.json`：10拒绝/6接受、字节保持/no mkdir；只证明拟议判据，无产品CLI已修声明 |
| 首次 `python -m pyright --project …/pyrightconfig.json --outputjson` | 0；filesAnalyzed=2、0错 | 绝对include被忽略、退回目录发现；结果保留 `types-first-invalid-include.json`，不据此声称显式include有效 |
| 首次配置恢复检查 | 1 | 错误假设上项filesAnalyzed=0，实际为2，assert失败且尚未修改配置；此为取证检查错误，不是产品类型问题 |
| 修正配置及独立pyright重跑 | 各0；filesAnalyzed=2、0错 | include明确改为相对 `fs_probe.py/target_design_probe.py`、exclude=[]、strict；`types-result.json`与真实summary断言0 |
| fs_probe增加三个无关入口后的首跑 | 1；5个digest CLI0后schema CLI1 | 合成schema缓存遗漏原 `closed_json/new_parseable` 成功标志，原汇总按既有规则exit1；没有改源码或绕过退出。仅补正确fixture的两字段 |
| fs_probe修fixture后完整复跑 | 0；5个digest CLI0＋3个其它CLI0 | `fs-result.json`保留最终stdout/stderr及别名身份；无关schema/verify/A-B均接受合法_manifest样本，digest原字节保持 |
| 新consumer探针首次严格pyright | 1；filesAnalyzed=2、1错 | `types-consumer-first-error.json`：arm的空engine_evidence列表为Unknown；仅将fixture JSON映射明确注解为 `dict[str, JsonValue]`，不改数据/生产类型，不suppress |
| 同配置最终严格pyright及summary断言 | 各0；filesAnalyzed=2、0 errors/warnings/informations | `types-final.json`；明确include两个实际探针、exclude=[]，不是workspace排除假绿 |
| 计划增补、原A1/helper/旧取证块逐字保全断言、七输入复核 | 均0 | `identity-before-artifact.json`；新plan SHA如上、HEAD已到b42，相关冻结完全一致 |
| HEAD增量的只读log/show/status | 0 | 总控文档checkpoint，无本轮plan/源码提交；不执行stage/commit |
| 独立 `git diff --check` | 0 | tracked修改零空白诊断，不用组合末项退出推断 |
| 独立 `git diff --no-index --check /dev/null <本artifact>` | 1，零输出（预期新增差异） | 新文件差异而非空白错误，不能记成exit0 |
| 最终branch/七输入/八原件/新plan/types/staged检查 | 0 | `identity-end.json`；七只读输入及八原件均一致，HEAD仍b42，暂存路径为空；plan新SHA及实际filesAnalyzed=2/0错再次核对 |

fs_probe 三次共实际运行19次模块CLI：15次digest exit0确认覆盖，3次无关入口exit0确认边界，1次schema fixture错误exit1已恢复。不能把15次缺陷exit0合并成验收成功。本轮不使用尾随cat覆盖失败退出，非零与修复均在本表保留；中间工具trace可复核。

本轮关键证据均位于 `workspace/tmp/pr197-f3-planamend-sol-20260930-01/`：`original-plan.md`、`identity-start.json`、`identity-before-artifact.json`、`identity-end.json`、`fs_probe.py/fs-result.json`、`target_design_probe.py/target-design-result.json`、`pyrightconfig.json`、三个阶段类型结果及最终结果。现存大小写目标samefile为真但resolve文字不等，硬链接也仅samefile相等，直接支持多判据的最小必要性。

## 风险分类、局限与 docs 决定

| 风险／未覆盖 | 分类 | owner／destination |
| --- | --- | --- |
| C01文字修订待同版窄审、源码尚未修 | fixed in current slice（仅计划候选，不关闭finding） | 总控→MiMo/Kimi窄Planreview→accepted amendment commit→Sol S1窄源码fix/双路code review |
| 修改后main的exit2/中文/完整时点与全部N/P矩阵 | covered by later approved slice（原S1；本amendment须先accepted） | digest producer／原临时验收；本轮设计探针不替代实际源码验收 |
| 检查与写盘间外部更换链接／输入 | requiring new issue or explicit user decision | 总控另定并发/事务goal；当前不加锁、事务或回滚 |
| 未实测卷的非ASCII absent别名等价规则 | requiring new issue or explicit user decision | 总控有新直接反例再裁决；不无证据扩大Unicode规则，现存身份由samefile处理 |
| 跨运行stem缓存来源、失败存在即跳过、schema退出统计quirk | requiring new issue or explicit user decision | 原缓存/统计goal owner；保持原限制，换输入用新out，不以C01顺改 |
| selected-only/parity与diagnose旧假设 | fixed in current slice（仅原A2披露）；重现/consumer参数化另需新goal | 操作者全量清单及对应数据根／总控；消费者未修改 |
| 历史公开locator、真实转换/OCR/规模质量与性能 | requiring new issue or explicit user decision | 用户／总控另授权；本轮完全合成全缓存或设计metadata探针，不是OCR证据 |
| F4/F5/F6/F7、其它WU | assigned to later work unit | 总控及既有对应owner，本轮只观察允许并发 |

无未分类风险；“未来待审/待实施”不是本轮授权外业务取舍。没有必要改变binding goal/固定产物布局/用户规则的证据，因此不请求新业务裁决。README只读、不触发更新：仅内部gate文档修改，未来C01只变开发utils输入预检，无产品入口/安装/用户工作流变化。永久测试/coverage仍按AGENTS的utils豁免，实质临时非空验收保持。

## 下一 gate 与停止

仅作者 **plan amendment候选完成**，不自行accepted gate。总控冻结新plan SHA `68c73f081a66a2457667cbe1d3d0b8ea273d98e862970a74f53318b1bcb4fc9f`、本artifact及上述七只读输入，把同版plan交MiMo/Kimi窄 **Planreview**：重点核C01最小owner、唯一命名真源、大小写/物理别名、拒绝时点、字节保全、消费者不扩限和A1～A4不回退；两路完成后由总控独立裁决，必要fix/re-review，accepted amendment commit之后才可恢复源码fix。当前源码候选继续保留，C01 accepted/未修复、implementation blocked。

本轮到此停止，不派发review、不写controller/queue、不提交任何文件，不把artifact自行标记accepted。
