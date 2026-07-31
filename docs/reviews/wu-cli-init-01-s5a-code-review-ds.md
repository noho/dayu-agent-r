# WU-CLI-INIT-01 S5-A Code Review (DeepSeek 独立路)

## Gate

- Work unit：`WU-CLI-INIT-01`
- Gate：`deepreview`
- Reviewer：DeepSeek (S5-A 独立路)
- 日期：2026-07-30
- 结论：**PASS**

## Scope

- Mode: current changes（仅未提交文件）
- Branch: `ci/pr-179-first-ci-readiness`
- Base: S1-S4 已提交（commit `b0af8ecf` 及之前）
- 审查文件（仅 3 个未提交文件）：
  - `docs/cli_init_workspace_manifest_v1.json`
  - `utils/smoke_cli_init_provider_matrix.py`
  - `tests/cli/test_smoke_cli_init_provider_matrix.py`
- 审查依据：
  - Goal Confirmation artifact `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`
  - Codex plan `docs/reviews/wu-cli-init-01-plan-codex.md` S5
  - S5 expected outcomes（plan 第 9 节 S5）：
    - 精确 5 dirs/43 files（第 43 个为 workspace 根 `.dayu-init.lock`）
    - 16 owner pointers（8 ordinary + 8 thinking）
    - deterministic schema/redaction/classifier/no-fallback
    - 禁止 actual 自生成 expected
    - 不得把 package copy 冒充真实 publication
- 不审查范围：S1-S4 已提交代码

## Pre-review 验证结果

| 验证项 | 结果 |
|---|---|
| 42 个 deterministic test 全部通过 | PASS |
| pyright 0 errors, 0 warnings | PASS |
| Manifest 5 dirs, 43 files, 16 owner pointers 结构 | PASS |
| Frozen manifest 43 个 SHA-256 digest 与当前 package 文件全部匹配 | PASS |
| Manifest path 按字母排序、无重复 | PASS |
| `.dayu-init.lock` 在 manifest 中恰好 1 次出现 | PASS |
| `config/README.md` 与 `config/.DS_Store` 正确排除 | PASS |
| 8 ordinary + 8 thinking owner pointer role 分布 | PASS |
| 无 `write_text`/`write_bytes`/`json.dump` — 不生成 expected | PASS |
| `validate_publication_tree` 独立枚举 actual tree，不从 manifest 反推 | PASS |
| `FROZEN_MANIFEST_SHA256` 与 checked-in 文件精确匹配 | PASS |
| `rglob("*")` 在 Python 3.11 不跟随符号链接下降（实测确认） | PASS |
| Secret scan pattern 不标记 env var 引用名（如 `MIMO_PLAN_API_KEY`） | PASS |

## Findings

### 1-未修复-低-`validate_publication_tree` 异常捕获后继续比较产生误导性二级错误

- **入口/函数**: `validate_publication_tree()`
- **文件(行号)**: `utils/smoke_cli_init_provider_matrix.py:660-701`
- **输入场景**: workspace_root 不可读、lock 缺失、config 非目录等根级 I/O 或形状错误。
- **实际分支**: `except (OSError, ValueError, json.JSONDecodeError)` 捕获后向 `issues` 追加一条 `actual_tree_unreadable:<ExceptionType>`，但紧接着继续在 `actual_directories`/`actual_files`/`actual_owner_paths` 全部为 `()` 的状态下与 frozen manifest 逐项比较。
- **预期行为**: 根因被捕获后应短路返回，不执行后续比较。
- **实际行为**: 根因 `actual_tree_unreadable:ValueError` 被淹没在后续 4—5 条噪音问题中（包括全部 43 个文件的 `missing` 列表、全部 16 个 owner pointer 的 `missing` 列表、directory count 不匹配等），导致运维人员必须先排查"为什么所有文件都缺失"而非直接看到 workspace 不可读。
- **直接证据**: `utils/smoke_cli_init_provider_matrix.py:700-701` 捕获后仅 `issues.append(...)` 无 early return；`line 703-735` 继续在所有 actual 为空的情况下比较。
- **影响**: 排障体验下降，但 `valid=False` 正确保持 fail-closed；不导致错误 pass。
- **建议改法和验证点**: 在 `except` 块内立即 `return PublicationValidationReport(valid=False, issues=tuple(issues), actual_directories=(), actual_files=(), actual_model_owner_paths=())` 短路，不执行后续比较逻辑。补充测试：传入不存在的 workspace_root 断言 `issues` 仅包含 1 条 `actual_tree_unreadable` 且无 `file_path_mismatch` 或 `model_pointer_mismatch`。
- **修复风险（低）**: 改动仅涉及错误处理控制流，不改变正常路径语义。
- **严重程度（低）**:

