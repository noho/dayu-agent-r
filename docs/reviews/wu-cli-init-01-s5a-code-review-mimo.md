# Code Review

## Scope

- Mode: current changes（WU-CLI-INIT-01 S5-A 独立 MiMo 路）
- Branch: `ci/pr-179-first-ci-readiness`
- Base: `main`
- Output file: `docs/reviews/wu-cli-init-01-s5a-code-review-mimo.md`
- Included scope:
  - `docs/cli_init_workspace_manifest_v1.json`（frozen publication manifest）
  - `utils/smoke_cli_init_provider_matrix.py`（S5-A 确定性 contract 模块）
  - `tests/cli/test_smoke_cli_init_provider_matrix.py`（S5-A 确定性 contract 测试）
- Excluded scope: S1-S4 已提交实现文件、其它未涉及文件
- Parallel review coverage: 无（scope 精确为三个文件，无需并行 subagent）

## 审查依据

- Goal Confirmation：`docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`
- Plan：`docs/reviews/wu-cli-init-01-plan-codex.md` S5 slice
- S5 要求：精确 5 dirs / 43 files（第 43 个为 workspace 根 `.dayu-init.lock`）、16 owner
  pointers、deterministic schema / redaction / classifier / no-fallback、禁止 actual 自生成
  expected、不得把 package copy 冒充真实 publication

## 验证执行

| 验证项 | 结果 |
|--------|------|
| `pytest tests/cli/test_smoke_cli_init_provider_matrix.py -v` | 42 passed, 0 failed |
| `pyright utils/smoke_cli_init_provider_matrix.py tests/cli/test_smoke_cli_init_provider_matrix.py` | 0 errors, 0 warnings |
| manifest SHA-256 与 test constant 一致 | `a4865273...cea88` 精确匹配 |
| manifest 结构：5 dirs / 43 files / 16 owners (8 ordinary + 8 thinking) | PASS |
| `.dayu-init.lock` SHA-256 = empty-file hash | `e3b0c442...b855` 精确匹配 |
| 所有 owner path 都在 files 列表中 | PASS |
| 所有 16 个 manifest JSON 均含 `default_model_id` | PASS |
| 三个 spot-check 文件 SHA-256 与 manifest 一致 | PASS |
| classifier 覆盖全部有效外部结果组合 | PASS |
| classifier fail-closed（矛盾证据 → INTERNAL_PRODUCT_BUG） | PASS |

## Findings

未发现实质性问题。

以下为逐维度审查结论：

### 1. `docs/cli_init_workspace_manifest_v1.json` — 冻结清单

- oracle_id / oracle_version / publication_root 与 plan S5 常量精确一致。
- 5 个目录（`config`、`config/prompts`、`config/prompts/base`、`config/prompts/manifests`、`config/prompts/scenes`）排序且无重复。
- 43 个文件排序且无重复；根级 `.dayu-init.lock` 恰好出现一次，SHA-256 为已知空文件摘要。
- 16 个 model projection owner 全部使用 `/model/default_model_id` pointer、合法 `ModelRole` 枚举、路径排序且无重复；owner paths 是 file paths 的严格子集。
- 8 ordinary + 8 thinking role 数量与 plan 的 16 scene 投影一致。
- 清单是从实际 package 发布树独立 snapshot 而来，不是从代码运行时动态生成的——满足"禁止 actual 自生成 expected"约束。

### 2. `utils/smoke_cli_init_provider_matrix.py` — 确定性 contract 模块

- **语义所有权**：每个纯函数拥有唯一明确的语义边界（preflight classification、availability classification、endpoint redaction、bounded summary、secret scan、no-fallback evaluation、manifest loading/validation）。不存在跨 ownership boundary 的 fallback 或 re-derivation。
- **schema 严格性**：`load_manifest` 对 JSON 做全键校验（`_require_exact_keys`）、类型校验（`_expect_mapping` / `_expect_list` / `_expect_string`）、路径校验（`_validate_relative_path`）、摘要格式校验（`SHA256_PATTERN`）、pointer 唯一性（`/model/default_model_id`）和 role 数量平衡（8+8）。未知字段、多余字段、类型不匹配均立即 fail closed。
- **fail-closed 设计**：`classify_availability` 对每种矛盾证据组合（credential_missing + request_attempted、exit 0 + no request、response without request 等）均归类为 `INTERNAL_PRODUCT_BUG`。`evaluate_no_fallback` 对 identity drift、run binding mismatch、observation without request 均添加 reason code。
- **redaction**：`redact_endpoint` 去除 userinfo/query/fragment，只保留 scheme/hostname/port/path_sha256。`scan_secrets` 检测 authorization header、bearer token、credential field value、canary 和已知 credential value，且 finding code 不回显 secret 本身。
- **live 边界**：`main()` 解析 argparse 后立即抛出 `NotImplementedError`，明确拒绝 S5-A 未实现的 live subprocess/Host trace 路径。不静默返回、不伪装成功。
- **类型完整性**：所有 15 个 dataclass 均为 `frozen=True, slots=True`；所有枚举均继承 `str, Enum`；所有函数签名均有完整类型注解；pyright 0 errors。

