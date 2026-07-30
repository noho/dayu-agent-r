# WU-CLI-INIT-01 Plan Review Adjudication

## Gate metadata

- Work unit：`WU-CLI-INIT-01`
- gate：`plan review adjudication`
- Controller：AgentController
- 日期：2026-07-30
- reviewed plan：`docs/reviews/wu-cli-init-01-plan-codex.md`
- independent reviews：
  - `docs/reviews/plan-review-20260730-140814.md`（AgentDS）
  - `docs/reviews/plan-review-20260730-141028.md`（AgentMiMo）
- decision：`fix-plan-and-rereview`

## Controller 直接裁决

### A01 — reset Enter / EOF finding

- 来源：AgentMiMo Finding 01。
- 裁决：`rejected-as-misread`。
- 理由：plan §6.4 已明确：
  - reset Enter/No -> `CANCELLED_SUCCESS(0)`；
  - reset EOF -> `FAILURE(1)`；
  - reset SIGINT -> `INTERRUPTED(130)`。
  这与 accepted oracle 一致。当前旧测试把 EOF 断言为 0 是需要迁移的偶然行为，
  不是 plan 自相矛盾。
- plan fix：只需把需要改写的现有 EOF 测试精确列入 S2，避免 implementation agent
  漏改；不改变状态机。

### A02 — persistence confirmation 的 No / EOF

- 来源：AgentDS Finding 01、AgentMiMo Finding 05。
- 裁决：`accepted-clarification`，正式语义为：
  - required secret batch 的持久化确认选择 No/Enter -> exit 1；
  - 该次 init 未完成，workspace 零发布；
  - EOF -> exit 1；
  - SIGINT -> exit 130。
- 理由：reset No 是取消一个 destructive reset，原 workspace 仍是有效完成态；
  required secret persistence No 则使所选 provider 的 init 前置条件没有完成，不能把
  “workspace 未初始化”报告为成功。现有
  `test_required_secret_refusal_stops_before_transaction_publication` 也已断言 exit 1。
- plan fix：在状态机和测试中写明两种 confirmation 的业务状态不同，不以表面对称性
  改退出码。

### A03 — 非 init `--config` 回归面

- 来源：AgentDS Finding 02。
- 裁决：`accepted`。
- plan fix：S1 对 `prompt`、`interactive`、`session resume` 至少参数化覆盖
  command 前与 command 后的 `--config`，断言 `config_dir` 精确映射；同时覆盖 init
  两种位置均 parser exit 2。

### A04 — execution profile minimum 的 typed 加载边界

- 来源：AgentDS Finding 03。
- 裁决：`accepted`。
- plan fix：指定唯一生产 API、加载时点、异常边界和测试。不得 loose-read JSON、
  硬编码 262144 或在加载失败时 fallback。package execution profile 是 init
  publication 的只读源资产；其内部 schema 无效时 fail closed 是产品错误，提前失败
  可以接受，但必须给出脱敏、可操作诊断且零 publication。

### A05 — versioned publication manifest 不能运行时自证

- 来源：AgentDS Finding 04。
- 裁决：`accepted-with-boundary`。
- plan fix：manifest 是用户确认行为的 checked-in、版本化快照；正常 smoke 必须拿
  实际树与冻结快照比较，禁止从当前实际树动态生成 expected 后再自比。若提供维护态候选
  生成，只能生成待审阅的新版本，必须经新 oracle/scenario version 和用户确认后生效。

### A06 — ordinary-file cleanup dispatch

- 来源：AgentDS Finding 05。
- 裁决：`accepted`。
- plan fix：明确扩展现有 private cleanup owner 的 typed expected identity/shape
  dispatch；regular file 与 ordinary directory 都先做 containment、identity lock、
  same-parent quarantine，quarantine 后分别 no-follow unlink / fd-safe recursive
  delete。不得在调用方复制安全协议或新增第二套 mutation helper。

### A07 — PRESERVE root config 补齐

- 来源：AgentMiMo Finding 02。
- 裁决：`already-covered-needs-precision`。
- 理由：plan S4 已要求逐个补齐 `config_file_names()` 且已有文件零改写；finding
  描述的是当前实现缺口，正是 S4 的修复目标。
- plan fix：把调用级步骤写得更精确：先 copytree 用户 config，随后逐个检查 staged
  root config；只从 package 复制缺失文件，再补 prompt，最后只改模型 owner 字段。

### A08 — DeepSeek 默认引用影响清单

- 来源：AgentMiMo Finding 03。
- 裁决：`accepted`。
- plan fix：S3 在改默认引用前运行并记录精确 `rg` inventory，区分 package-default
  偶然断言与显式 DeepSeek fixture；只迁移前者，不机械替换 provider-specific tests。

### A09 — primary default selection / runtime fail-closed