### 2-未修复-低-`main()` 中 `NotImplementedError` 使 `__main__` 块的 `SystemExit` 构造成为死代码

- **入口/函数**: `main()` / `if __name__ == "__main__"`
- **文件(行号)**: `utils/smoke_cli_init_provider_matrix.py:1026-1048`
- **输入场景**: `python utils/smoke_cli_init_provider_matrix.py --oracle-version 1`
- **实际分支**: `main()` 在 `line 1042` 无条件 `raise NotImplementedError(...)`，永不返回 `int`。
- **预期行为**: 如果设计意图是 `SystemExit` 包装退出码，`main()` 应在参数解析有效后 `return 0` 或 `return 1` 而非抛异常；如果设计意图是明确拒绝 live 执行并产生 traceback，则 `__main__` 块应直接调用 `main()` 无需 `raise SystemExit(...)`。
- **实际行为**: `raise SystemExit(main())` 中 `main()` 先抛出 `NotImplementedError`，`SystemExit` 永远不被构造。代码意图与实现不一致。
- **直接证据**: `line 1042`: `raise NotImplementedError(...)`；`line 1048`: `raise SystemExit(main())`——前者先于后者执行，后者为死代码。
- **影响**: 不影响正确性（live 路径被正确拒绝），但代码意图模糊。`NotImplementedError` 的非零退出取决于 Python 解释器默认的未处理异常行为（exit 1 并打印 traceback）。
- **建议改法和验证点**: 要么保留 `NotImplementedError` 直接传播，移除 `raise SystemExit(...)` 包装；要么让 `main()` 在 live 路径返回非零 int，`__main__` 块调用 `sys.exit(main())`。建议当前保持现状，在后续 live 实现 slice 中一并修正，因为当前入口的语义是"尚未实现"而非"已实现但失败"。
- **修复风险（低）**: 不改变当前用户可见行为。
- **严重程度（低）**:

### 3-未修复-低-`validate_publication_tree` 的 `rglob` 目录发现仅覆盖 `config/` 子树，不检测 workspace 根级非 `config` 目录

- **入口/函数**: `validate_publication_tree()`
- **文件(行号)**: `utils/smoke_cli_init_provider_matrix.py:673-684`
- **输入场景**: workspace 根下存在 `portfolio/` 等非 init-owned 目录。
- **实际分支**: `line 673`: `directory_paths = [config_root]`；`line 674-678`: `config_root.rglob("*")` 只在 `config/` 子树内递归。workspace 根级的非 `config` 目录不进入 `actual_directories` 集合。
- **预期行为**: 按 plan 设计，"workspace 中 portfolio 等非 init-owned sibling 不参与比较"——这是有意为之的正确行为。
- **实际行为**: 目录比较仅在 init-owned `config/` 子树内进行，workspace 根级新增非 `config` 目录不会被检测为 `directory_mismatch`。文件比较同理，workspace 根级非 `config` 文件不会被发现。
- **直接证据**: `line 673-684` 目录发现起点为 `config_root`；manifest `directories` 列表不含 `config` 之外的顶级目录。
- **影响**: 如果未来 init 需要管理 workspace 根级其他目录（如 `.portfolio`），当前 manifest 设计与验证逻辑需要同步扩展。当前阶段这是正确的设计约束，不是 bug。记录为可追溯的设计点。
- **建议改法和验证点**: 无需修改。如果后续 oracle version bump 引入新 managed root，需同步更新 manifest `directories` 列表与 `validate_publication_tree` 的发现范围。
- **修复风险（低）**: 保持现状。
- **严重程度（低）**:

