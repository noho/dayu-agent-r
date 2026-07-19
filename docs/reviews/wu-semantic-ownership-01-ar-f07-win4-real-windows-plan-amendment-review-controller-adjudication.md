# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Real-Windows Plan Amendment Review Controller Adjudication

## Result

`PASS_WITH_ACCEPTED_PLAN_FINDINGS / ACCEPTED_OPEN=4 / BLOCKER=0 / PLAN_FIX_REQUIRED / IMPLEMENTATION_NOT_AUTHORIZED`

## Identity and reviewed target

- Timestamp：`2026-07-20 05:45:50 +0800`。
- Work identity：既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella remediation continuation / `AR-F07 WIN4`；不是新 WU。
- Reviewed plan：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`，1045 lines，SHA-256
  `79e984d6fe5fe1ce08cd1affc60b241f9691c6ba94b9ec3e75850676b9d61bb4`。
- Frozen remote evidence target：`b85def887e72dc69e972f42a82a18989523f8634`。
- AgentMiMo review：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-mimo.md`，SHA-256
  `6782a69f3fa47e895c47321f3c8674050357afea0a48cede474682617b9aca36`。
- AgentDS review：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-review-ds.md`，SHA-256
  `7df6dbf7e8b12b705611b85f97a35fe9655b96b39e124f02716100ba5b8e7e91`。

两路 reviewer 均接受 root cause、owner、精确两个 slices、allowlist、验证矩阵、remote lineage、security 与 deferred
边界；没有 blocking finding 或 open question。Controller 依据直接 protocol、当前 test fixture 与 Python stream 行为接受以下
四项窄 plan-only 修正。它们不授权 implementation。

## Accepted findings

### WIN4-RW-PR-F01 — Source snapshot 必须使用 public context-manager lifecycle

- 来源：AgentMiMo F-01、AgentDS DS-F02；合并为一个 canonical finding。
- 裁决：`ACCEPTED / PLAN-ONLY / LOW`。
- 直接证据：`SourceSnapshotProtocol` 显式定义 `__enter__` / `__exit__`；当前 plan 只写“读取 snapshot”，存在实现者直接持有
  返回对象而不进入生命周期的歧义。
- 必须修复：§13.2.1 与相关 owner-test 文本必须明确使用
  `with source_repository.read_source_snapshot(..., materialize_files=False) as snapshot:`，并且只在 `with` 块内读取
  identity、source kind、primary filename 与 descriptors。不得在 CLI test 重复测试 Fins protocol 自身的 close-after-use
  内部语义。

### WIN4-RW-PR-F02 — 既有 getpass tests 必须显式、确定性地选择 TTY path

- 来源：AgentMiMo F-02、AgentDS DS-F01；合并为一个 canonical finding。
- 裁决：`ACCEPTED / PLAN-ONLY / MEDIUM`。
- 直接证据：当前 `_GetpassSequence` 只 monkeypatch `getpass.getpass`；新增 helper 先查询 `sys.stdin.isatty()`，因此测试运行器
  的 ambient stdin capability 会决定 mock 是否被调用。§13.4 已识别需要“明确处于 TTY path”，但未冻结 fail-closed test
  contract。
- 必须修复：plan 必须要求受影响既有 tests 把 production 实际读取的 `sys.stdin` 替换为 test-owned、严格 typed TTY fake；
  `isatty()` 恒为 `True`，`readline()` 若被调用立即以 assertion 失败。不得 mock production `_read_secret_input`，不得只修改
  `sys.__stdin__`，不得依赖本机/CI ambient TTY。redirected owner tests继续用真实 `io.StringIO` 或等价严格 typed stream，
  显式返回 `isatty() == False`。

### WIN4-RW-PR-F03 — 两种 EOF 表现必须显式收敛

- 来源：AgentMiMo F-03。
- 裁决：`ACCEPTED / PLAN-ONLY / LOW`。
- 直接证据：TTY `getpass.getpass()` 的 EOF 是 `EOFError`；redirected `readline()` 的 EOF 是空字符串。仅写“两个 EOF
  收敛”仍要求 implementation 自行推断不同输入形态。
- 必须修复：§13.2.2 明确 TTY path 只捕获 `EOFError` 并映射为既定 value-free `CliInitOperationError`；redirected path
  把 `readline() == ""` 映射为同一错误。两路都不得把 prompt、secret、raw buffer 或 raw exception text 投影到用户输出；
  `KeyboardInterrupt` 仍不捕获、不改写。

### WIN4-RW-PR-F04 — CR 只能作为已移除 LF 的前缀被剥离

- 来源：AgentDS DS-F03。
- 裁决：`ACCEPTED / PLAN-ONLY / LOW`。
- 直接证据：§13.2.2 的“再移除其前单个 `\r`”意图是处理 `\r\n`，但实现者可能把它写成两个无条件 suffix checks，
  从而删除没有 `\n` 的孤立 trailing `\r`，与“其它字符原样保留”冲突。
- 必须修复：plan 明确记录是否实际移除了末尾单个 `\n`；只有该条件成立且新末尾是单个 `\r` 时才继续移除它。孤立
  trailing `\r` 原样保留。owner tests增加 bare-CR preservation case；禁止使用会删除任意数量尾随换行字符的 `rstrip`。

## Rejected or no-action observations

1. 不接受在 CLI test 重复实现 Fins snapshot close-after-use 的 protocol-owner tests；当前 finding 只要求正确消费既有 public
   context-manager contract。
2. 不接受直接 monkeypatch production `_read_secret_input` 作为既有 orchestrator tests 的修复；这会绕过正在验证的 owner
   boundary。
3. 不接受修改 workflow、`tests/cli/test_init_smoke.py`、setx、Fins production、CLI output 或引入 Windows/GitHub identity
   分支；两路 review 没有提供要求扩大 allowlist 的直接证据。
4. AgentDS 对 publication guard、Windows lock 与 old-Mac 输入的具体后果描述不作为新的 durable product fact；Controller 只接受
   protocol lifecycle与字符保留契约本身。

## Security and scope disposition

- Config 与 Host internal SQLite/EventLog继续属于 trusted-local domain；本 finding fix不新增 secret storage、redaction 或统一
  authorization infrastructure。
- Tool Trace/audit、public/LLM-facing/operator diagnostics继续禁止 API key/header 明文。
- Issue 142、151、175、177、178及Web/WeChat/render均未进入当前 implementation。
- Gemini低预算仍是`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。

## Next gate

只允许 AgentCodex 在既有 plan 中修复 `WIN4-RW-PR-F01..F04`，并新增 plan-fix evidence。不得修改 product、test、README、
workflow 或 design，不得 stage、commit、push、dispatch 或进入 implementation。Controller validation后必须由AgentMiMo与AgentDS
对完整 fixed plan并发 re-review；四项 finding只有在双路完整 re-review与Controller最终裁决后才能关闭。
