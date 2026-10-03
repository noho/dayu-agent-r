RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-8c00ecbc

# F3-PR4-A1 两句计划异常文字修复候选

- label：`pr197-f3-digestexception-sol-20261001-01`；gate：同一 F3-S1 的 plan amendment fix，非新 S2。本文为本轮真实身份与验证记录；plan 头部旧 runtime、canary、label、候选身份及历史验证窗口逐字保留，不作为本轮证明。
- runtime 为 Codex，provider 为授权路由 gpt-6-sol；当前上下文未提供可核验的实际 canonical model，诚实记 `unknown`，不从 canary 猜模型。CANARY 已用工具读取本轮指定文件，原始内容保存于 `workspace/tmp/pr197-f3-digestexception-sol-20261001-01/canary.read.txt`。
- binding goal：`docs/gateflow/pr-197-r1-f3-goal-20260930.md`，SHA `fcb4d6bc4cf9d34d2163a2b13435537ca305e9f12694c183f617c92246933935`；唯一根权威：`docs/gateflow/pr-197-r1-f3-digest-exception-adjudication-20261001.md`，SHA `3ebe7600059f16832241017cdb495c2ae3f4e8401f3d09d53745679375218a2b`。已读 AGENTS 与 Gateflow skill；不重裁现成业务语义。
- 写界：只替换 `docs/gateflow/pr-197-r1-f3-plan-20260930.md` 中第 123、128 行指定文字，唯一新增本报告；命令与验证日志只在 `workspace/tmp/pr197-f3-digestexception-sol-20261001-01/`。没有修改 source/tests/README/goal/旧报告/根控制文档、freeze 或 originals；未派发 Agent、stage/commit/push/PR/merge/comment、变更分支/工作树/main、网络访问或推进下一 gate。

## 动机、owner 与实际变更

低严重性计划矛盾成立：C01 表第 123 行写身份检查 OSError 直接向 main 传播，而第 136 行已裁判据 5 要求私有预检补具名上下文、抛 ValueError 并链接原异常；第 128 行统一要求 ValueError/OSError 也会误导纯路径推导及私有预检的 raises 声明。文字 owner 是 C01 私有预检 contract，业务 owner 仍为 digest producer；不是产品故障证据或新的公开取舍。

第 123 行改为冲突具名 ValueError，身份检查失败补同一记录/PDF/样本目标/汇总目标上下文后抛具名 ValueError 并链接原 OSError/ValueError。第 128 行按各函数实际 contract 说明异常：纯路径推导不虚构业务异常；digest 私有预检声明上述 ValueError 原因链；main 的其它输入 OSError 仍进原输入错误边界。

- 旧 plan SHA：`05729875b12bcf78a7518ed462b93cd582c056fb849321e38fed11e7fc09f126`。
- 新 plan SHA：`2983efa4326cc799565fab27a350d79bf74b40d540beb0143b4dfa90f181a421`。
- 全件正向：原件仅两次各唯一替换所得 bytes == 当前完整 plan；全件逆向：当前 plan 逆两替换 == 冻结原件全部 bytes。739 行中仅 123、128 改变，其余 737 行逐字节相等。见 `workspace/tmp/pr197-f3-digestexception-sol-20261001-01/two-replacements.proof.json`、`final.verify.json`。

完整实际两个 hunk（`git diff --no-index --unified=0 <original> <plan>`，真实 exit 1 表示有差异，stderr 0 bytes）：

