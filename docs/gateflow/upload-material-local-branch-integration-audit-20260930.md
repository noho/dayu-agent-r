# 本地开发成果汇入 PR #197 的核对记录

日期：2026-09-30。目标分支 `codex/upload-material-oracle`；用户持有 `main` 的最终合并权。本次只在目标分支集成，不改 `main`。原 PR head 为 `ab5893ce`，安全引用 `refs/safety/upload-oracle-before-local-integration-20260930` 指向该提交。

## 已核对的提交

- `codex/upload-material-dotfile`、`codex/upload-material-o03`、`codex/upload-material-o20` 的各三个本地独有提交，`git cherry -v` 对当前 PR head 均报 `-`：补丁等价内容已经进入 PR，不能重复合并旧快照覆盖后来修复。
- `codex/upload-material-o11` 的 `9141b5e9`、`cea46f5f` 在目标分支分别重新提交为 `c4c83891`、`e698895a`；受影响 687 项测试通过、项目 pyright 0。
- `codex/upload-material-assets` 的已接受计划 `1453a659` 在目标分支重新提交为 `46d4978f`；`codex/upload-material-o12` 的已接受计划 `b201d9f3` 重新提交为 `359f907f`。这两项是计划与评审证据，不能冒充产品实施闭环。

## 资产规划未提交实现

源工作树 `/private/tmp/dayu-upload-assets` 的 56 个变更文件已按内容哈希保全至 `/private/tmp/dayu-upload-assets-safety-20260930.tar.gz`，清单在 `/private/tmp/dayu-upload-assets-safety-20260930.json`。原工作树和分支仍保留。34 个已跟踪文件通过三方补丁合到目标分支工作树，22 个未跟踪文件复制到目标分支工作树；冲突仅 `dayu/cli/commands/fins.py`、`dayu/fins/README.md`、`tests/fins/test_fins_ingestion_runtime.py`，已按当前 #198/O11 与资产 handoff 语义人工合并。初次组合测试 757 通过、2 失败，根因是 CLI 新准入构造点误用去空白函数，破坏 O11 日期原文校验；已在 CLI 输入投影处改用既有 `_optional_material_date_text`，对应回归已通过。

此批代码仍是 **未通过最终 code gate 的候选**。F15～F20 与集成审查 I-R1～I-R4 已有主工作树修复候选，状态与 runner 失败记录见 `docs/gateflow/upload-material-assets-s1-code-review-adjudication-20260929.md`。总控在主工作树独立验证受影响及相邻 14 文件 **1075 passed、1 skipped**，全量 pyright **0 errors**，diff check 通过。相同代码已冻结到两份独立审查工作树，56/56 文件 SHA 匹配；MiMo 与 ds-flash 同版复审在途。须完成结构化结果核验、总控裁决后才能提交并推送 PR #197。

## 其它工作树

其余 WU 分支大多停在旧共享基线 `8d8d494f`，未形成独有代码提交；多个工作树留有未提交的 goal、plan、review 文档，不能把这些候选当作已完成产品代码。detached review 工作树的代码快照要与当前 PR 按内容比较，过时快照不得覆盖当前 owner。全部分支与工作树暂不删除。若后续确认某份未提交文档是已接受 gate 的唯一证据，再按其 gate 状态集成并记录来源。

为防临时工作树消失，已将 163 份 PR 原缺失文档逐文件核对哈希：16 份已随接受的 O11/O12/资产计划进入目标分支，另 147 份无覆盖复制到目标工作树。来源、原始 SHA-256 与复制状态见 `docs/gateflow/upload-material-local-evidence-preservation-20260930.json`。复制后资产 S1 审查裁决文件又追加本轮事实，因此当前哈希与原始索引不同；其余 162 份仍逐字匹配，原件继续保留在索引指定源路径。该索引只表示原始证据获保存，**不表示其中任何候选/失败 review 获 gate acceptance**。`stash@{0}` 是此前 PR 同步前的安全快照；`stash@{1}` 属独立 WU-CM-01，均未应用或删除。

## 待完成

