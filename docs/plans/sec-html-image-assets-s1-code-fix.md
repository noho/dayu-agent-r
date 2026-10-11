# SEC HTML 图片资产 S1 code review 后修复记录

- Work unit：`sec-html-image-assets`；gate：`fix`（S1 code review 后）；slice：唯一 approved S1。
- Branch：`fix/sec-html-image-assets`；accepted plan/HEAD：`771299b8244e5cb25ce8f943ab41671d8e59e16c`；真实旧代码基线：`297bfbbc67b7d7468e3dfb6669a3385c4dd10d18`。
- Scope/decision：已读取根 AGENTS.md、Gateflow skill、goal、approved plan、S1 implementation、193943/193944 两路 review 和 195654 最终总控裁决。只处理 accepted 且未修复的 C1/C3/C4/C5/C6；服从总控标准契约，不采用原 review 的分号拒绝建议。C2 保持 rejected-with-reason，没有加入 Cf 黑名单。
- 状态：**本 worker 已实施修复并完成最终代码验证，交总控进入双路 re-review。** 这不是 re-review 裁决、slice accepted 或 final closeout；原 review finding 最终状态仍由后续 reviewer/总控回写。
- Artifact path：`docs/plans/sec-html-image-assets-s1-code-fix.md`；本轮权威验证：`docs/validation/sec-html-image-assets-code-fix.json`。

## 根因判断与改动边界

五项动机均由直接 owner 代码和回归支持：分号被 `urlparse.path` 截断会把必要图片指向另一资源；`dict(attrs)` 覆盖首属性会漏实际引用；解码后任意 `%` 拒绝超出了原样合法单组件契约；基础 descriptor 的 storage 校验裸异常越过 typed 发现失败；目标 HTML 图片数与全部 filing 图片数及最终测试宇宙原记录不一致。修复均在产生/校验相应语义的 owner，不在 workflow/adapter/展示层兜底。

本 worker 实际修改的代码/测试/README 只有：

- `dayu/fins/downloaders/sec_downloader.py`：完整图片 path、首属性值、百分号边界、基础名字 typed 失败。
- `tests/fins/test_sec_html_image_assets.py`：owner 回归与真实 Fs publication/失败/复用/请求断言。
- `tests/fins/test_sec_html_image_assets_real_cli.py`：完整已选 HTML 的独立引用核验、目标/filing 分栏逐图证据、producer hash 与 UA 无泄漏布尔检查。
- `dayu/fins/README.md`、`tests/README.md`：按职责说明当前稳定契约及验收边界。
- 本 fix artifact 与最终 validation JSON。

其余三生产 owner、另外两 approved 测试及根 README 的已有 S1 改动没有被本 worker 再修改。最终验证对四生产 owner 都采用新 clean 测量。未改 storage/schema、旧 HTML 补链/6-K 筛选、其它业务文件、goal/plan/control/review 或实施 artifacts；未读取原业务任务其它业务文件。原业务 workspace 0 写，真实 CLI base 全部新建在独立临时 root。package 保持 0.1.4，未发布 download contract 保持 v1.3.0，没有额外 bump。

## Findings 的修复与证据

| Accepted finding | Owner 修复 | 本 worker 实跑证据 / 交接状态 |
| --- | --- | --- |
| C1 / DS finding 1 | 新图片 helper 的输入校验、base 归一化、origin/path 授权和最终身份全部使用保留完整 path 的 `urlsplit`；最终候选解析后再去 query/fragment。 | src/srcset/picture-source 的字面分号与 `%3B` 同 canonical，不与 `plot` 合并；含分号 file base 的 `?/#` 保留完整身份；分号子目录及分号后的危险编码 typed 失败；基础 exact 文件零重复 HEAD；特殊名 exact HEAD/GET、必要失败 exact 名称、旧 publication rollback/retry、完整指纹通过。已实施并验证，待双路 re-review。 |
| C3 / mimo F-001 | extractor 对 HTMLParser 已小写的每个属性名保留首值；None/空值也占位，不收集所有重复值。 | 重复 src/srcset/picture-source/base href、大小写、None/空首值与后续 base 不覆盖均通过；三类入口及无值 base 经正式 fresh/旧版/缺版本发布集合回归。已实施并验证，待双路 re-review。 |
| C4 / mimo F-002 | 单次解码后只拒绝残留 `%HH` triplet 或其它已批准危险；普通字面 `%` 合法。 | 合法 `plot%25.jpg` 的三入口/base、canonical/去重、基础复用、exact transport/发布指纹通过；src/srcset/base 的 `%2520/%252F/%252e` 和 raw 非法 triplet 继续 typed 失败。已实施并验证，待双路 re-review。 |
| C5 / mimo F-003 | existing descriptor 调用 storage filename helper 的边界捕获 ValueError，保留 cause 并投影 SecHtmlImageDependencyError；非法名只用封闭“基础文件”标签和安全说明。 | 非法基础路径/分隔/非原样名、控制名与大小写碰撞回归；pipeline 的 fresh/upgrade 坏基础 descriptor 均为 typed FILING_FAILED，零 begin/图片请求，旧 publication/meta/revision/hash 保留；无 workflow except ValueError。已实施并验证，待双路 re-review。 |
| C6 / mimo F-004 | 历史 implementation JSON 不改写；新 JSON 权威记录最终 collect/pass/skip、clean coverage、pyright 和新独立真实矩阵。 | 最终 3646 collected / 3637 passed / 9 skipped；两例目标 HTML 15+12=27，完整 filing 15+13=28；2025 额外 image_1a.jpg 单列。逐一解析全部实际已选 HTML，核验所有28图的 GET、仓储 URI/size/SHA256 和完整 descriptor 指纹；不把额外图片称财务表。已实施并验证，待双路 re-review。 |