## Open Questions

1. **模型 owner 中 8 ordinary / 8 thinking 的角色分配是否与 S3 已实现的 manifest `default_model_id` 一致？** 当前测试 `test_frozen_manifest_matches_fresh_real_publication_tree` 通过 FIRST publication 间接验证，但 deterministic test 没有直接逐文件断言每个 manifest 的 `default_model_id` 值与预期 provider model id 的相等性。建议在后续 live smoke matrix 中补齐每个 scene 的 typed identity assertion。

2. **`CREDENTIAL_VALUE_PATTERN` 不匹配 camelCase 键名（如 `apiKey`）。** 当前 regex 的键名模式为 `api[_-]?key`，仅匹配 `apikey`/`api_key`/`api-key`。如果 future report schema 使用 `apiKey` 字段名，该 pattern 不会捕获。当前 report schema 由同一模块定义（`ProviderMatrixRowReport`），使用 snake_case 字段，所以无实际风险。建议在 secret scan 文档中明确 pattern 覆盖范围，避免未来 schema 变更时遗漏。

## Residual Risk

- **S4 实现质量依赖**：测试 `production_publication_tree` fixture 依赖 S4 的 `snapshot_managed_roots`、`prepare_workspace_transaction`、`publish_workspace_transaction` 正确性。如果 S4 有未发现的 bug（如 PRESERVE 漏补某类 managed file），本 slice 的 manifest 验证仍会通过（因为只测 FIRST mode），但真实 publication 可能与 manifest 不一致。该风险已由 S4 自己的 focused test 覆盖，本 slice 不重复。

- **Live provider matrix 尚未实现**：`main()` 显式拒绝 live 执行。15-row 真实 provider matrix 的 subprocess 编排、Host trace 读取、真实请求发出与 evidence 收集尚未验证。该风险分配给后续 live implementation slice。

- **Manifest 版本不可变性**：`FROZEN_MANIFEST_SHA256` 硬编码在测试中。如果 checked-in manifest 因 package file 变更需要更新，必须同步更新该常量。建议在 CI 中增加一条检查：`test_checked_in_manifest_digest_is_stable_across_validation` 必须在任何 commit 修改 `docs/cli_init_workspace_manifest_v1.json` 的同一次 commit 中也更新 `FROZEN_MANIFEST_SHA256`。

## 验证记录

```text
pytest tests/cli/test_smoke_cli_init_provider_matrix.py -v
  42 passed in 1.27s

pyright utils/smoke_cli_init_provider_matrix.py tests/cli/test_smoke_cli_init_provider_matrix.py
  0 errors, 0 warnings, 0 informations

Manifest SHA-256 验证:
  - Checked-in 文件: a4865273f11ce059aaabaf9d91ee1154a7f5c1f26794828c343a20e0e73cea88
  - 测试中硬编码值: a4865273f11ce059aaabaf9d91ee1154a7f5c1f26794828c343a20e0e73cea88
  - 匹配: True

  - 43 个 manifest file digest 与当前 package 文件全部匹配: True
  - Manifest 加载前后 digest 不变: True
```

## 裁决

**PASS** — 3 个未提交文件满足 S5 deterministic contract 的全部核心要求：

- frozen manifest 精确描述 5 directories、43 files（第 43 个为 `.dayu-init.lock`）、16 model projection owner pointers（8 ordinary + 8 thinking）；
- `validate_publication_tree` 独立枚举 actual tree，不依赖 manifest 构造 expected（无自证路径）；
- 所有 classifier（`classify_preflight`、`classify_availability`、`evaluate_no_fallback`）为确定性纯函数，无 fallback 宽容分支；
- secret scan（`scan_secrets`）与 endpoint redaction（`redact_endpoint`）fail-closed；
- utils 模块无文件写入逻辑，checked-in manifest 在验证前后 digest 不变；
- 42 个 deterministic test 全部通过，pyright 零错误。

3 个 low-severity finding 均不影响正确性与安全性，建议在后续 slice 中按优先级处理。
