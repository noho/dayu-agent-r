RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6
CANARY=gpt-6-sol-3d84c797

# PR197-R1/F3-S1 implementation 与自验

- label：`pr197-f3-implement-sol-20260930-01`；当前 stage **implementation blocked（F3-S1-IMP-B01 / 总控 F3-C01）**，仅代码与本轮自验，未进入 review、未 commit/stage/push。
- cwd：`/Users/leo/workspace/dayu-agent-r`；branch：`codex/upload-material-oracle`；起始 HEAD `60307c15947e2f89457e03126b1251aeb4264c53`。
- accepted plan：`docs/gateflow/pr-197-r1-f3-plan-20260930.md` SHA-256 `a88dcf8e84ba4371b9081714aa736e043b95fea4395d68a5cacf1250130bb172`；binding goal SHA `fcb4d6bc4cf9d34d2163a2b13435537ca305e9f12694c183f617c92246933935`。七个输入 SHA 实读匹配 rereview freeze；其 bb11 HEAD 是旧审查窗口，本轮起点 60307 文档 checkpoint，源码身份相同。
- 已读取 AGENTS、Gateflow、goal/完整 plan/plan-fix、同版 MiMo 215517 与 Kimi 215618 窄报告、总控末节 F3 accepted 与最新用户现成裁决优先、四源码和根 README 约束。记忆只辅助保持裁决/实施权分离，不作为当前业务权威。
- 唯一源码 writer 范围：四既有 utils + 新 `utils/analysis_sample_inputs.py`；另新增本 artifact。所有临时材料仅在 `workspace/tmp/pr197-f3-implement-sol-20260930-01/`。

## 实施映射与 owner

| plan | 本轮实现 owner/变化 |
| --- | --- |
| 输入 contract/F3-S1 | analysis_sample_inputs 为唯一 root/manifest/PDF/stem 唯一性/同目录 baseline 规则 owner；不搜索或解析业务结果 |
| schema/digest/verify main | 必需 root/manifest，完整预检先于 mkdir/缓存/worker，传显式 Path；schema/digest ProcessPool，verify ThreadPool |
| A1 | 各脚本本地精确 TypedDict/Required/SchemaSuccessErrorUnion，仅 JSON/第三方出口 cast，原 bool closedJSON 与计数消费不改 |
| A2 | schema/digest 只汇总本次所选、digest 原 sorted 产物顺序；diagnose consumer 未改，历史 parity 不承诺 |
| A3 | A/B main 唯一 id/kind 必需与 id unique owner，非 A/B 不拒绝重复 id；缺臂整体 exit2 |
| A4 | 无闭包 counters 等价提升为模块私有 _number_counters，只改两处调用名与类型/docstring |
| CLI/docs | 删除旧搜索/选择 flags/私人身份；统一 python -m utils...；help 自足说明字段、最小例子、cwd 规则、stem 缓存限制 |

无生产 upload/download/Fins 行为、依赖、README、永久测试或产品 contract 改动。保留 worker 原转换调用及默认参数；移除既有 worker 内导入，改为模块级导入实际 runtime 模块，不加 lazy import 或兼容 shim。

## 验证过程（按实际顺序保留，后文为最终收尾）

1. 初始 branch/HEAD/status/canary 实读 exit0；七 SHA 断言 exit0，四源码原始副本与 identity-start.json 保存至本轮临时目录。已公告 F7 plan untracked，不编辑、不 stage。
2. 临时 implement.py 写四入口 exit0；新 helper/本 artifact 写入 exit0。下一步完整离线 harness 与真 pyright，自验尚未完成。

## Docs 与风险分类

根 README Agent 更新约束实读：面向最终用户，utils 属开发 checkout 入口，不改变产品工作流；不更新任何 README。