1. 资产规划最终双路同版 review、总控裁决和目标分支提交/推送；若有新 finding，先登记、owner 修复、重新冻结复审。
2. 复核其它 dirty 工作树是否存在 PR 未收录的**已接受** gate artifact；候选/失败证据保存在原工作树，不能伪称闭环。
3. 目标分支最终全量 `git diff --check`、受影响测试、pyright、PR head 读回；`main` 必须仍为 `fac32ecbf`。

## 2026-09-30 再盘点与实施顺序约束

- 用户进一步明确：**先把其它分支已有成果全部并入 `codex/upload-material-oracle` 并同步远端，再实施任何尚未实施 WU**。本次资产 S1 的 I-R 修复仅处理待整合代码自身 review finding；O16、material 文件状态、CNInfo 单日与其它尚未实施 WU 不在整合时顺带启动。
- 重新逐个读取 `/private/tmp/dayu-*` 相关工作树的 `git status --porcelain -uall`。除 `/private/tmp/dayu-upload-assets` 的 40 个产品/测试/README 工作文件及 16 个文档文件外，所有有名 WU 工作树均无额外未提交产品代码；其 dirty 内容仅为计划、裁决和审查文档。资产原 56 份文件有压缩包和 SHA 清单，已合入目标主工作树候选，未删原树。两个旧 `dayu-issue198-pr197-r2-*` detached 审查树的 `dayu/runtime/log.py` 与 `tests/runtime/test_log.py` 虽显示 dirty，但逐字节与当前目标主工作树一致；不是遗漏代码。其余 detached review 快照不是产品开发目标，保留不覆盖当前代码。
- 对其它 WU dirty docs 逐文件比较当前目标树：没有缺失路径；仅旧 #198 审查裁决、旧 #198 S2 裁决和旧交接 prompt 共数处同名内容差异，当前目标树包含更晚的验收/推送/交接事实，不能用旧快照覆盖。原始来源和 SHA 已在 `upload-material-local-evidence-preservation-20260930.json` 保留。
- 分支提交复核：`codex/issue198-pr197-integration`、`codex/issue198-s2` 已是目标 HEAD 祖先；dotfile/O03/O20 的独有提交 `git cherry` 为补丁等价；O11/O12/资产已按前述冲突/审查受控重放。O11 最后原提交因与当前集成后的 CLI 所有权修订不具相同 patch-id，使用重放提交和 owner 测试核对实际语义，不据 patch-id 缺失推断代码遗漏。
- 主工作树最新资产候选由总控独立验证 **1376 passed、1 skipped**、pyright **0 errors/0 warnings**。同版 63 文件冻结到 `/private/tmp/dayu-upload-assets-review-r3-mimo-20260930` 与 `/private/tmp/dayu-upload-assets-review-r3-dsflash-20260930`，每文件 SHA 相同，排序 manifest SHA-256 为 `35d417892eea0f2a50c5d24a37027277f28d03e0787ccb794af6782ff38d146f`；MiMo/ds-flash 已预检 `setup_status=ok` 并用各自绝对 cwd、独立输出派发，在途。未通过复审前不提交或推送。
- **后续范围纠正**：r3 冻结版包含 Sol 提前实施的 O05 form/name 前置必填，与本节“先整合后实施”冲突；该 1376 项绿测仅证明旧候选技术上通过，不构成范围验收。两路 r3 审查已由总控 SIGINT 停止、各 exit130，冻结工作树和 runner 输出保留，不能计 gate pass。I-R15 已改 `deferred-to-UM-O05`；Sol 正在主工作树撤出 O05 改动并保留 I-R17/O11 防绕过修复，之后重新独立验证与同版双路审查。详见资产 adjudication。
- O05 撤出后的主工作树候选经总控独立扩展验证 **1374 passed、1 skipped**、pyright **0 errors/0 warnings**。r4 复审因漏复制 O05 goal 文档而取消（两路 exit130，均不计 gate）。r5 两份全新审查树已核对 65/65 文件 SHA 与全部必读相对文件，manifest SHA-256 为 `3ccfc2a2f57db9e2426a021150b53819c9125dc0bb3dcfa2b39e5a6891137fbe`；MiMo/ds-flash 双路在途。O05、O16、material 文件状态和其它未实施 WU 均继续排在分支整合与远端同步之后。
- r5 ds-flash 有效、MiMo 内容有效但一条系统 Python 探针 exit1 导致严格 Agent 失败；总控据直接 owner 路径接受 I-R19～I-R22（死导入、测试死条件、裸计划绕过、控制名优先级）。Sol 修复候选经主工作树独立 **1386 passed、1 skipped**、pyright **0 errors/0 warnings**。r6 两份全新快照 68/68 文件 SHA 相同，manifest SHA-256 `dfc9af564931b07710b4ba0261f154ed61dd9d0d5ffe8501525a42fd3b4bd7f7`，必读项目文件齐全，MiMo/ds-flash 同版复审在途。`git ls-remote github` 与 `gh pr view 197` 当前均仍指旧 head `359f907f`（PR OPEN/draft/base main）；主 `HEAD` 同为该值，`main` 仍 `fac32ecbf`，安全 ref 仍 `ab5893ce`。资产代码和本轮归档文档尚未提交/推送。
- 总控又复算 `upload-material-local-evidence-preservation-20260930.json` 的 **163** 条来源 SHA：源文件全部存在且仍与原索引逐字一致；目标主工作树 163 个对应路径均存在，只有持续追加审查裁决的 `upload-material-assets-s1-code-review-adjudication-20260929.md` 当前 SHA 不再等于原始归档版，其原件与原始 SHA 仍保留。这保证历史未提交文档没有因本轮整合丢失，也不把旧候选评审误称已过 gate。
- 资产 S1 r7 冻结快照 71/71 SHA 一致；ds-flash 有效复审新增 I-R27/I-R28 低项，已登记并修复；MiMo 旧快照内容零新项，但六条非零命令和 router stderr 使严格结果失败。总控对修后主树 17 文件矩阵 **1399 passed/1 skipped**、全量 pyright **0 errors/0 warnings**。修后 r8 冻结到 `/private/tmp/dayu-upload-assets-review-r8-mimo-20260930`、`/private/tmp/dayu-upload-assets-review-r8-dsflash-20260930`，74/74 文件 SHA 同主树，排序 manifest SHA-256 `04c8e41da9b06479803632c58f6364d12883cc167b8453c2154b8417d461282b`；MiMo 与 ds-flash 的 Claude runner 绝对 cwd、独立输出、stderr、canary 预检均 `setup_status=ok`，并行复审在途。未提交/推送，O05/O16/file-state/其它未实施 WU 不启动。
- r8 两路结构化均有效；ds-flash 发现并经总控核证的 I-R29 死 canonical ticker 参数已在主树最小删除，MiMo 同版内容无其它新项。总控在 I-R29 修后再次独立验证 **1399 passed/1 skipped**、全量 pyright **0 errors/0 warnings**。r9 冻结到 `/private/tmp/dayu-upload-assets-review-r9-mimo-20260930`、`/private/tmp/dayu-upload-assets-review-r9-dsflash-20260930`，77/77 文件 SHA 同主树，排序 manifest SHA-256 `946fd54f2f78802801e92451b4d1a9764340c3a3b50f462343bbdd268ffba094`；两路 Claude runner 显式绝对 cwd、独立 JSON/stderr/canary，预检均 `setup_status=ok` 且并行在途。未提交/推送、未动 main、未实施其它 WU。
- r9 MiMo 与 ds-flash 双路最终均 exit0、Claude JSON success/completed、canary 匹配、stderr 仅精确白名单模型元数据提示；报告分别归档 `docs/reviews/code-review-20260930-130612.md`、`docs/reviews/code-review-20260930-130001.md`，两者对 I-R29 三行删除和指定回归均零新 material finding。总控据源码、报告、1399 passed/1 skipped、pyright0 判本次资产待整合代码 gate 通过；仍须完成目标分支的 staged diff、commit、push、PR head 读回。远端提交前最后读回 PR #197 为 OPEN/draft、head `359f907f`、base `main`，`main` 为 `fac32ecbf`。
