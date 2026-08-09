# PR 190 / F17 Implementation

- Gate：`implementation`
- Work unit：PR 190 / F17，闭合 frozen workspace publication manifest digest 派生链
- Accepted plan：`docs/gateflow/pr-190-f17-plan-20260807.md`
- Plan acceptance：`docs/gateflow/pr-190-f17-plan-acceptance-20260807.md`
- Artifact path：`docs/gateflow/pr-190-f17-implementation-20260807.md`
- Completion status：`pass`
- 下一入口：`code review`；按用户明确要求，本轮不进入 review、不 commit、不 push

## Scope 与 owner decision

问题真实存在，严重性限定为冻结 publication 派生链不闭合，而非 production publication 行为错误。唯一语义 owner chain 为：

1. `dayu/config/prompts/scenes/conversation_compaction_user.md` raw bytes 是 prompt 内容真源，本 gate 只读；
2. `docs/cli_init_workspace_manifest_v1.json` 是冻结 publication truth consumer，负责记录目标 asset digest；
3. `tests/cli/test_smoke_cli_init_provider_matrix.py::FROZEN_MANIFEST_SHA256` 是 manifest 保存后 raw bytes 的二级 pin。

实施严格限定为两个单行 hunk：更新 manifest 中唯一目标 entry，再从已保存 manifest 的 `Path.read_bytes()` 实际计算 SHA-256 并更新测试 pin。未修改 prompt、production transaction、validator、fixture/assertion、Oracle/scenario/readiness、schema、public contract、README 或 `docs/cli_ci.md`；未新增 helper、fallback 或兼容分支。

## Pre-state evidence

- `git branch --show-current && git status --short`：exit 0；分支 `codex/interactive-oracle`，工作树 clean。
- `shasum -a 256 docs/cli_init_workspace_manifest_v1.json dayu/config/prompts/scenes/conversation_compaction_user.md`：exit 0；pre-state manifest 为 `d95de68e69b0aacc712ec6bf468c8604a91460a17f3e2497f397182517a6a9f8`，prompt 为 `22e7bc5015cb369ff228a754b557493594b8313c99877944b5a7c08da0dc1c88`。
- 标准库 JSON parser 结构化断言：exit 0；`files=43`，目标 path 精确命中 1 entry，其余 42 entries 均不使用旧 digest `59b50e13ea636c434fcabe26adf6d9ed22665dfcba03533ebcf5e9b524b87b76`。
- fresh production `InitMode.FIRST` strict audit：exit 0；`valid=false`，`issues=("file_digest_mismatch:config/prompts/scenes/conversation_compaction_user.md",)`，actual/manifest inventory 均为 5 directories / 43 files / 16 model owners，`.dayu-init.lock` 存在。不存在第二 mismatch。
- `pytest tests/cli/test_smoke_cli_init_provider_matrix.py::test_frozen_manifest_matches_fresh_real_publication_tree -q`：exit 1；按预期仅在 `assert report.valid` 失败，作为修复前失败基线。

## Implementation result

- 使用 JSON parser 按精确 path 唯一定位 manifest entry，并从 prompt `read_bytes()` 计算实际 SHA-256；将该 entry 从 `59b50e13ea636c434fcabe26adf6d9ed22665dfcba03533ebcf5e9b524b87b76` 更新为 `22e7bc5015cb369ff228a754b557493594b8313c99877944b5a7c08da0dc1c88`。
- 保存 manifest 后，从其 `Path.read_bytes()` 实际计算 SHA-256 为 `064f80660b2cba0f16db392a46e8dc68ac45fdcd31252f96423c854e342cae22`；该实算值与计划交叉检查值一致，再据此更新 `FROZEN_MANIFEST_SHA256`。未使用计划预测值替代实际重算。
- post-state 结构化断言：`files=43`、目标 entry 1、其余 entries 42、旧 digest 在其余 entries 中出现 0 次。

## Validation

