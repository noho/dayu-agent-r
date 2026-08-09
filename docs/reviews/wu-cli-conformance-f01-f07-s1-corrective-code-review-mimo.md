# WU-CLI-CONFORMANCE-F01-F07 S1/F01 Corrective Fix Review（MiMo）

## Scope

- Mode：current changes（uncommitted diff relative to HEAD `e5b572d4`）
- Branch：`codex/interactive-oracle`
- Base：`e5b572d44fa86beac8a23413007cc48805c9ba67`
- Output file：`docs/reviews/wu-cli-conformance-f01-f07-s1-corrective-code-review-mimo.md`
- Included scope：
  - `utils/smoke_cli_init_provider_matrix.py`（unstaged diff）
  - `utils/smoke_host_public_awaiting_entrypoint.py`（unstaged diff）
  - `docs/reviews/wu-cli-conformance-f01-f07-s1-corrective-fix-codex.md`（untracked corrective artifact）
  - Owner contract：`dayu/service/entrypoint_runtime.py` L433-451
  - Regression guard：`tests/service/test_entrypoint_runtime.py` L1058-1063
  - Accepted plan、S1/S2 controller artifacts、S1 implementation artifact
- Excluded scope：无
- Parallel review coverage：无

## 独立验证结果

### Diff 精确性

`git diff e5b572d4 -- utils/` 确认仅两处删除，每处各删除一行 `explicit_config_dir=None` keyword，无其它改动：

- `utils/smoke_cli_init_provider_matrix.py:2386`：删除 `explicit_config_dir=None`
- `utils/smoke_host_public_awaiting_entrypoint.py:808`：删除 `explicit_config_dir=None`

### Owner contract 确认

`dayu/service/entrypoint_runtime.py:433-451`：`EntrypointRuntimeRequest` 为 `@dataclass(frozen=True, slots=True)`，仅含 6 个字段（`workspace_root`、`package_config_root`、`scene_id`、`context_slot_values`、`assembly_overrides`、`env`）。`explicit_config_dir` 已不存在。

### 其它 typed constructor 扫描

S1 commit `a41526ec` 同时从 `ServiceHostAdminRequest` 删除了 `config_overlay_dir`。独立扫描所有 `ServiceHostAdminRequest(` 调用点（4 处：`dayu/cli/commands/session.py:217`、`tests/service/test_host_admin.py:95,157`、`tests/cli/test_session_command.py:736`），均无 `config_overlay_dir` 残留。

扫描全部 `EntrypointRuntimeRequest(` 调用点（13 处：2 个 utils、1 个 production、10 个 test），修正后均不含 `explicit_config_dir`。

`rg -n 'explicit_config_dir' --glob '*.py' dayu tests utils` 仅命中 `tests/service/test_entrypoint_runtime.py:1063` 的 owner 级负向断言（`assert "explicit_config_dir" not in field_names`），不是实现残留。

`rg -n 'CONFIG_DIR_OPTION_NAME|resolve_explicit_config_dir' --glob '*.py' dayu tests utils`：零命中。S1 删除的 helper/export/forwarding 符号无残留。

**结论：不存在其它遗漏的 typed constructor call site。**

### Focused pyright

```
python -m pyright utils/smoke_cli_init_provider_matrix.py    → 0 errors, 0 warnings, 0 informations
python -m pyright utils/smoke_host_public_awaiting_entrypoint.py → 0 errors, 0 warnings, 0 informations
```

### Full pyright

```
python -m pyright → 0 errors, 0 warnings, 0 informations
```

### Compile / import

```
python -m py_compile utils/smoke_cli_init_provider_matrix.py utils/smoke_host_public_awaiting_entrypoint.py → exit 0
python -c 'import utils.smoke_cli_init_provider_matrix; import utils.smoke_host_public_awaiting_entrypoint' → exit 0
```

### Registry 与 index

- `python -m json.tool docs/cli_ci_oracles.json`：通过
- `python -m json.tool docs/cli_ci_scenarios.json`：通过
- `docs/cli_ci_oracles.json` SHA-256：`f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`（与 S1 冻结基线一致）
- `docs/cli_ci_scenarios.json` SHA-256：`7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`（与 S1 冻结基线一致）
- `git diff --cached --name-only`：无输出，index empty
- `git diff --check`：通过

### 因果链确认

1. S1 commit `a41526ec` 从 `EntrypointRuntimeRequest` owner contract 删除 `explicit_config_dir` 字段
2. S1 commit 正确更新了 production 和 test 调用点，但遗漏了两个 `utils/` 调用点
3. S2 controller adjudication 正确分类为"S1 引入的 cross-slice regression"而非既有 debt
4. Corrective fix 机械删除两个过期 keyword，不恢复字段、不增加 alias/wrapper/default
5. 修复后 focused/full pyright 均为 0，compile/import 通过

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- 两个修改文件均位于 `utils/`，按项目约束默认无需测试与覆盖率。本次改动不改变运行时行为，只令调用方符合现有 typed owner contract，residual risk 极低。
- 未运行两个 smoke 脚本的真实外部 provider/Host 场景。本机械 contract 修复已由 focused/full pyright、compile 与 import 覆盖，且用户未授权外部场景执行。

## Verdict

**PASS — 无 accepted finding。**

Corrective fix 因果成立、scope 精确、无兼容字段/alias/wrapper、F01 Python 实现零残留、两个 focused 及 full pyright 均为 0、compile/import/diff/registry/index 全部通过、无其它遗漏 typed constructor。Corrective artifact 声称的所有验证结果均经独立复核确认。
