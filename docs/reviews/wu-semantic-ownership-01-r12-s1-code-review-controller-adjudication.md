# WU-SEMANTIC-OWNERSHIP-01 / R12 S1 Code Review Controller 裁决

## 1. Gate 与权威

- 本文裁决现有 umbrella WU `WU-SEMANTIC-OWNERSHIP-01` 的 R12 S1 双路完整 code
  review；它不是新 WU，也不授权 S2、S3、commit、push 或 PR。
- Accepted-plan HEAD：`8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`。
- Accepted plan：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，
  608 lines / SHA-256
  `69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2`。
- Controller validation：
  `docs/reviews/wu-semantic-ownership-01-r12-s1-controller-validation.md`，
  166 lines / SHA-256
  `826b11a6caa288c19562b1663b3000448dbdd3ff519ab40971b27f199f9bec19`。
- AgentMiMo review：
  `docs/reviews/wu-semantic-ownership-01-r12-s1-code-review-mimo.md`，
  294 lines / 14,658 bytes / SHA-256
  `4f27c186ac0ec9f439956f5eadf34458dd7f11455d5a8684f57e9d3dfcdc7492`。
- AgentDS review：
  `docs/reviews/wu-semantic-ownership-01-r12-s1-code-review-ds.md`，
  442 lines / 22,891 bytes / SHA-256
  `06094e2704e6f8a42385f77e7d0e0fa56474be40272bfe511948b81958900652`。

## 2. 独立证据结论

三路证据同源且可复现：`EnvironmentPersistenceEntry` 明确允许任意非空且不含
NUL、CR、LF 的值；`_render_managed_block()` 用 `shlex.quote()` 生成合法 export
行；但 `_parse_managed_block()` 用全文 `content.count(marker)` 把 quoted value 中的
marker 子串误当成结构 marker。写后校验发生在 `os.replace()` 之后，因此合法值会形成
“profile 已替换、当前进程未注入、调用却报失败”的半完成结果。

这不是测试偶然行为。值合法性由 typed entry owner 决定，marker parser 只拥有独立 marker
行及其配对结构；它不得从 export value 子串重新推导结构事实。

## 3. Finding 裁决

### R12-S1-CR-F01 — ACCEPTED / HIGH

- 合并来源：AgentMiMo `R12-S1-CR-01`、AgentDS `DS-R12-S1-01` 和 Controller
  validation §5。
- 状态：`OPEN / MUST_FIX_BEFORE_S1_REREVIEW`。
- 严重度：`HIGH`。这是合法边缘输入的稳定 correctness/data-integrity 错误，并且错误发生
  在 profile 已替换之后；但未观察到 secret 泄漏、命令注入、环境注入或 workspace
  发布，故不采纳 `CRITICAL` 分级。
- 唯一 owner：`dayu/cli/init_environment.py` 的 POSIX managed-block parser；测试 owner
  是 `tests/cli/test_init_environment.py`。

必须满足以下修复契约：

1. parser 必须区分独立、完整的 marker 行与合法 shell export value 内的偶然 marker
   子串，不得再用全文 substring count 代替结构判断。
2. 合法值包含 begin、end 或两者 marker 子串时，首次创建与已有单块替换都必须成功；
   写后校验成功后才可整批注入当前进程。
3. 非 export 的普通文本或注释中嵌入 marker、缺配对、逆序、多块、重叠及非法 managed
   block export 仍必须 fail closed。
4. 不得扩大 entry value 拒绝集合；尤其不得把 marker 字样加入 secret 黑名单。
5. 不得增加 parser framework、兼容分支、fallback、下游补偿或 rollback 新协议。
6. 测试必须断言当前失败路径的真实磁盘状态，并证明修复后同一路径成功；不得用 fake
   隐藏 `os.replace()` 后的状态。

允许 AgentCodex 修改的精确范围仅为：

- `dayu/cli/init_environment.py`
- `tests/cli/test_init_environment.py`
- 新增 `docs/reviews/wu-semantic-ownership-01-r12-s1-code-review-fix-codex.md`

`dayu/cli/init_catalog.py`、`tests/cli/test_init_catalog.py`、既有 artifacts、plan、control、
S2/S3 及其它路径均只读。

### Value equality candidate — REJECTED / NO FIX

`InitModelChoice` 是 frozen value object；相同字段值的副本通过 membership、不同字段值被
拒绝是正确 contract。不得引入 identity check、registry shim 或兼容层。

### Windows captured output observation — OBSERVATION / NO FIX

S1 按 accepted plan 使用 binary captured output，production 不读取、不记录其内容；当前无
泄漏证据。未来若增加日志必须另行经过 secret-safe projection，但不构成本轮 accepted
finding。

### Windows `setx` 不可回滚 — ACCEPTED RESIDUAL / OWNER EXTERNAL RUNNER

Windows 多项 `setx` 的系统级不可回滚性是 plan 已声明 residual；本地 deterministic
evidence 不能替代真实 Windows runner。真实 Windows normal-install/run evidence 继续是
umbrella final 的 `PENDING_RELEASE_BLOCKER`，不由本 finding 扩域实现事务协议。

## 4. Gate 结论

- accepted/open finding：`1`（`R12-S1-CR-F01`）。
- rejected/no-fix candidate：`1`。
- observation/no-fix：`1`。
- accepted residual：`1`（Windows runner destination 已明确）。
- design contradiction：`0`。
- local blocker：`0`。

下一 gate 仅为 AgentCodex 修复 `R12-S1-CR-F01`，随后 Controller 完整验证与 AgentMiMo /
AgentDS 并发完整 S1 re-review。S2、S3、accepted commit、aggregate、push、PR 仍未授权。