| 风险/未覆盖 | 分类与 owner/destination |
| --- | --- |
| 当前 locator/输入拒绝/选择汇总 | fixed in current slice（实现候选，须自验及下轮双路 code review；不宣布 finding closed） |
| 旧选择格式/direct-file 退役 | fixed in current slice（help/输入 contract，无历史迁移） |
| selected-only 对 diagnose 全量/parity 的影响 | fixed in current slice（仅披露）；操作者全量 manifest 对应默认数据根；consumer 仅固定默认数据根，隔离 --out 不自动跟随；历史 parity 重现/consumer 参数化 requiring new issue or explicit user decision |
| 同 stem 跨运行来源鉴权/错误结果存在即 skip | requiring new issue or explicit user decision；另立缓存 goal，换输入用新 --out |
| schema failed_stems 本轮 vs error_count 所选缓存 | requiring new issue or explicit user decision；保留原 quirk/退出公式 |
| 历史公开 locator | requiring new issue or explicit user decision；用户/总控历史级处置 |
| 真 PDF/OCR/规模性能/质量 | requiring new issue or explicit user decision；合成 Docling/stub 不能作为 PDF/OCR 证据 |
| 无永久 pytest/coverage | binding goal/AGENTS utils 明确豁免；本轮临时验收负责，持续防护需另立 WU（requiring new issue or explicit user decision） |
| F4/F7 与其它产品 finding | assigned to later work unit；总控及各 WU owner |

完成后停交总控独立核实，再 MiMo/Kimi 同版 Deepreview；本轮不宣布 slice/PR pass，不 commit。

3. 首次源码 pyright JSON exit0，version 1.1.409，filesAnalyzed=5，0 errors/warnings/informations。人工 diff 发现生成时 verify worker docstring 仍写旧 stem 参数；已在被触碰函数补齐三个 Path 参数说明，未改变行为。移除未使用 TypeAlias 导入与拼接空行。

4. 临时 harness 首次独立 pyright exit1，真正 filesAnalyzed=2：commands 记录中 list[str] 与 JsonValue 列表不变性引发 1 个 reportArgumentType。只在 harness JSON 记录处显式构造 list[JsonValue]，不 suppress/cast 掩盖，不改生产文件。goal/plan SHA 与 branch/HEAD 同时复核不变。

5. harness 独立类型复跑 exit0，filesAnalyzed=2/0 errors。acceptance-run1 单独命令 exit1：缺 --sample-root 的 stock argparse stderr 只有英文用法/required 错误，中文诊断断言失败；前面非空 worker、Path 路由、两个真实 child pickle、计算/缓存/跨 cwd/所选汇总断言均通过，但整体验收未通过。修复在四个 main 的 argparse 输入 owner：只捕获 parse_args 的 SystemExit(2)，补中文必需参数/--help 提示后原样重新抛出；不改退出码、不补参数、不增加 parser 框架。该新增修复仍映射 plan 输入中文错误成功信号。

## 当前停止条件：F3-S1-IMP-B01（不得即兴修复）

第二轮指定完整 harness `acceptance.py` 单独命令 **exit0**，输出 `F3 input acceptance PASS (504 assertions, 175 subprocess commands)`；第一轮失败保留且已恢复。该 PASS 只表示具名临时验收通过，不能当作 slice/PR 或 finding closed。

补充最小有效输入反例发现 accepted plan 的输入规则与固定产物命名冲突：

