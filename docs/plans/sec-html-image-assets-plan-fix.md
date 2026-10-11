# SEC HTML 图片修复：Plan fix artifact

## Gate / work unit / scope

- Work unit：`sec-html-image-assets`；gate：`fix`（plan review 后，仅修计划）；worker：`gpt-6-sol`。
- 分支：`fix/sec-html-image-assets`；base：`297bfbbc67b7d7468e3dfb6669a3385c4dd10d18`。
- Binding goal：`docs/plans/sec-html-image-assets-goal.md`（已确认）；裁决真源：`docs/reviews/plan-review-20261011-183624.md`。原 review：`docs/reviews/plan-review-20261011-180739.md`、`docs/reviews/plan-review-20261011-180741.md`。
- Changed files / artifacts：仅 `docs/plans/sec-html-image-assets-plan.md` 与本文 `docs/plans/sec-html-image-assets-plan-fix.md`。
- 本轮禁止实现、修改 goal/control/review、生产代码、测试、历史真实 fixture 或原业务 workspace；禁止 commit/push/PR、其它 Agent、清会话。本 worker 不代替总控裁决/登记 gate，不重复 baseline 测试或真实下载。
- Preflight：核对 branch/status；已有未跟踪 goal/control/plan/review/validation 为上游状态，原样保留。读取 AGENTS.md、Gateflow、当前 plan、裁决、两份原 review及已确认goal；只补读受影响 mock/断言、skip/HEAD、资产文件名 owner 的必要段落，未全仓扫描或重新读取业务来源。

## Decisions / findings

初步修复状态统一为 **已修复待 re-review**。这里只说明计划文本已闭合；尚无实现或 re-review 证据，不能作为 review pass/accepted plan commit 的依据。总控保有最终 finding 状态与 gate 放行权。

| Finding | 既有裁决 | 初步状态 | 修订闭合位置 / owner |
| --- | --- | --- | --- |
| SECIMG-A1 | accepted | 已修复待 re-review | plan 的 S1 allowed/focused、自动化测试表及 A1 专节；`tests/fins/test_sec_earnings_repair.py` 供数/断言 owner，生产下载语义由 downloader/workflow/upsert 持有 |
| SECIMG-A2 | accepted | 已修复待 re-review | plan 调用步骤5–7、Phase A/B状态表、空fp专段及测试表；SEC filing workflow 的阶段/skip owner，复用 `_can_skip` 真源 |
| SECIMG-001 | accepted | 已修复待 re-review | plan 直接候选/srcset专节、共享URL/name、allowed/无src发布/升级/失败矩阵；SEC downloader 依赖发现 owner |
| SECIMG-002 | accepted | 已修复待 re-review | plan 首base/URL专节、最小合成URL矩阵、发现失败诊断；SEC downloader 地址真源 owner |
| SECIMG-003 | rejected-with-reason | 不纳入修复；沿用总控裁决 | plan 单组件边界、子目录typed失败/旧publication保留及R4；后续目录能力 owner 为SEC downloader/Fins storage，无映射/schema设计 |

### A1：完整测试边界及明确测试供数

- 将 `tests/fins/test_sec_earnings_repair.py` 加入 allowed files 和 focused pytest，broad 仍覆盖 tests/fins；不通过缩小测试集合避开失败。
- 对三份原 META cover 的实际 `meta-20240201_g1.jpg`、`meta-20250129_g1.jpg`、`meta-20260128_g1.jpg` exact URL，在该测试文件内提供常量/注释标识为 SYNTHETIC 的确定性 JPEG bytes。它们不是 SEC 原图，不新增伪官方 raw 图片，不更改历史 HTML或source manifests。mock 仍拒绝其它未声明URL；HEAD ETag/size和GET来自相同测试bytes。
- cover-only、cover+exhibit、untouched、retry、重复、注册集合与fingerprint全部迁移为同一完整 descriptor 集合F，逐文件从正式仓储读回，断言exact集合/size/SHA-256/manifest/snapshot；不能把“cover必须存在”当全集断言或在期望中复用被测extractor。
- 继续保护8-K HTML选择、EX-99/primary、未选来源、processed重处理、current快跳与overwrite补HTML，以及原附件失败的原子保留；补META必要图GET故障保留。没有生产compat branch。

### A2：空fp的前置工作及失败优先

- 保留当前版本+空fp在完整F等价后返回 `remote_files_equivalent` 的现有规则；不修复空fp、不加历史读取/默认值/兼容分支。
- listing/既有precheck → 成功的完整base GET → 三类候选/base/URL发现及开启时的HEAD尝试 → 完整F/fingerprint → `_can_skip`。base必要GET或typed发现失败先于skip返回失败，旧publication保留；取消沿现有终态。HEAD元数据不可用仍是optional，不新增必须HEAD成功的资格。
- owner测试用公开source create/blob/batch建立明确的空fp边缘输入，不能改已发布meta或mock classifier。等价时证明前置请求发生、图片GET/begin/upsert零、source/fp/hash/revision不变；base GET/非法srcset/不安全base失败不能skip；集合扩大必须继续GET/publish。