- 来源：AgentMiMo Finding 04。
- 裁决：`rejected-as-required-owner-check`。
- 理由：PRESERVE 明确保留用户编辑，因此 init publication 正确并不能保证用户后续没有
  制造主 scene / compactor family drift。业务 contract 要求实际运行时同源；Service
  assembly 是两个 selection 汇合且 Host 尚未打开的最早 owner boundary。使用无
  invocation override 的 primary default 与 compactor 比较，既避免把单次
  `--model` 错当 drift，也能在真实运行前 fail closed。
- plan fix：补充上述触发场景和必要性说明；不删除该校验。

## Plan fix acceptance criteria

1. 只修改 plan artifact，不修改生产代码、测试或 accepted oracle。
2. 纳入 A01-A09 的裁决，并保留用户冻结的 compactor/model/provider 同源语义。
3. 明确 existing test migration、typed profile load API、manifest 防自证边界与 cleanup
   dispatch。
4. `git diff --check` 通过。
5. 修改后重新交给 AgentMiMo 与 AgentDS 独立 plan rereview；两路都没有未关闭的
   material finding 后，plan gate 才能 pass。

## Next entry point

AgentCodex 执行 plan fix；不得进入 implementation。

## Rereview adjudication

### Inputs

- `docs/reviews/plan-review-20260730-142447.md`（AgentDS：
  `pass-with-risks`）
- `docs/reviews/plan-review-20260730-142807.md`（AgentMiMo：`pass`）

### R01 — PRESERVE copytree symlink 行为

- 来源：AgentDS N01。
- 裁决：`accepted`。
- plan fix：PRESERVE 继续复用当前
  `shutil.copytree(..., symlinks=True, ignore_dangling_symlinks=False)` 语义，
  不得 follow symlink；测试证明 staged tree 保留 symlink shape，随后由 no-follow
  validation 拒绝，不能把外部目标复制成 regular file。

### R02 — cleanup shape 判定

- 来源：AgentDS N02。
- 裁决：`accepted`。
- plan fix：shape 必须从同一次 no-follow identity/stat 的 mode 通过
  `stat.S_ISREG` / `stat.S_ISDIR` 判定；禁止 `Path.is_file()` /
  `Path.is_dir()` 或其它 follow-symlink API。

### R03 — PRESERVE 的 target execution profile

- 来源：AgentDS N03。
- 裁决：`accepted-as-current-plan-fix`，不 defer。
- 理由：PRESERVE 的业务 contract 是保留有效 workspace
  `execution_profiles.json`。因此 dynamic model context 的直接上游 minimum 必须来自
  本次 init 成功后将实际生效的 target typed profile，而不是无条件来自 package。
  否则用户 workspace profile 的 minimum 高于 package 时，context 输入会在当前步骤被
  错误接受，之后才在 staging/runtime 失败，违反可恢复 context 错误原步骤重试的 oracle。
- plan fix：
  - FIRST / OVERWRITE / confirmed RESET：读取 package execution profiles
    （`workspace_config_dir=None`）；
  - PRESERVE：以真实 workspace config dir 调用 layered typed
    `load_execution_profiles(...)`；缺失文件按 loader 的 package layering 规则取得
    package default，存在但非法的 workspace profile fail closed 并提示
    `--overwrite`，不得回退 package 掩盖损坏；
  - minimum 取 target typed default profile并显式下传；
  - tests 覆盖 PRESERVE workspace minimum 高于 package 时，较低 context 在原步骤
    重试；缺失 profile 使用 package layer；非法 profile fail closed。

### R04 — argparse post-parse 可达性

- 来源：AgentDS N04。
- 裁决：`no-plan-change`。
- 理由：命令后 `init --config` 由 init subparser 自身 parser error 2，命令前
  `--config ... init` 由 post-parse init-specific rejection error 2；两条路径无需
  都经过 post-parse。S1 六个正向和两个反向 case 足以证明公共契约。

### Rereview gate decision

`fix-plan-and-rereview`。AgentCodex 只修 R01-R03；随后 AgentMiMo 与 AgentDS 再做
独立 material-finding rereview。不得进入 implementation。

### Final rereview

- `docs/reviews/plan-review-20260730-143852.md`（AgentMiMo）：`pass`，无 material
  finding。
- `docs/reviews/plan-review-20260730-144048.md`（AgentDS）：`pass`，无 material
  finding。
- R01-R03：`已修复`。
- A01-A09：`已修复`或按 Controller 理由 `rejected-with-reason`，无未决项。
- residual risks：外部 provider 可用性、Windows junction/reparse 与 Custom
  显式输入均已在 approved plan 分类；无 unclassified residual risk。

Final plan review decision：`pass`。

Next entry point：`accepted plan commit`，随后
`implementation S1 — CLI public parser contract`。