```diff
diff --git a/workspace/tmp/pr197-f3-digestexception-sol-20261001-01/originals/docs/gateflow/pr-197-r1-f3-plan-20260930.md b/docs/gateflow/pr-197-r1-f3-plan-20260930.md
index f54563e8..3f3b8b1d 100644
--- a/workspace/tmp/pr197-f3-digestexception-sol-20261001-01/originals/docs/gateflow/pr-197-r1-f3-plan-20260930.md
+++ b/docs/gateflow/pr-197-r1-f3-plan-20260930.md
@@ -123 +123 @@ A/B 最小例子（也可供前三入口使用）：
-| `_require_distinct_digest_targets(samples: list[AnalysisSample], digest_root: Path) -> None` | 模块级私有、顺序完整预检；无 callback/options | 使用同一常量及 `_digest_path`，保留名仍在本helper；通用身份判据复用C02公共 `analysis_targets_alias`。发现冲突抛 ValueError，身份检查 OSError 向 main 传播；不读 digest 内容、不创建输出 |
+| `_require_distinct_digest_targets(samples: list[AnalysisSample], digest_root: Path) -> None` | 模块级私有、顺序完整预检；无 callback/options | 使用同一常量及 `_digest_path`，保留名仍在本helper；通用身份判据复用C02公共 `analysis_targets_alias`。发现冲突抛具名 ValueError；身份检查失败时补同一 1-based 记录索引、PDF 路径、样本目标、固定汇总目标及“无法检查固定汇总冲突”的中文后，抛具名 ValueError 并链接原 OSError/ValueError；不读 digest 内容、不创建输出 |
@@ -128 +128 @@ A/B 最小例子（也可供前三入口使用）：
-需增加 `Final`、`AnalysisSample` 与公共 `analysis_targets_alias` 的显式类型导入；C01不改 loader签名、worker Path、成功/错误 TypedDict、数字算法或 A1～A4 类型设计。新增函数完整中文 docstring 至少说明参数、返回值及 ValueError/OSError；main docstring 说明冲突以 SystemExit(2) 拒绝且无任何分析写入，不承诺执行后回滚。模块概览与 argparse 中文 help/epilog 同步说明 **digest 专属保留目标**、ASCII 大小写规则、已有链接也会检查、错误在执行前拒绝；原字段/例子/路径基准、同 stem 跨运行缓存限制继续自足，不给其它入口追加限名说明。help 从同一常量插值固定名字，不另建命名配置。
+需增加 `Final`、`AnalysisSample` 与公共 `analysis_targets_alias` 的显式类型导入；C01不改 loader签名、worker Path、成功/错误 TypedDict、数字算法或 A1～A4 类型设计。新增函数完整中文 docstring 按各函数实际 contract 说明参数、返回值及异常：纯路径推导不虚构业务异常；digest 私有预检对冲突及身份检查失败声明具名 ValueError，身份检查失败链接原 OSError/ValueError；main 的其它输入 OSError 仍由原输入错误边界处理。main docstring 说明冲突以 SystemExit(2) 拒绝且无任何分析写入，不承诺执行后回滚。模块概览与 argparse 中文 help/epilog 同步说明 **digest 专属保留目标**、ASCII 大小写规则、已有链接也会检查、错误在执行前拒绝；原字段/例子/路径基准、同 stem 跨运行缓存限制继续自足，不给其它入口追加限名说明。help 从同一常量插值固定名字，不另建命名配置。
```

## 保全与首尾核验

首检 15 live / 15 originals 全部逐项 SHA 匹配且 live 与原件 bytes 相等；末检 14 readonly live 仍匹配、plan 匹配上述新 SHA、15 originals 仍匹配原 SHA。逐项路径、预期/实算值与布尔结果保存在 `initial.verify.json` / `final.verify.json`，均位于 `workspace/tmp/pr197-f3-digestexception-sol-20261001-01/`。五个 F3 related utils 源码及邻接 `ab_ocr_convert.py` 保持原 SHA；未把 F4 storage/CN 候选读作本任务证据。

- 唯一 workspace：`/Users/leo/workspace/dayu-agent-r`；首尾 branch：`codex/upload-material-oracle`。
- freeze 起点 HEAD：`dc29c1fe5e173d9ef710cd7f44fd0889e0da46c9`；首检 HEAD：`dc29c1fe5e173d9ef710cd7f44fd0889e0da46c9`；末检 HEAD：`dc29c1fe5e173d9ef710cd7f44fd0889e0da46c9`。HEAD 只记录，非冻结的根合法 docs checkpoint 不作漂移阻塞。
- 首尾 main：`fac32ecbff9bfe792b63ee9667c8697826b631f4`；freeze SHA 首尾：`85c5f0c54f52d3e45625debb932d2e0ac4419d1af1ee0dc05944a7047c5003f2`；Git staged path 输出首尾一致，本轮无 stage。
- 保护证据：plan 第 124 行 main `except (OSError, ValueError)`、第 136 行判据 5、第 209–228 行公共 alias OSError 透传及公共分组 ValueError 链、C01/C02 全部矩阵与 PA01 均保持。`protected-segments.json` 记录完整区段 SHA 与字节相等；正逆全件比较同时保护其它 docstring/signature/type、A1–A4、布局、缓存、默认值、owner 及旧头部。
- 真实 source 定位只读取 `utils/analysis_sample_inputs.py` 输入异常边界及 `utils/build_semantic_digests.py:390–429` 的现行 main；公共新 helper 仍是 plan contract，未伪称其已实现。

## 静态验证、失败与文档判定