- 清单 `[{"pdf":"_manifest.pdf"}]`，PDF/同目录真实合成基线均为普通文件，路径/stem 唯一、根内、无私人数据；符合 plan 的全部定位规则与“不要求 fil_cn_ 前缀”。
- `load_samples` 实际接受。预置合法所选 digest 到 `<out>/digests/_manifest.json`，正式模块 CLI exit0，按存在即 skip；随后同一路径被汇总 JSON 覆盖，`numbers` 消失，stems 为 `["_manifest"]`。
- 此时“所选 digest 保留”和“固定汇总 _manifest.json”无法同时满足。后续 verify 读取这份 digest 会缺 `numbers`；不能以同 stem 缓存鉴权/历史 parity 限制掩盖这个单次有效输入命名冲突。
- 直接证据：`workspace/tmp/pr197-f3-implement-sol-20260930-01/reserved-stem-evidence.json`；独立 `reserved_stem_probe.py`/`.log`，**exit0 仅确认反例，不是通过证据**；自建临时输入已清理，未真实转换。
- owner：输入 helper 的 stem 规则与 digest main 的固定汇总产物命名边界。最小备选为新增保留 stem 拒绝规则，或改变摘要/产物布局；前者新增 accepted plan 未给定的输入拒绝，后者改变要求保持的布局。**没有实施任一备选，没有 fallback/后缀/搜索/兼容分支。**

状态：**implementation blocked**，源码写入停止；由总控按用户现成裁决核实该契约冲突，必要时取得明确 scope/输入裁决并修订/审查 plan。当前不能把候选交作可放行 slice 或自行进入 code review gate。下一 entry point 为总控核实 `F3-S1-IMP-B01` 后决定 plan 修订路径；原定 MiMo/Kimi 同版代码双路审查尚未进入。

该新增风险分类：**requiring new issue or explicit user decision**；owner/destination 为总控/用户的输入与产物命名裁决。与原缓存来源/历史风险分开登记，是当前阻塞项，未分类风险为零。

## 收尾验证与实际产物（源码停止后只取证/更新本 artifact）

本轮仅形成 F3-S1 **实现候选**；必需普通输入验收完成，但上述反例阻塞整体实现完成，PR197-R1/F3 仍未经代码双路复审/裁决，不能记 closed。总控并发新增 `docs/gateflow/pr-197-r1-f3-reserved-artifact-collision-20260930.md` 已只读，记录 F3-C01 accepted-candidate/未修复；其 F3-C01 与本报告 F3-S1-IMP-B01 是同一根因，不重复计 finding。本轮不修改总控 artifact，也不根据其初步方案直接实现。

### 实际五文件 diff 与候选身份

| 文件 | 实际增/删行 | 候选 SHA-256 |
| --- | --- | --- |
| `utils/docling_schema_regression.py` | +134/-69 | `c6a16716acdcbaf879d2ea2b1276c3eb73f42c8557968e5732cd99e63e95d208` |
| `utils/build_semantic_digests.py` | +216/-67 | `4eab095a838d21fd63dbf7402b7dc872ccc43cf0aa761bccc7f5835c0aa98fd0` |
| `utils/verify_missing_tokens.py` | +113/-36 | `2cf113b92fa7723c24e064eb8f8c8f8ed36743865bc7b7b17b92361f65e3a339` |
| `utils/ab_ocr_compare.py` | +44/-71 | `b28ad6f4d6119609290d3cd7f1683fe8de74255a78ddb487ea5695269e98d175` |
| `utils/analysis_sample_inputs.py` | 新增123行 | `021e777e263a87d8389741819f933d61bcca0e2f9762d49b116ed9f36580e296` |

新 helper 只有 frozen AnalysisSample 与 plan 指定四个函数；无 callback/profile/options 框架、业务结构 validator、兼容入口或搜索。分析结果本地类型按 plan 原块落地；Schema 三数组非 nullable、成功/失败联合、Required 下标、grid 每行列表、JSON 出口 cast 均已真实检查。数字函数的冻结 counters AST body 与模块顶层 body 相同；_number_diff 的所有原表达式仅有两处调用名变化，运行时完整 NumberDiff 与冻结函数类型副本相等（包括共同表格 400）。未改 _context、A/B 三个比较函数及数值正则/拼接/排序/截断。

### 全部验证命令/退出记录

所有 Python/pyright 运行前均 `source .venv/bin/activate`，Python **3.11.15**。子进程正式命令为 `sys.executable -m utils.<模块>`，显式 `PYTHONPATH=/Users/leo/workspace/dayu-agent-r`；跨 cwd 也只此机制，不加 direct-file import shim。临时代码和合成输入均在本轮专属临时目录，TemporaryDirectory 自行清理，不使用默认/历史输出根。