### SECIMG-001：有限直接候选与精确srcset语法

- 三类输入为 img/src、img/srcset、picture内source/srcset，所有候选必要且取并集；不按屏幕宽度、media/type/sizes或w/x选一张，不把picture外source扩为视频/音频下载。
- plan逐条定义ASCII空白、按位置扫描的URL/descriptor/逗号边界、允许单尾逗号、无descriptor隐含1x、正整数w/正有限十进制x及允许指数语法；混组/重复数值/多个descriptor/未知后缀等非法输入明确失败。
- `%2C`/`%20`等编码在候选分界后进入同一URL owner解码。原始URL内部逗号、空候选与data分界歧义失败，不能简单split后丢候选；有限明确data形式不产生远端资产，也不能吞掉后续URL。
- 全部输入复用同申报URL/canonical去重/单组件名称与collision真源；没有通用解析框架、新公开候选schema或其它image标签。无src的img/srcset与picture/source分别覆盖fresh、正式旧publication普通补齐、任一候选GET失败保留，断言完整F/hash/size/fp/仓储寻址。

### SECIMG-002：首base的真源及安全URL解析

- 取全文第一个带href的base，包括空/空白/无值href；无href不占位，后续base不覆盖，首个不安全base也不能跳过。先收集全文再解析候选，base在img后同样生效。
- `D`是实际HTML的archive URL，base相对于D用标准URL解析；同申报目录/文件的尾斜杠、relative/root/absolute及query/fragment都明确。候选先按base解析，之后才去query/fragment确定归档身份。
- 外站/跨申报/非法base+相对候选typed发现失败，含root/query/fragment相对形式；不向外站请求，不回退归档根、不采用后续base。显式绝对与协议相对图片独立校验，合法同申报绝对URL不受base重写。
- 最小合成owner表给出完整canonical URL集合与失败reason，覆盖首空/多个base、file/dir、root/query/fragment、base点段、路径组件前缀假匹配、编码边界、不安全base+绝对候选。成功核对完整F与正式仓储读回；发现失败零图片GET/begin/source mutation且旧publication不变。真实TSM无base/srcset，不增加伪真实输入。

### 保留的方案与最小性

- 保持1个行为S1；SEC版本仍为v1.2.0→v1.3.0；完整F复用原 `build_source_fingerprint`、正式source upsert/文档版本/processed规则，batch外预取及identity/reset/materialize/upsert/commit/rollback方案不变。
- Phase A/B均复用当前版本资格；本地rebuild不授予新下载版本、仓储merge保留原版本/缺席状态的方案不变。
- 独立临时base、正式baseline CLI播种旧来源、指定当前CLI新下载/普通补齐/重复/故障/逐图hash/诊断的真实矩阵与准确argv保留。增加真实输入结构确认，合成base/srcset仅作为owner验证，不能伪装真实TSM证据。
- 子目录候选继续 `html_image_reference_invalid`，给明确“子目录/单文件名/未发布/已有来源保持”诊断；不取basename、不改HTML、不静默complete。无真实目录图证据及单组件public asset contract是现有裁决边界，不重开goal。
- 四项修订分别闭合成功信号1/3的实际集合、信号2的阶段/升级及信号4的测试边界，不改变五成功信号、不扩为CSS/JS递归/浏览器/OCR/新schema或元数据修复目标。未发现直接代码事实使四项修订无法在既有owner边界实施。

## Validation

- 本轮为纯文档fix：核对四finding的allowed/interface/候选/base/状态/test/docs/alignment/residual一致性，检查两artifact whitespace、必要条目与保护文件零改动；tracked生产代码/测试diff及index diff为空。
- 保护范围核对：goal/control、两份原review、总控review及remote-preflight的SHA-256前后相同；真实fixtures未写入；原业务workspace只读且本轮未访问。唯一写入为上述两artifact。
- 实际文档检查：`python3` stdin检查两artifact尾换行/无尾空白/code-fence配对、1个S1、focused的earnings文件、四finding/修复状态、必要规则/全部residual分类及旧窄范围文本移除，退出0（`artifact_structure_whitespace_alignment=pass`）。同一次检查用标准库 `urljoin/urlsplit` 核对空/相对/query-relative/file-base query/fragment/base点段的6个合成规则，全部断言通过；这不是生产parser测试。`git diff --exit-code`、`git diff --cached --exit-code`及whitespace检查均退出0，6份保护artifact前后hash相等。
- 实施命令在plan中仍明确先 `source .venv/bin/activate`；focused新增earnings文件，broad pytest/四生产文件各>=80% coverage/全仓pyright，以及opt-in真实CLI矩阵保留。本轮没有运行这些代码测试、baseline、coverage、pyright、网络下载或故障注入；总控已有baseline证据不计为本次修复验证。
- 未读取、输出或保存UA值；未来真实验证仍只内存传递既有literal，证据只保存配置布尔值，不保存env/headers。没有创建commit或外部变更。