| 命令 | Exit | 结果 |
| --- | ---: | --- |
| fresh production `InitMode.FIRST` publication + `validate_publication_tree(...)` structured audit | 0 | `valid=true`、`issues=()`；actual/manifest 均为 5/43/16；lock 存在 |
| `pytest ...::test_frozen_manifest_matches_fresh_real_publication_tree ...::test_checked_in_manifest_digest_is_stable_across_validation -q` | 0 | 2 passed，3 个第三方 deprecation warnings |
| `pytest --collect-only -q tests/cli/test_smoke_cli_init_provider_matrix.py` | 0 | 71 tests collected |
| `pytest tests/cli/test_smoke_cli_init_provider_matrix.py -q` | 0 | 71 passed，3 个第三方 deprecation warnings |
| `python -m json.tool docs/cli_init_workspace_manifest_v1.json >/dev/null` | 0 | JSON parse 通过 |
| 标准库 JSON parser + AST pin + `read_bytes()` digest/count assertions | 0 | target 唯一；prompt digest = entry；manifest raw digest = test pin；43/1/42/0 均符合 |
| `shasum -a 256 docs/cli_init_workspace_manifest_v1.json dayu/config/prompts/scenes/conversation_compaction_user.md` | 0 | manifest `064f8066...cae22`；prompt `22e7bc50...c1c88` |
| `python -m pyright dayu/ tests/ utils/` | 0 | full pyright 通过，无新增或扩散错误 |
| `python -m ruff check tests/cli/test_smoke_cli_init_provider_matrix.py utils/smoke_cli_init_provider_matrix.py` | 0 | All checks passed |
| `python -m compileall -q tests/cli/test_smoke_cli_init_provider_matrix.py utils/smoke_cli_init_provider_matrix.py` | 0 | 通过 |
| `git diff --check` | 0 | 通过 |
| exact changed-file guard：status/name-only/numstat/word-diff/unified-zero-context/protected-path diff | 0 | artifact 前产品/测试路径精确为 2 个；各 1 insertion / 1 deletion、各一个单行 hunk；受保护路径零 diff |

## Final digests 与 counts

- Prompt raw SHA-256：`22e7bc5015cb369ff228a754b557493594b8313c99877944b5a7c08da0dc1c88`
- Manifest 目标 entry：`22e7bc5015cb369ff228a754b557493594b8313c99877944b5a7c08da0dc1c88`
- Manifest raw SHA-256：`064f80660b2cba0f16db392a46e8dc68ac45fdcd31252f96423c854e342cae22`
- Test frozen pin：`064f80660b2cba0f16db392a46e8dc68ac45fdcd31252f96423c854e342cae22`
- Inventory：actual/manifest 均为 5 directories / 43 files / 16 model owners；owner suite 71 tests。

## Docs trigger decision

- `tests/README.md`：不更新；测试层级、运行方式、维护规则和测试数量均未变化，只更新既有二级 digest pin。
- `dayu/config/README.md`：不触发；`dayu/config/` 与 prompt 内容均未修改。
- 根 `README.md`：不触发；安装、初始化、CLI 入口、输出、日志、workspace 位置与最终用户工作流均未变化。
- `dayu/README.md`：不触发；分层与装配边界未变化。
- `docs/cli_ci.md`：不修改；accepted Oracle、scenario registry、readiness 与 CI 流程均未变化。
- `docs/gateflow/`：仅新增本 implementation gate evidence artifact。

## Residual risks / uncovered areas

- 非目标 bytes 被改写：`fixed in current slice`；由保存后 raw digest、JSON 结构化断言、numstat、word diff 与 exact two-hunk guard覆盖。
- 第二 publication mismatch 或 inventory 漂移：`fixed in current slice`；post strict audit 为 `issues=()` 且 5/43/16 保持不变。
- 测试数量意外减少：`fixed in current slice`；collect-only 为 71，owner suite 为 71 passed。
- 真实 provider / Oracle replacement scenarios 未重跑：`assigned to later work unit`；F17 未改变 provider、Oracle/scenario/readiness 或产品行为。
- 未来 package asset 再次漂移：`assigned to later work unit`；现有 strict validator 与 frozen digest test 会 fail closed，本 slice 不新增自动更新写路径。

不存在未分类 residual risk 或 blocking open question。implementation gate 完成；按用户限制停在 code review 之前。