| 操作（均为本轮实际运行） | exit | 证据与断言 |
| --- | --- | --- |
| 七冻结 SHA/branch/HEAD 初检 | 0 | `identity-start.json`；旧七 SHA 一致，起点为60307而非旧bb11 |
| 五源码首次 `python -m pyright <五file> --outputjson` | 0 | `source-types-first.json`，1.1.409，filesAnalyzed=5，0 errors/warnings/informations |
| 临时 harness 首次独立类型检查 | 1 | `harness-types-first.json`，filesAnalyzed=2，1个 JsonValue list 不变性错误；已修临时 JSON 记录处，非 suppress |
| 临时 harness 修后独立类型检查 | 0 | `harness-types-second.json`，filesAnalyzed=2，0错误 |
| 完整 harness 第一轮独立命令 | 1 | `acceptance-run1.log`/`commands-run1.json`；missing-root 无中文诊断失败，修复四 main 的 parse_args 错误提示 |
| 完整 harness 第二轮独立命令 | 0 | `acceptance-run2.log`，**504具名断言/175次子进程**，只有全项通过才打印 PASS |
| 175次子进程真实退出分布 | 逐条记录 | `commands.json`：exit0 22次、exit1 3次、exit2 150次；全部与场景预期一致，不把预期失败算转换成功 |
| 未缓存 schema/digest/verify worker | harness内 | 两份不同字节/文件名；每 worker 每样本 cache miss；同签名 stub 核默认 OCR/table 参数；schema三项校验true，digest missing200/added300，verify对应四计数1/0/1/0，二次verify无新转换 |
| 三 main 同步 executor 验收替身 | harness内 | 三组精确 Path tuple 路由，真实worker消费两份样本；schema/digest仍ProcessPool，verify仍ThreadPool，不声称替身是真实转换并发 |
| 实际 ProcessPool spawn、max_workers=2 | harness内 | 两个不同child pid真实接收模块顶层函数/Path、回读唯一PDF字节与baseline/out路径，无转换 |
| 四 CLI 非空续跑/所选汇总 | harness内 | 未选中结果/digest/cache/arm原字节保持；schema total2；digest字段/排序/字节计数原公式；第二轮_manifest不自计入；verify只选两个stem；A/B显式id/kind/原列与Dice 0.5/1.0 |
| cwd/root/manifest/out | harness内 | manifest在root外仍按root；绝对CLI不同cwd与相对启动cwd产生相同输出；nested有效，不枚举未选PDF；loader/worker/main用rglob失败sentinel验证无扫描依赖 |
| 四入口输入负例与先拒绝 | harness内 | 缺root/manifest、root缺失/文件、manifest缺失/目录/坏JSON/坏UTF-8/空数组/非数组、记录null/缺pdf/错类型/空白/未知字段、PDF缺失/目录/绝对/.. /重复路径/重复stem/根外symlink、前条有效后条无效；每条exit2/中文/输出不存在或原字节保持，同一main加converter/executor/mkdir失败sentinel证明拒绝先于执行 |
| 脚本特定必需输入/元数据 | harness内 | digest/verify/AB缺基线、schema基线目录、verify缺/目录digest、AB缺/目录任一臂、缺id/kind/重复id，worker数0与-1；同份重复id清单在非AB三个入口仍保留两条 |
| 原缓存/异常/退出保持 | harness内 | schema缺基线有效且None字段；texts=null/7原TypeError→error，保留异常前字段、不写new_counts；所选error结果todo空仍error_count1/failed_stems[]/exit1；digesterror存在仍skip/failed[]/exit0；verify/AB内容缺键传播KeyError/exit1 |
| defaults常量/help与argparse原默认核对 | 0 | 原输出仍仓库workspace/tmp/docling-regression，仅核对不运行；冻结/候选真实AST worker默认分别2/4/2相等，`defaults-audit.json`；四help分别exit0，含字段/必需性/例子/路径/缓存限制 |
| reserved_stem_probe.py（阻塞反例） | 0 | 仅确认合法_manifest.pdf与固定产物冲突，详见B01；不是PASS |
| 临时最终独立类型检查 | 0 | `harness-types-final.json`，明确include acceptance/frozen_numeric/reserved_stem_probe三文件、exclude=[]、实际filesAnalyzed=3，0错误；不采用workspace排除假绿 |
| 首次指定全量 `python -m pyright dayu/ tests/ utils/ --outputjson` | 0 | `pyright-full-first.json`，filesAnalyzed=780，0错误；随后中文提示改动后再跑最终版本 |
| 最终指定全量同命令 | 0 | `pyright-full-final.json`，**780文件、0 errors/warnings/informations** |
| 最终默认 `pyright --outputjson` | 0 | `pyright-default-final.json`，**780文件、0 errors/warnings/informations**，没有改配置/依赖/排除项 |
| `pyright --version` / `python -m pyright --version` | 各0（独立复核） | 均 **1.1.409**；1.1.414更新提示仅warning，未升级 |
| plan原文字面locator扫描 | 0 | `SAMPLES`子串命中原MAX_TABLE_SAMPLES等算法常量；不是私人locator/搜索，不能按字面预期exit1冒称；算法常量保持 |
| 同范围词边界locator扫描 | 1（预期无命中） | 五文件无SAMPLE_LIBRARY_ROOT/SAMPLES变量、私人目录/rglob；旧六条样本身份已人工检查删除，没有换成默认身份 |
| tracked `git diff --check` | 0（独立复核） | 全tracked diff无空白诊断；未改并发治理文档 |
| helper `git diff --no-index --check /dev/null …` | 1（预期新文件差异），无诊断 | 不将no-index差异exit1错记0；早期组合命令最终exit1已拆开独立确认tracked check0 |
| 终检输入/源码/branch/scope | 0 | `identity-end.json`与candidate-source-sha.json一致；goal/plan/plan-fix不变；源码tracked只有本轮四文件、新helper独立；收尾HEAD **60307c15947e2f89457e03126b1251aeb4264c53** |

