# WU-SEMANTIC-OWNERSHIP-01 / R12 S1 Code Re-Review Controller 裁决

## 1. Gate 与输入

本文裁决现有 umbrella WU `WU-SEMANTIC-OWNERSHIP-01` 的 R12 S1 fixed cumulative
tree；不是新 WU，不授权 S2/S3、stage、commit、aggregate、push 或 PR。

- AgentMiMo corrected re-review：283 lines / 12,597 bytes / SHA-256
  `3af83fc542c341f0de3ed4c06db957ea556e7a7a7f5fbcbe7b7767d0f1953a8a`。
- AgentDS corrected re-review：477 lines / 24,013 bytes / SHA-256
  `3f51cfb6b29ee2e9bd6790b378e70c469e1f3f08133add9c17f8919f4d47d38b`。
- 两路均完整读取累计 S1 tree，独立返回 PASS、关闭 `R12-S1-CR-F01`、新 product
  finding `0`、blocker `0`。

## 2. 既有 finding 裁决

### R12-S1-CR-F01 — CLOSED

采纳两路 closure。合法 begin/end/both marker value × absent/existing profile 的六个
case 全部成功；九个 malformed case 仍 fail closed；Controller 自己的六个真实 success
和三个真实 rejection smoke 也一致。值拒绝集合、Windows path、catalog SHA、secret-safe
projection 与 whole-batch injection 未漂移。

### Value-object equality — REJECTED / NO FIX（维持）

frozen dataclass 的 value equality 是正确 contract；两路均确认无 identity shim、registry
或兼容层需要。

### MiMo partial-marker/export-name test suggestion — REJECTED / NO ACTION

该 residual 使用的字符串不是完整 Dayu marker；在真实 managed block 内，非法 name 仍由同一
`_parse_export_name()` / allowlist owner 拒绝。现有正反矩阵已覆盖完整 marker 在 value、
普通文本、注释、非法 name 和非法 export shape 的边界。不得为了非业务 partial substring
新增测试驱动分支或延期 accepted finding。

### Windows captured output / `setx` / post-write residuals — CLASSIFIED

- captured output 当前不读取、不记录：observation / no fix；
- `setx` 跨项不可回滚和真实 Windows runner：accepted residual / external runner，仍是
  umbrella release blocker；
- 一般 POSIX 写后校验失败时 profile 可能已替换但不注入、不 publish：accepted plan
  contract，不新增 rollback。

## 3. Controller direct project-instruction finding

### R12-S1-RR-CF01 — ACCEPTED / LOW

Controller 对当前四个 S1 Python 文件运行 AST/docstring contract scan。两个 production
owner 文件为 `0` 缺口；两个本 WU 新增测试文件各有 `16` 个测试函数未完整说明参数、返回值
和异常，共 `32` 个：

```text
dayu/cli/init_catalog.py: 0
dayu/cli/init_environment.py: 0
tests/cli/test_init_catalog.py: 16
tests/cli/test_init_environment.py: 16
```

这直接违反 `AGENTS.md`“函数必须提供完整中文 docstring，至少包含参数、返回值、异常”。它不
改变产品运行时正确性，故分级 LOW；但这些文件是本 S1 新代码，finding 必须在 S1 内关闭，
不得作为后续优化或 residual。

唯一允许修复范围：

- `tests/cli/test_init_catalog.py`
- `tests/cli/test_init_environment.py`
- 新增 `docs/reviews/wu-semantic-ownership-01-r12-s1-code-rereview-fix-codex.md`

修复契约：

1. 为精确 32 个缺口函数补完整中文 docstring；有参数时逐一说明，统一说明返回值，并说明测试
   assertion/fixture/被测边界可能传播的异常语义。
2. 只改 docstring，不改 decorator、参数、测试 body、assertion、fixture、production code、
   test count 或 coverage behavior。
3. 不新增 AST framework、repo-wide linter rule、compat/test shim、README 或其它文件。
4. 修复后同一 AST scan 在四文件上必须为 `0/0/0/0`。
5. 仍须通过 `66` focused tests、两个单文件 coverage、full pyright、scoped Ruff、full Ruff
   exact baseline、diff/staged/scope/source scans。

## 4. Final ledger 与 next gate

- `R12-S1-CR-F01`：closed。
- re-review product finding：`0`。
- Controller-direct accepted/open：`1`（LOW `R12-S1-RR-CF01`）。
- rejected/no-action：value equality + partial-marker test suggestion。
- classified residual：Windows runner/`setx`、captured output、POSIX post-write truth。
- design contradiction：`0`。
- local blocker：`0`。

下一 gate 仅为 AgentCodex 完整 docstring fix，随后 Controller validation 与两路完整 S1
final re-review。S2/S3、commit 和 aggregate 仍未授权。
