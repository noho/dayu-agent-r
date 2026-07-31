# WU-CLI-INIT-01 S6 Implementation

## Gate metadata

- Gate：`implementation`
- Work unit：`WU-CLI-INIT-01`
- Slice：`S6 — README、aggregate validation 与 handoff`
- Baseline commit：`48567008`
- Branch：`ci/pr-179-first-ci-readiness`
- 日期：2026-07-30
- 状态：`PASS`
- Artifact path：
  `docs/reviews/wu-cli-init-01-s6-implementation-codex.md`

## Scope 与 Controller exception

Accepted S6 原始 allowed files：

- `README.md`
- `dayu/config/README.md`
- `dayu/service/README.md`
- `tests/README.md`
- 本 implementation artifact

首次完整 focused suite 暴露 16 个同源失败后，Controller 裁决其为 S3 package
compactor baseline 变更后遗漏的测试 fixture migration，并明确允许最小扩展：

- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`

本次没有修改 production、ConfigLoader、Service assembly、package config、provider
harness、retained evidence 或 frozen manifest，也没有调用 provider。

## 第一性原理判断与 root cause

失败动机成立，且不是 S6 README 改动造成的环境噪声：

1. 基线 `48567008` 的四个 package execution profile 已把
   `run_baseline.model_id` 与 `compactor_baseline.model_id` 全部设为
   `mimo-v2.5-pro-plan`。
2. Service 使用不带 invocation override 的 package compactor selection 构造
   compactor runner；其 header 正确要求 `MIMO_PLAN_API_KEY`。
3. 16 个失败都在
   `dayu.service.host_assembly._render_headers(...)` 以
   `missing env MIMO_PLAN_API_KEY` 终止。
4. 同一基线的 prompt / interactive runtime fixture 只传
   `{"DEEPSEEK_API_KEY": ...}`。DeepSeek key 只满足各测试显式选择的单次 ordinary
   override，不能满足 package Mimo compactor baseline。
5. 当前 S6 首次失败时相对 `48567008` 只有四份 README 改动；两份失败测试和
   production/package owner 均与基线逐字节一致。

因此 root cause 是测试输入 fixture 没有随 S3 已接受的双 selection credential
需求迁移。正确修复 owner 是两份测试各自共享的 runtime assembly env helper，不是
production fallback、ConfigLoader 绕过、Service 特例或逐测试补丁。

## Changed files

- `README.md`
- `dayu/config/README.md`
- `dayu/service/README.md`
- `tests/README.md`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `docs/reviews/wu-cli-init-01-s6-implementation-codex.md`

## 实现与文档同步

### 测试 fixture migration

两份测试文件分别新增唯一 `_runtime_assembly_env()`：

- 保留 `DEEPSEEK_API_KEY`，满足测试本身的显式 ordinary override；
- 增加 `MIMO_PLAN_API_KEY`，满足 package compactor baseline；
- 所有相关 runtime assembly input 复用该 helper；
- helper docstring 明确只供
  `prepare_entrypoint_runtime -> Service assembly -> compactor` 完整装配路径使用；
  mock-assembly 测试继续只声明自身消费的输入，不批量增加 Mimo credential；
- 返回 fresh typed `dict[str, str]`，不修改进程环境，不读取真实 credential；
- 没有逐测试 monkeypatch，没有降低 secret resolution，也没有绕过真实
  ConfigLoader / Service assembly。

### README

- 根 README：记录 `init` 不接受 `--config`、`--model/-m` 的单次 Run 语义、
  FIRST/PRESERVE/OVERWRITE/RESET、普通文件 repair、EOF/SIGINT/确认退出码，以及
  package/init 后 ordinary 与 compactor 单 family；跨 provider family 的单次主 Run
  override 不改变 compactor，未 init 时 compactor 继续使用包内默认 family。
- Config README：记录 PRESERVE 补齐五个根配置与 prompt、普通文件 repair 边界、
  15-choice / 16-manifest family 投影、target effective profile context minimum、
  package Mimo run/compactor fallback 和 compactor 独立 runner hint。
- Service README：记录 primary default、ordinary invocation effective 与 compactor
  effective 三个 selection，primary/compactor 四字段 family fail-closed，以及
  invocation override isolation。
- Tests README：记录完整 focused/coverage 命令、冻结的 5-directory /
  43-file / 16-pointer publication manifest、deterministic harness、显式 live
  provider matrix、脱敏和 no-fallback contract。

四份 README 只描述当前已实现行为；新增行不含 WU、review、迁移阶段或 future
表述。

## DS review finding adjudication

DS review artifact：
`docs/reviews/wu-cli-init-01-s6-code-review-ds.md`。

| Finding | Decision | Actionable part | Final status |
|---|---|---|---|
| 双 credential fixture 模式缺少使用边界说明 | accepted, non-blocking | 只补两个 shared helper 的中文 docstring，明确完整 assembly/compactor 路径；不批量修改 mock-assembly 测试 | 已修复 |
| 根 README 未显式说明跨 family override 与 compactor 解耦 | accepted, non-blocking | 补充 init-selected / package-default family 与 invocation override 的关系 | 已修复 |

DS 建议中的逐个 mock 测试注释、移除 mock credential 或新增 lint/type mechanism
不属于本次 accepted actionable part；这些路径不消费 compactor assembly，批量修改会
扩大 scope，未实施。production diff 保持为空。

## Retained provider report

按用户要求没有重新调用 provider。只读复用 S5-B 已验证的正式 report：

`workspace/tmp/wu-cli-init-01/20260730T112936Z-a86f5ccdeab5/matrix-report.json`

- SHA-256：
  `b3eb7a1a83f384a7274c9ad253d221d5dfd5dbd61e763830859397d59c6786c0`
- rows：15
- `available`：7
- `credential_missing`：3
- `endpoint_unconfigured`：1
- `provider_rejected`：2
- `rate_limited`：2
- internal contract valid：15/15
- canonical no-fallback valid：15/15
- report secret scan：pass
- overall exit：0
- persistence violations：0
- Host SQLite accepted observation records：10，分布于 10 rows；exact-byte match
  count 合计 20，只表示 bounded scanner match，不表示业务事件数量

外部 unavailable 分类不构成 product failure；report 中没有
`internal_product_bug`、unclassified row、fallback 或 secret-scan failure。

## Tests 与验证

所有命令均在 `source .venv/bin/activate` 后运行。

### 首次 aggregate focused 与 root-cause classification

完整 focused suite 首次结果：

```text
16 failed, 724 passed, 5 skipped, 3 warnings
```

16 个失败全部为上述 `missing env MIMO_PLAN_API_KEY`。首次 coverage run 复现同一
16 个失败；这份失败证据没有被隐去或改写。

### Scope-exception fix validation

原 16 个失败节点精确复跑：

```text
16 passed, 3 warnings
```

两份完整测试文件：

```text
pytest tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_command.py -q
93 passed, 3 warnings
```

第 12 节完整 focused suite：

```text
740 passed, 5 skipped, 3 warnings
```

skip 均为既有平台能力分支；warnings 均来自 `edgar` deprecated import，不是本 WU
失败或新增 warning。

### Coverage

完整 focused coverage 同样为 `740 passed, 5 skipped`。结果：

| File | Coverage |
|---|---:|
| `dayu/cli/arg_parsing.py` | 100% |
| `dayu/cli/session_execution.py` | 80% |
| `dayu/cli/commands/init.py` | 95% |
| `dayu/cli/init_catalog.py` | 90% |
| `dayu/cli/init_workspace.py` | 87% |
| `dayu/runtime/assembly.py` | 92% |
| `dayu/service/host_assembly.py` | 95% |
| `utils/smoke_cli_init_provider_matrix.py` | 81% |
| aggregate | 88% |

全部列入计划的 owner 文件达到不低于 80% 的目标。

### Pyright

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

### README stale-surface scan

- 根、Config、Service README 中 `--model-name`：零命中。
- Tests README 中 `--model-name`：唯一命中是“拒绝旧参数”的当前负向测试事实。
- 旧“PRESERVE 只补 prompt”：零命中。
- `conversation_compaction` / run / compactor baseline 使用旧 DeepSeek package
  default 的描述：零命中。
- accepted plan broad scan 的其余命中只包含：
  - parser owner 的 `init` `--config` 拒绝；
  - `init` `--config` 前后位置负向测试；
  - `--model-name` help absence / parser rejection 负向测试。
- production、用户命令示例、current positive test 与 smoke invocation 中没有 stale
  public surface。

### Diff checks

- `git diff --check`：pass。
- 相对 `48567008` 的变更只包含本 artifact、四份 README 与 Controller 明确允许的
  两份测试文件。
- production diff：empty。
- frozen manifest SHA-256 保持：
  `a4865273f11ce059aaabaf9d91ee1154a7f5c1f26794828c343a20e0e73cea88`。
- 未 commit。

### DS review follow-up validation

两个 shared helper 各选一个经过完整 assembly/compactor 路径的最小节点：

```text
pytest -q \
  tests/cli/test_prompt_command.py::test_prompt_tty_runtime_display_closes_thinking_before_activity_and_final \
  tests/cli/test_interactive_command.py::test_interactive_sigint_after_run_id_cancels_host_run