所有下列命令在唯一 workspace 运行，双流与 exit 分别保存；完整文件检查未裁剪到改动句。

| 命令 | 真实 exit / stdout / stderr | 日志（相对本轮日志目录） |
| --- | --- | --- |
| `git diff --no-index --unified=2 <original> <plan>` | 1 / 4372 bytes / 0 bytes；两个改行合成一个 hunk | `plan.diff.command.json`、`plan.diff.stdout`、`plan.diff.stderr` |
| `git diff --no-index --unified=1 <original> <plan>` | 1 / 3840 bytes / 0 bytes；完整两个 hunk | `recovery.commands.json`、`plan.two-hunks.stdout`、`plan.two-hunks.stderr` |
| `git diff --no-index --check <original> <plan>` | 1 / 0 bytes / 0 bytes；完整 plan 无空白错误 | `recovery.commands.json`、`plan.noindexcheck.stdout`、`plan.noindexcheck.stderr` |
| `git diff --no-index --check /dev/null docs/gateflow/pr-197-r1-f3-plan-digest-exception-fix-20261001.md` | 首次 3 / 93 bytes / 0 bytes；修正后 1 / 0 bytes / 0 bytes；完整报告无空白错误 | `report.noindexcheck.stdout`、`report.noindexcheck.stderr` |

非预期失败与恢复：编辑与证明 Python 命令 exit 1，stdout 空，stderr 为 `<stdin>:41 AssertionError`；两替换与正逆全件比较已成功，失败只因误要求 `--unified=2` 必有两个 hunk。读取真实 diff 确认相邻改行合并后，以 `--unified=1` 恢复双 hunk 输出并再次正逆全件核验；未为恢复改写 plan。原失败双流与原因在 `edit-attempt.stdout` / `edit-attempt.stderr` / `failures.json`。报告首次 noindexcheck 返回 exit 3、stdout 93 bytes、stderr 空，实际指出第 34 行嵌入 diff 的空白上下文行有尾空格；生成报告命令因此在 `<stdin>:130` 断言失败（outer exit 1、stdout 空）。改用真实 `--unified=0` 输出保留完整两个 hunk且没有空白上下文行，未改 plan；再次完整报告检查为 exit 1、双流空。首检失败命令及双流保存在 `report.noindexcheck.attempt-1.*`，生成命令失败双流保存在 `report-generation-attempt-1.*`，恢复 diff 在 `plan.zero-context.command.json` / `.stdout` / `.stderr`。全部失败登记于 `failures.json`。正常 diff/noindexcheck 的 exit 1 已如实记录，不记作 exit 0，也不冒称全部工具零失败。

本轮无真实 source 变动，pytest / pyright / per-file coverage 均 N/A；未重跑 19/22 设计 probe 或全仓 baseline。未来同一 F3-S1 真正源码 PA01 的受影响完整 harness、C01/C02 新增矩阵及默认全量 pyright exit0/0 errors 不豁免。仅内部计划文字及本报告，不触发 AGENTS 的 README 更新条件；不改 README。

## Residual 与停止状态

| 分类 | 当前项 / 状态 | owner / destination |
| --- | --- | --- |
| fixed in current slice | F3-PR4-A1 两句已修候选，未经 re-review，不能作 gate pass | C01 私有预检 contract / 根核收后同版两句窄复审、根裁决 |
| covered by later approved slice | C01/C02 产品仍 accepted／未修；仅沿用原 F3-S1 源码阶段，非新 S2 | digest producer、各入口目标命名与共享身份 owner / accepted amendment 后同一 S1 source fix 与 code review |
| assigned to later work unit | F2、F4–F7 及其它既有队列项未在本轮处理 | 对应 WU owner / 既有根队列；F4 同版只读 code review 不作为本轮证据 |
| tracked by existing issue | 既有修复归属仍为 PR197 / issue198；本轮不更新外部状态、不用 issue 标签延期本 accepted finding | 根总控 / 既有 issue198 修复队列与 PR197 |
| requiring new issue or explicit user decision | 原已分类 Unicode 尚未创建别名、预检后外部换链接、跨运行缓存来源、历史公开 locator 与真实语料验证边界保留 | 原 plan 所列总控/操作者 / 新直接反例或新 goal、另行明确授权；不扩大本轮范围 |

文字已修候选；F3 plan gate 尚未 accepted，C01/C02 产品未修。完成本报告与静态验证后停止，下一步由根核收→MiMo/授权 DS backup 同版只审两句与保全→根裁决必要 fix/re-review→accepted amendment commit→未来 source fix；本轮不自行放行或推进。
