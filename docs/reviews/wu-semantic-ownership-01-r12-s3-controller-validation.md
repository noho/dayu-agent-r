# WU-SEMANTIC-OWNERSHIP-01 / R12 S3 Controller validation

## Gate 与结论

- Gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R12 S3 cumulative implementation Controller validation；不是新 WU。
- Agent artifact：`docs/reviews/wu-semantic-ownership-01-r12-s3-implementation-codex.md`，222 行 / 14,272 字节 / SHA-256 `4e0f8938a813b801bf2a5ff736df9d10190e44b8072ff8a53864201072394ae8`。
- 固定执行真源：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，SHA-256 `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`。
- 结论：`PASS_WITH_MANDATORY_REVIEW_CHALLENGES / READY_FOR_DUAL_COMPLETE_CUMULATIVE_CODE_REVIEW`。
- accepted/open implementation finding：`0`；local blocker：`0`；unclassified residual：`0`。
- 本结论只授权 AgentMiMo / AgentDS 并发完整 code review。它不授权 fix、commit、aggregate、push、PR 或 umbrella closeout。

## 第一性原理与 owner 核验

S3 动机成立。S1/S2 已完成选择事实、OS secret store、managed-root transaction 与真实 Service validation owner；仍缺的闭环是 publish 后入口预热、真实 POSIX/Windows 用户工作流证明与三类 README 投影。当前实现把语义留在正确边界：

- `dayu/cli/commands/init.py` 只在 FIRST/RESET 成功 publication 后调用无参 import-only helper；PRESERVE/OVERWRITE 不调用；普通 import failure 只投影 error type 与固定摘要，不回滚配置，控制流异常不被吞掉。
- init 只拥有 `dayu.cli.commands.interactive`、`dayu.cli.commands.prompt` 两个 root；transitive graph 继续由模块 import graph 自己拥有，没有复制 `session_execution` / `entrypoint_runtime` 或调用 runtime assembly。
- 真实 config/scene smoke 继续消费 `ConfigLoader`、Service discovery 与 `SceneToolCatalog`；lock smoke 继续消费 `dayu.runtime.filelock` 和公开 waiting notification，没有 production test sentinel、有限 production timeout 或重试概率。
- stale prompt caller 与根 README contract test 都迁移到显式交互/当前用户契约；production 未新增 implicit default、fallback、compatibility 或下游 repair。
- Windows workflow 只提供真实 runner 证据，不新增 platform abstraction、权限框架、registry value artifact 或 deferred Issue 实现。

## 固定累计 review target

完整 S1→S2→S3 product/test/README/workflow target 为以下 20 个路径：

1. `.github/workflows/r12-init-windows.yml`
2. `README.md`
3. `dayu/cli/arg_parsing.py`
4. `dayu/cli/commands/init.py`
5. `dayu/cli/init_catalog.py`
6. `dayu/cli/init_environment.py`
7. `dayu/cli/init_workspace.py`
8. `dayu/config/README.md`
9. `dayu/service/README.md`
10. `dayu/service/entrypoint_runtime.py`
11. `dayu/service/host_assembly.py`
12. `tests/README.md`
13. `tests/cli/test_arg_parsing.py`
14. `tests/cli/test_init_catalog.py`
15. `tests/cli/test_init_command.py`
16. `tests/cli/test_init_environment.py`
17. `tests/cli/test_init_smoke.py`
18. `tests/cli/test_init_workspace.py`
19. `tests/cli/test_prompt_command.py`
20. `tests/service/test_host_assembly.py`

各路径 SHA-256 与 Agent artifact 完全一致；对逐路径 `shasum -a 256` 行排序后再次 SHA-256 的 manifest digest 为 `2835b3e137f0a7ddef150fb02b728cf73f3488abeccebb534d947bd60ded6f2d`。S2 声明保持不动的 11 个累计路径也逐项匹配 final lock。staged tree 为空。

## Controller 独立验证

### Tests 与真实 POSIX smoke

Controller 在 Agent 返回后独立运行固定计划命令：

| Profile | Controller 结果 |
|---|---|
| S3 cumulative affected CLI/Service | `408 passed, 5 skipped, 3 warnings` |
| runtime/config/scene/tool anchors | `184 passed` |
| full `tests/cli` | `505 passed, 7 skipped, 3 warnings` |
| final Service target | `133 passed, 3 warnings` |

五个 S3 skip 都由 `platform.system() != "Windows"` 的真实 Windows-only nodes 产生；本机是 Darwin。三条 warning 是既有 `edgar` deprecation warning。真实 POSIX 四态、ConfigLoader/13-scene validation、profile、public `portfolio`/`assets` sentinel、RESET No 整树 hash、单 waiter 与双 queued publisher 均实际执行通过。

### 七个 production owner 单文件 coverage

每个模块独立运行且都使用 `--cov-fail-under=80`：