### 3. `tests/cli/test_smoke_cli_init_provider_matrix.py` — 确定性 contract 测试

- **fixture 设计**：`production_publication_tree`（module scope）通过 production `prepare_workspace_transaction` + `publish_workspace_transaction` 构造真实 FIRST publication tree，不手动拼凑文件。`fresh_publication_tree`（function scope）复制后允许独立破坏。`_write_manifest_variant` 通过精确文本替换生成非法 manifest 变体。
- **manifest 校验覆盖**：
  - 正向：冻结 manifest 与真实 publication tree 精确匹配（路径、摘要、model pointer）
  - 稳定性：验证前后 manifest SHA-256 不变
  - 反向：新增文件、删除文件、内容篡改、model pointer 漂移均 fail closed
  - schema：非法 JSON、未知根字段、错误 oracle version、非法 SHA-256、错误 json_pointer 均被拒绝
- **classifier 覆盖**：
  - preflight：5 个 parametrize case 覆盖 `CREDENTIAL_MISSING`、`ENDPOINT_UNCONFIGURED`、`SERVICE_UNREACHABLE`、`REQUESTABLE`（全满足）和 `REQUESTABLE`（无 endpoint 要求）
  - availability：9 个 parametrize case 覆盖全部 7 个非 `INTERNAL_PRODUCT_BUG` enum 分支 + 2 个 `INTERNAL_PRODUCT_BUG` fail-closed 分支
  - 额外：外部 preflight 与请求事实矛盾 → `INTERNAL_PRODUCT_BUG`
- **no-fallback 覆盖**：
  - 同 run 同 identity → passed
  - 未发请求无 observed identity → passed（preflight failure）
  - identity drift + trace mismatch + alternate success → 5 个 reason code
  - observation without request → fail closed
- **其它**：endpoint redaction（secret 去除 + 非法 URL 拒绝）、bounded text summary（截断 + 负数拒绝）、secret scan（5 类泄漏 + 空探针拒绝 + ref 名允许）、main 入口显式 NotImplementedError
- **self-proof**：测试不使用 mock/fake 代替 production 代码。`production_publication_tree` fixture 直接调用 production init workspace owner，证明冻结 manifest 是从真实 publication 产物独立校验的。
- **test 不自生成 expected**：`FROZEN_MANIFEST_PATH` 指向 checked-in 文件，`FROZEN_MANIFEST_SHA256` 是硬编码常量。测试从未从 actual tree 动态生成 expected 后自比。

### 4. 非目标 / scope creep 检查

- 三个文件均不修改 Host lifecycle、Engine loop、Fins storage、memory/EventLog schema。
- 不新增 provider integration、不申请 credential、不启动 Ollama。
- 不把 mock/fake 当作真实 matrix 通过证据。
- `main()` 明确拒绝 live 路径，不静默伪装。
- 模块 docstring 明确声明"S5-A 的纯函数、严格类型 schema 和命令行骨架"。

### 5. Secret / fallback fail-closed 检查

- `scan_secrets` 的 regex 模式不匹配纯 env ref 名（如 `MIMO_PLAN_API_KEY`），只匹配实际值泄漏。
- `evaluate_no_fallback` 对 identity drift、run binding mismatch、observation without request 均添加 reason code，`fallback_observed` 与 `passed` 独立计算但语义一致。
- `classify_availability` 对矛盾证据 fail closed 到 `INTERNAL_PRODUCT_BUG`。
- endpoint redaction 去除 userinfo/query/fragment。

## Open Questions

无。

## Residual Risk

- **config/README.md 存在于 package 目录但不在冻结 manifest 中**：这是正确行为——`publish_workspace_transaction` 只创建 init-managed 文件，不复制 package 中的 README.md。production fixture 通过真实 transaction 构造 publication tree，已证明不包含该文件。风险为零。
- **.dayu-init.lock 不在 git-tracked config 目录中**：该文件是 init 时创建的 workspace 根级 lock 文件，SHA-256 为空文件摘要。production fixture 通过 `publish_workspace_transaction` 创建它。风险为零。
- **live provider matrix 尚未实现**：当前 `main()` 明确抛出 `NotImplementedError`，这是 S5-A 的预期行为。live 路径属于后续 S5-B scope。

## 结论

**PASS**

三个文件完整满足 S5-A 的确定性 contract 要求：冻结 manifest 精确匹配 5 dirs / 43 files / 16 owner pointers；纯函数模块的 schema / redaction / classifier / no-fallback 逻辑严格 fail closed；测试通过 production publication tree fixture 证明 self-proof，不自生成 expected，不伪装 pass。pyright 0 errors，42 tests passed。