2 passed, 3 warnings
```

warnings 仍是既有 `edgar` deprecated import。follow-up 没有修改运行逻辑，前述完整
focused、coverage 与 pyright 证据保持有效。follow-up 后再次执行
`git diff --check`：pass。

## Findings fixed

| Finding | Decision | Final status |
|---|---|---|
| S3 package Mimo compactor baseline 后 prompt fixture 缺少 Mimo credential input | Controller accepted scope exception | 已修复 |
| S3 package Mimo compactor baseline 后 interactive fixture 缺少 Mimo credential input | Controller accepted scope exception | 已修复 |

修复后没有 production fallback、credential owner 漂移或测试绕过。

## Residual risks 与 uncovered areas

1. Retained provider availability 是该次真实 run 的环境事实，没有在 S6 重试。
   - classification：`assigned to environment/provider owner`
   - 当前证据：15/15 internal/no-fallback valid，overall exit 0
2. 真实 Windows junction/reparse 与 `setx` nodes 未在本地 Darwin 执行。
   - classification：`tracked by existing issue`
   - owner：GitHub Issue #184 的跨平台 CI
3. Host SQLite retained resolved credential 属于 accepted canonical observation，
   不是 violation 或 deferred finding；非 Host SQLite artifact 与 canary 仍由
   harness fail closed。

没有未分类 residual risk、blocking open question 或 deferred S6 finding。

## Completion

- Completion signal：`pass`
- Stop condition：`none`
- 初始 stop condition：focused tests 的 16 个同源 fixture failure
- Resolution：Controller scope exception 后在测试 fixture owner 修复并完成全部
  revalidation
- Commit：未创建
- Next entry point：S6 re-review / Controller adjudication