| Production file | TOTAL | MISS | Coverage |
|---|---:|---:|---:|
| `dayu/cli/init_catalog.py` | 276 | 27 | 90% |
| `dayu/cli/init_environment.py` | 304 | 16 | 95% |
| `dayu/cli/init_workspace.py` | 547 | 70 | 87% |
| `dayu/cli/commands/init.py` | 295 | 27 | 91% |
| `dayu/cli/arg_parsing.py` | 294 | 1 | 99% |
| `dayu/service/host_assembly.py` | 570 | 30 | 95% |
| `dayu/service/entrypoint_runtime.py` | 571 | 67 | 88% |

没有使用 package aggregate 替代单文件门槛。

### Type、Ruff、diff 与边界

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- 15 个 cumulative changed/new Python 路径 scoped Ruff：`All checks passed!`；包括 S3 的 stale caller 与 Controller follow-up README assertion owner test。
- full Ruff current：144 条；SHA-256 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`；与 entry baseline `cmp` exit 0。
- `git diff --check` 通过；staged tree 为空。
- Service diff 精确为 `dayu/service/README.md`、`dayu/service/entrypoint_runtime.py`、`dayu/service/host_assembly.py`、`tests/service/test_host_assembly.py`。
- Fins/Host/Engine/Tool/runtime、package models/manifests、五份设计真源、`pyproject.toml`、`utils` 的 tracked/untracked diff 均为空。
- forbidden runtime-assembly scan 在 `commands/init.py` 为零；production import scan只命中 exact two roots 与 `importlib.import_module`。
- CLI-side Fins classification/raw stripping 与 metadata-only/synthetic/fake-provider/test-shim scan 为零；network scan只命中 `urllib.parse.urlsplit` 本地语法校验和 argument-safe `subprocess.run` 的 `setx` owner。
- auth scan只有既有 `host_context.authorization_claims=()` 与既有 session test fixture，R12 diff 没有统一 tool authorization framework 或新 permission schema。

## Windows workflow 安全与证据边界

Controller 完整读取 `.github/workflows/r12-init-windows.yml` 和全部 Windows-only nodes：

- runner 固定 `windows-latest`、Python 3.11 和 Windows x64 Python 3.11 lock constraint；workflow 正常执行四态/重载、pre-seeded junction fail-closed、普通 symlink精确 privilege skip、root identity、replace rollback、scan-delete race、真实 `setx` round-trip/cleanup以及 R11 两个真实 cmd/upload nodes。
- JUnit 断言与生产错误投影使用 name-only/固定错误；版本、capability、source hash 和 environment names 可上传，environment/registry values 与 raw registry output 不上传。
- workflow 的 `if: always()` 不会把前一 step 的失败改成成功；只保证 R11 节点和可用诊断继续执行/上传。
- 本机未执行 Windows tests，Controller 不把 skip 或 workflow 文件存在写成 Windows success。

## Mandatory review challenges

两路 reviewer 必须对完整 20-path 累计目标做 `$deepreview` 对等的 complete review，并至少独立挑战：

1. prewarm 是否严格只在 publication success boundary 后的 FIRST/RESET 调用，failure/interrupt/diagnostic I/O 是否保持真实控制流；
2. import observation seam 是否遗漏其它 import-time network/external mutation，或测试是否错误固化 transitive graph 为新的 product contract；
3. POSIX/Windows真实 smoke 是否只消费 owner contract，尤其 lock 双 waiter、RESET sentinel、junction/reparse、workspace identity、rollback、scan-delete race 与 `setx` cleanup；
4. workflow/JUnit/log/artifact 任一失败路径是否可能泄露 environment/registry value，或用 skip/`always()` 掩盖必跑节点；
5. README 四态、16 known manifest projection、secret persistence、lock/prewarm 文字是否与代码同源且没有扩大 durability、network、Host lock 或 assets/portfolio 承诺；
6. S1/S2 已关闭 findings 是否因 S3 累积修改而回归，是否出现 deferred Issue 142/151/175/177/178、Web/WeChat/render 或统一 authorization scope leakage。

## Findings 与 residual risks

- 当前 accepted/open implementation finding：`0`。
- **`PENDING_RELEASE_BLOCKER`：真实 Windows runner 证据。** `.github/workflows/r12-init-windows.yml` 必须在 Windows runner 成功执行并产生 name-safe evidence；在此之前 reviewer/Controller 不得把 Windows gate、S3、R12 或 umbrella 写成最终通过。owner/destination 是 R12 Windows workflow release gate；这不是 deferred code finding。
- RESET 两个 managed roots 不是 single-syscall transaction 的既有 residual 保持不变；owner 是 R12 当前 per-root replace/rollback contract 与 RESET 前停止 active Dayu 的用户责任。本轮不引入 Host/process lock、journal 或 filesystem framework。

## Next entry point

并发 AgentMiMo / AgentDS complete cumulative code review only。每路 artifact 必须固定上述 20-path manifest、明确区分本机通过与 Windows pending evidence、给每个 finding 最终可裁决状态。reviewer 不得修改文件、fix、commit、push、PR、进入 aggregate 或关闭 R12/umbrella。