C2 未实施，沿 195654 的 rejected-with-reason；DS open questions 按总控既有裁决处理，没有新增产品/scope 决策。

## 最终实际验证

所有命令先 `source .venv/bin/activate`。最终准确 subprocess argv、cwd、显式非敏感配置、log/hash、exit、sourcehash before/after 均记录在 validation JSON；不输出/保存 UA 值、headers 或完整 env。

最终运行根：`workspace/tmp/sec-html-image-assets-code-fix-final-_9uka6o_/`。

| 验证 | 实跑结果 |
| --- | --- |
| 最终 `python -m pytest -q -p no:cacheprovider --collect-only tests/fins tests/cli/test_fins_commands.py`（另有准确 basetemp） | exit 0；3646 collected |
| 最终 `python -m pytest -q -p no:cacheprovider tests/fins tests/cli/test_fins_commands.py --cov=dayu/fins/downloaders --cov=dayu/fins/pipelines --cov-report=term-missing --cov-report=json:<final-root>/evidence/coverage.json`（另有准确 basetemp） | exit 0；3637 passed，9 skipped；新 COVERAGE_FILE，无 append |
| 全仓 `pyright`，最后代码/测试修改之后 | exit 0；0 errors / 0 warnings / 0 informations |
| 显式 opt-in 的 `python -m pytest ... tests/fins/test_sec_html_image_assets_real_cli.py` | exit 0；2 passed / 0 skipped；两例各12次，共24次正式 CLI |
| `git diff --check`、新增 artifact/源文件 whitespace 检查 | exit 0 |

四生产 owner 的新 clean coverage：

| 文件 | Coverage |
| --- | --- |
| sec_downloader.py | 95.15% |
| sec_download_filing_workflow.py | 89.86% |
| sec_pipeline.py | 89.54% |
| sec_rebuild_workflow.py | 89.92% |

逐文件均 >=80%；没有新增 coverage 排除、ignore、Any/object 或松散类型。旧 line-map 数据未 append，未复用旧 coverage；新 broad 已覆盖全部受影响测试。四 owner 和本 unit 测试的最终 hashes 在 collect/broad/pyright/real 前后一致；CLI observer 同时验证新/旧入口 origin、package/download version 和实际 downloader 源码 hash。

### 新真实矩阵

| 样例 | 目标 HTML 引用/去重 | 完整 filing 图片 | 全部已选 HTML | 额外图片 |
| --- | --- | --- | --- | --- |
| 2019 / 0001193125-19-110066 | 17 / 15 | 15 | d733154d6k.htm | 无 |
| 2025 / 0001046179-25-000082 | 12 / 12 | 13 | a2q25e_withguidancexfinal.htm、a2q25presentatione_6kxwm.htm、tsm-20250717x6k.htm | image_1a.jpg；仅称必要依赖 |

fresh、两个 baseline 正式旧状态（upgrade/failure-upgrade）、普通升级、exact GET 404 的 fresh/upgrade、故障解除后的 retry、四类成功 base 的 repeat 均完整保留 argv/stdout/stderr/operator.log/observer/descriptor/snapshot/hash/versions。四次注入故障 exit1，fresh MISSING、upgrade 旧 publication/manifest/meta/revision/hash/version exact 保留；解除故障 retry 成功；四类 repeat skipped 且零目标 transport。旧状态来自原 base git archive 的生产 CLI，没有手改文件/元数据或种旧状态。28张图在四种成功 base 均逐图核验；真实 manifest/HTML 未改。