## Docs decision

- 本轮只更新plan与本文，不修改README。实施后按各README职责更新fins/tests/root，先复核其约束。
- fins写直接三类候选/有限srcset/首base/共享边界、版本资格/空fp晚期skip及必要失败原子保留；tests说明合成owner矩阵、META测试bytes与历史raw保持及真实CLI的各证明范围；root给普通补齐准确命令及平铺/子目录诊断、失败定位/rebuild边界，不把内部解析类型暴露给最终用户。
- 分层/装配未变化，不更新dayu/README或其它业务层README。子目录不能建议basename/手工补文件作为补救。

## Residual risks / owner / destination

分类只说明归宿，不是风险消除或S1已实施；`covered by later approved slice` 指plan经re-review接受后执行的S1。

| ID / 风险或未覆盖项 | 分类 | Owner / destination path / 非阻塞依据 |
| --- | --- | --- |
| PF1 四accepted finding的计划缺口 | fixed in current slice | plan fix worker；destination：`docs/plans/sec-html-image-assets-plan.md`、本文。仅文本闭合，初步已修复待re-review，最终review证据由总控产生，不以分类放行gate |
| R1 两例27张去重图全部远端GET/hash/限流可用性尚未验证 | covered by later approved slice | S1实现worker/总控；destination：`tests/fins/test_sec_html_image_assets_real_cli.py`、`docs/validation/sec-html-image-assets-implementation.json`。验收必要，若无法完成则阻塞实施验收，不降标准 |
| R2 srcset/base/URL/name、空fp失败优先、earnings迁移、版本/rebuild/事务/取消/竞争尚未实现 | covered by later approved slice | SEC downloader/workflow/rebuild及测试owner；destination：plan allowed测试、S1 implementation/code-review artifacts和implementation JSON。当前只修plan，无实现pass证据 |
| R3 HEAD策略/validator稳定性，快跳不探测远端新变化 | assigned to later work unit | SEC transport/workflow维护者；destination：独立“远端重校验/指纹策略”work unit。沿已有算法/overwrite，不扩大本目标；当前逐次descriptor fp及byte hash分别验证 |
| R4 子目录地址契约、更宽srcset/歧义data、CSS/JS/browser、legacy非UTF-8能力 | assigned to later work unit | SEC downloader/Fins storage维护者；destination：有真实失败样本的独立“目录资产地址契约/其它HTML资源解析”work unit。SECIMG-003已rejected-with-reason，暂无真实目录证据；本S1只验证边界typed失败/旧publication保留，不设计路径映射/schema；三类有限候选与base已纳入S1，不延期 |
| R5 外站/跨申报/OCR/数值提取 | assigned to later work unit | 后续需求提出方；destination：独立需求work unit。已确认非目标，当前零越界请求；不安全base的相对引用明确失败 |
| R6 200非空非图片内容、HEAD/GET间validators或bytes变化 | assigned to later work unit | SEC transport维护者；destination：独立“响应内容校验/validator同响应身份”work unit。沿现有raw transport契约，不新增图像校验；同一HTML预取bytes决定依赖集合仍由S1保障 |
| R7 真实bases未运行processor/LLM，不证明OCR/财报数值/真实processed重算 | assigned to later work unit | Fins processor/分析能力维护者；destination：独立图片读取/OCR验收work unit。当前只承诺正式来源可寻址，processed标记由S1真实Fs owner测试验证 |

Blocking open questions：**无**。必要真实验证仍待S1，尚不能称已通过；若实现或网络直接证据与plan矛盾，交总控裁决，不猜fallback、不改筛选或goal。

## Completion / handoff

- Completion status：计划修订交付完成；四accepted finding初步 **已修复待 re-review**，未实施、未review pass、未commit/push。
- 当前worker任务到此交接；下一个未完成Gateflow入口为 `re-review`，由总控登记及执行，未修改control。接受计划checkpoint、S1、后续review/deepreview/draft-PR/final-closeout仍按固定顺序。
- Artifact paths：`docs/plans/sec-html-image-assets-plan.md`、`docs/plans/sec-html-image-assets-plan-fix.md`。