临时证据文件共同前缀：`workspace/tmp/pr197-f3-implement-sol-20260930-01/`。日志保留每次失败与恢复，harness命令没有尾随cat覆盖Python失败。没有pytest/coverage永久资产：按AGENTS和binding goal的utils豁免，但已运行上述实质验收。无真实PDF/OCR、外网/provider调用、私人语料或用户数据读取；DoclingDocument/stub只证实输入路径和既有分析消费。

### 首尾Git与交接

起始/收尾branch均 `codex/upload-material-oracle`，HEAD均60307。收尾另观察到已授权总控F4 goal、adjudication、queue、handoff追加及F7 plan/controller evidence，和F3-C01治理记录；只读、不改/stage，不对它们做旧字节assert。五源码在停止后的candidate哈希与终检匹配，binding goal/accepted plan无未知漂移。本轮没有branch/worktree/commit/push/PR/merge、子Agent或review派发。

README决定维持不更新；风险分类维持前表，加B01/C01为当前阻塞且 requiring new issue or explicit user decision。下一步由总控独立核实反例、决定accepted plan amendment及同版双路计划复审；在授权修订前本轮不继续源码修复。之后才可能恢复implementation/code review；当前不能自行宣布slice/PRpass或finding closed。

最终空白检查独立执行：tracked `git diff --check` exit0；helper 与本 implementation artifact 的 `git diff --no-index --check /dev/null <file>` 各exit1且零输出，均为新增文件差异、无空白诊断。最后源码/goal/plan/plan-fix SHA与branch断言exit0，HEAD仍60307；无未知源码漂移。本轮终态为 implementation blocked，停止交总控。