SEC_USER_AGENT 只在内存复用既有 literal；新旧本轮 evidence 与交付 artifacts 逐文件字节检查结果只记录布尔值。原业务 workspace 和原证据目录无写入，未清会话；真实 roots 不运行 processor/LLM，不声明 OCR/财务数值或真实 processed 重算通过。

### 历史与失败尝试

- `docs/validation/sec-html-image-assets-implementation.json` 和 S1 implementation artifact 保留 pre-fix 历史，protected hash 未变；其中3554 broad、旧 sourcehash/旧尝试及27口径不作为本轮最终证明。它们对最终代码验证已 superseded；原两路 review 由 re-reviewer 回写，本 worker 不代审。
- 本轮首次 owner 193 pass 及随后 affected focused 445 pass 保留完整日志。初步193执行没有单独采集 sourcehash，明确仅为 preliminary，不能充当最终冻结证据；445运行的源码 hashes 已记录，新最终 broad 覆盖同一 owner 集合。
- 首次 pyright 发现2个新真实验证器 JSON list 类型错误，显式类型修正；未用 ignore/Any/排除绕过。该尝试 exit1 保留。此前在途 broad 主动中止，640 pass/exit2，不当作完整通过；此前真实24次矩阵 runtime 完整成功，但类型修订后又新建 root 重跑，前者明确 superseded。失败/中止/重复证据均在最终 JSON 的 validation_attempts，未覆写原日志或旧源 hash。

## Docs decision

读取并遵守相应 README 约束。Fins README 按稳定契约补首属性值/完整 path/百分号及 typed 基础名失败；tests README 按已实现维护约定补 owner 边界和完整 filing 分栏核验。根 README 的命令、参数、用户工作流和日志定位没有新增变化，本 worker 不再修改；无分层/装配变更，不触发 dayu/README.md。没有机械扩写或产品内部术语外泄。

## 残余风险、owner 与 destination

| 风险 | 分类 | Owner / destination | Status / path |
| --- | --- | --- | --- |
| R1 最终28图/补齐/必要失败/幂等证据 | fixed in current slice | S1 worker/总控；最终24 CLI矩阵 | 已验证，待re-review；本轮 validation JSON |
| R2 发现/版本门/rebuild/事务/取消/并发/processed标记与C1/C3/C4/C5 | fixed in current slice | SEC downloader/workflow/rebuild/tests；总控双路re-review | 实施验证完，review未代判；本artifact + validation JSON |
| R3 HEAD策略/validator漂移、当前版本快跳不重检远端 | assigned to later work unit | SEC transport/workflow维护者；独立远端重校验/指纹策略需求 | 已批准非目标；approved plan |
| R4 子目录、更宽srcset、CSS/JS/browser、legacy非UTF8 | assigned to later work unit | SEC downloader/Fins storage维护者；有真实样本的目录资产地址契约/资源解析需求 | 当前有限边界typed失败已验证；approved plan |
| R5 外站/跨申报/OCR/财务数值 | assigned to later work unit | 后续需求提出方；独立能力需求 | 已确认非目标；goal/plan |
| R6 HTTP200非空非图片内容、HEAD/GET内容与validator不同源 | assigned to later work unit | SEC transport维护者；响应内容校验/validator同响应身份需求 | 未扩大响应契约；approved plan |
| R7 真实processor/LLM/OCR/processed重算 | assigned to later work unit | Fins processor/分析维护者；独立图片读取/OCR验收 | 合成Fs owner验证processed标记，不替代真实转换；approved plan |
| C2 Unicode视觉混淆/展示策略 | assigned to later work unit | Fins storage/展示维护者；有样本的全局文件名展示契约需求 | 当前rejected-with-reason；195654裁决 |
| DS OQ2/RR10 私有typed prefetch边界 | assigned to later work unit | SEC downloader/workflow维护者；独立公共typed transport契约需求 | 总控确认当前approved边界，无当前行为finding；195654裁决 |
| DS RR9 真实新形态样本采集 | assigned to later work unit | SEC downloader/tests维护者；有真实新形态的独立验收需求 | 三候选/base合成owner矩阵本S1已验证；195654裁决 |

无未分类风险或 scope/owner 阻塞。剩余流程是总控派发双路 re-review、裁决并决定 accepted slice checkpoint；本 worker 未启动 Agent，未 stage/commit/push/PR，未修改 control/review 或创建 accepted slice commit。
