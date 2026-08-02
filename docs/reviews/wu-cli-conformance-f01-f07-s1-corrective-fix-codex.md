# WU-CLI-CONFORMANCE-F01-F07 S1/F01 Corrective Fix 记录（Codex）

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- PR：`190`
- Slice：`S1 / F01 — 删除全局 --config`
- Gate：`S1/F01 corrective fix`
- Entry HEAD：`e5b572d44fa86beac8a23413007cc48805c9ba67`
- 分支：`codex/interactive-oracle`
- 状态：`CORRECTIVE FIX COMPLETE — STOP`
- Artifact：`docs/reviews/wu-cli-conformance-f01-f07-s1-corrective-fix-codex.md`

## 动机、直接因果与语义 owner

修复动机成立，严重性评估正确。S1 commit
`a41526ecbf5c1d16c24a19114b0d0e21208d1dd0` 已从
`EntrypointRuntimeRequest` owner contract 删除 `explicit_config_dir`，但遗漏两个
utils typed constructor call site。修复前 focused pyright 直接复现：

- `utils/smoke_cli_init_provider_matrix.py:2386`：
  `No parameter named "explicit_config_dir" (reportCallIssue)`；
- `utils/smoke_host_public_awaiting_entrypoint.py:808`：
  `No parameter named "explicit_config_dir" (reportCallIssue)`。

每个文件均且仅有这一个错误。owner request schema 已正确删除该字段，因此问题不在
owner contract，而在两个调用方未同步。正确修复边界是机械删除过期 keyword；恢复字段、
增加 alias、wrapper、default、loose parsing 或下游补偿都会重新制造已删除语义，故明确
禁止且未实施。

## Scope 与实际修改

Preflight 确认 entry HEAD 精确匹配、分支不是受保护主干且工作树 clean。实际代码改动仅为：

- 从 `utils/smoke_cli_init_provider_matrix.py` 的
  `EntrypointRuntimeRequest(...)` 删除 `explicit_config_dir=None`；
- 从 `utils/smoke_host_public_awaiting_entrypoint.py` 的
  `EntrypointRuntimeRequest(...)` 删除 `explicit_config_dir=None`。

除本 artifact 外，未修改其它生产代码、tests、docs、README 或 registry。未新增测试：
两个修改文件均位于 `utils/`，按项目约束默认无需测试与覆盖率；本次改动也不改变运行时
行为，只令调用方符合现有 typed owner contract。未 stage、commit、push 或操作 PR。

## 验证命令与结果

### Focused pyright

```bash
source .venv/bin/activate
python -m pyright utils/smoke_cli_init_provider_matrix.py
python -m pyright utils/smoke_host_public_awaiting_entrypoint.py
```

两个命令分别得到 `0 errors, 0 warnings, 0 informations`。

### Full pyright

```bash
source .venv/bin/activate
python -m pyright
```

结果：`0 errors, 0 warnings, 0 informations`。

### Compile / import

```bash
source .venv/bin/activate
python -m py_compile utils/smoke_cli_init_provider_matrix.py utils/smoke_host_public_awaiting_entrypoint.py
python -c 'import utils.smoke_cli_init_provider_matrix; import utils.smoke_host_public_awaiting_entrypoint'
```

两个命令均以 exit 0 完成且无输出。

### F01 residue、diff、registry 与 index

- `rg -n 'explicit_config_dir[[:space:]]*=' --glob '*.py' dayu tests utils`：
  零命中；
- `rg -n 'CONFIG_DIR_OPTION_NAME|resolve_explicit_config_dir' --glob '*.py' dayu tests utils`：
  零命中；
- `rg -n 'explicit_config_dir' --glob '*.py' dayu tests utils`：仅命中
  `tests/service/test_entrypoint_runtime.py` 中 owner 级“字段不存在”负向断言，不是实现残留；
- `git diff --check`：通过；
- `python -m json.tool docs/cli_ci_oracles.json`：通过；
- `python -m json.tool docs/cli_ci_scenarios.json`：通过；
- `docs/cli_ci_oracles.json` SHA-256：
  `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`；
- `docs/cli_ci_scenarios.json` SHA-256：
  `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`；
- `git diff --cached --name-only`：无输出，index empty。

两个 registry hash 与 S1 冻结基线一致。

## Docs decision

本 corrective fix 不改变用户可见 CLI、Service/Host/Engine 分层、公共契约或运行时语义，
不触发 README 更新。按用户限定，唯一新增 docs 是本 gate artifact；未修改 frozen registry、
oracle、scenario、design 或其它 review artifact。

## Findings、residual risks 与下一入口

- Finding：两个遗漏 typed constructor keyword，状态为 `已修复`。
- Residual risks：无未分类 residual risk；未发现删除 keyword 之外所需的语义变更。
- Uncovered areas：未运行两个 smoke 的真实外部 provider/Host 场景；本机械 contract 修复已由
  focused/full pyright、compile 与 import 覆盖，且用户未授权外部场景执行。
- Completion：本 S1 corrective fix gate 完成；按用户要求在未 stage/commit/push/PR 的状态下
  停止。下一合法入口由后续独立 corrective review gate 决定。
