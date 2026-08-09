# WU-CLI-CONFORMANCE-F01-F07 S5/F05 Implementation 记录（Codex）

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- PR：`190`
- Slice：`S5 / F05 — 只从 interactive effective tool set 移除 preprocess`
- Gate：`implementation`
- Entry HEAD：`c556df2bc6d175f34b7a80c3a83cf1b079e61cc7`
- 分支：`codex/interactive-oracle`
- 执行日期：2026-08-03（Asia/Shanghai）
- 状态：`IMPLEMENTATION COMPLETE — next: independently dispatched code review`
- Artifact：`docs/reviews/wu-cli-conformance-f01-f07-s5-implementation-codex.md`

本记录只覆盖 accepted plan
`docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md` §7、frozen F05
oracle/scenario、`docs/cli_ci.md` 与 design truth 约束下的 implementation 和
implementation validation。按用户约束，本轮不执行自我 code review、deepreview、stage、
commit、push 或 PR 操作，也不替代后续独立 code-review artifact。

## Preflight、第一性原理判断与语义 owner

Preflight 确认当前分支为 `codex/interactive-oracle`，entry 工作区干净且不是 protected
trunk。F05 动机成立，且严重性评估与直接代码/数据证据同源：

- 真实 `dayu/config/prompts/manifests/interactive.json` 的
  `tool_tags_any` 原本明确包含 `fins-preprocess`。
- `prepare_entrypoint_runtime()` 先做真实 provider discovery，再把真实 scene manifest 与
  discovered tool catalog 交给 `prepare_scene()`；其选择结果随 Service submit request 进入
  Host admission。
- Host admission 冻结 selected business tool facts，dispatch 再从同一 selected names 构造
  effective bundle 和最终 `AgentRunRequest.tool_schemas`。因此当前 manifest tag 会让
  `start_fins_preprocess` 进入 interactive 的最终 LLM-facing schema；这不是测试夹具推断。
- frozen oracle `interactive.28-tool-registration-boundary` 与 accepted scenario
  `interactive.interactive.tool-registration.no-preprocess` 明确要求 interactive 保留财报读取、
  下载，但不向 Host 注册 `start_fins_preprocess`；独立 preprocess 实现仍须保留。

语义 owner 是 interactive scene manifest；Service/CLI/Host 只机械消费 scene selection，Fins
provider/实现拥有独立 preprocess 能力。正确修复只删除 manifest 的一个 capability tag。
在 CLI/Service 按 tool name 过滤会复制语义并掩盖 owner 错误；删除 provider/实现会破坏独立
preprocess contract。两种路径均未采用。当前 owner 清晰，无 blocker，也不需要新增配置层、
feature flag、兼容分支或第二套 tool-selection policy，因此没有过度设计。

## 实际 scope 与变更

唯一生产变更：

- `dayu/config/prompts/manifests/interactive.json`
  - 仅从 `tool_selection.tool_tags_any` 删除 `fins-preprocess`。
  - `fins-read`、`fins-download`、`web`、`utils` 的值与顺序不变。
  - 其它 tag、scene/model/runner hint/agent policy/default/fragment/context slot/config 字段均不变。

Owner-level tests 只修改 accepted plan §7.1 允许的四个文件：

- `tests/runtime/test_scene_assets_migration.py`
  - 把 interactive 与 WeChat 期望拆开；interactive 保留 list/read/download/time，排除
    preprocess/upload 及对应 LLM-facing guidance；WeChat 继续服从自身 manifest 并保留
    preprocess。
- `tests/runtime/test_scene_prepare.py`
  - 锁定 interactive 精确剩余 tag 顺序与完整 `tool_selection` 配置；默认 scene contract
    不再把 interactive 与 WeChat 的 long-transaction set 混为一谈。
- `tests/service/test_entrypoint_runtime_interactive_path.py`
  - 真实读取 package manifest，走真实 discovery、scene prepare、Service assembly、真实 Host
    admission/dispatch，并在记录型 deterministic Engine worker 收到的最终
    `AgentRunRequest.tool_schemas` 上断言：无 `start_fins_preprocess`，仍有
    `start_fins_download`、`list_documents`、`read_section`。
- `tests/tools/test_combined_tools_acceptance.py`
  - 直接经独立 `preprocess_provider` 发现唯一 `start_fins_preprocess` 定义，并真实调用其
    callable，断言返回 external-job awaiting outcome；证明实现/provider 没有被删除或禁用。

另新增本 implementation artifact。没有修改 CLI、Service、Host、Engine、Fins production、
README、design、oracle/scenario、registry 或其它文件；没有 stage、commit、push 或操作 PR。

## Manifest before/after 与行为不变量

Entry HEAD 的 manifest selection：

```json
{"mode":"select","tool_names":[],"tool_tags_any":["fins-read","fins-download","fins-preprocess","web","utils"],"allow_empty":false}
```

当前 working tree 的 manifest selection：

```json
{"mode":"select","tool_names":[],"tool_tags_any":["fins-read","fins-download","web","utils"],"allow_empty":false}
```

真实 Host effective schema owner test 的必要集合结果：

```text
start_fins_preprocess  absent
start_fins_download    present
list_documents        present
read_section           present
```

同时保持以下不变量：

- discovery business bundle 与 preprocess provider 仍包含 `start_fins_preprocess`；只有
  interactive per-Run selected/effective schema 排除它。
- 独立 preprocess callable 仍创建 typed external-job awaiting observation。
- WeChat 仍由自身 manifest 选择 preprocess；没有从 interactive 期望反推其它 scene。
- download/list/read 与当前时间工具仍由同一 manifest → prepare → Host effective schema 真源
  产生。
- 未引入 name blacklist、`hasattr/getattr`、fallback、compatibility shim 或测试 fake name set。

## 验证结果

### JSON 与 focused pytest

执行：

```bash
source .venv/bin/activate
python -m json.tool dayu/config/prompts/manifests/interactive.json >/dev/null
pytest \
  tests/runtime/test_scene_assets_migration.py \
  tests/service/test_entrypoint_runtime_interactive_path.py \
  tests/runtime/test_scene_prepare.py \
  tests/tools/test_combined_tools_acceptance.py \
  -q
```

结果：manifest JSON 严格解析通过；`79 passed, 3 warnings in 6.30s`。三条 warning 均来自
`edgar` 依赖的既有 deprecation warning。

### Coverage applicability

Accepted plan §11.1 的 `>=80%` 单文件门槛适用于“每个修改 Python production 文件”。S5
唯一 production 变更是 JSON manifest，没有修改 Python production 文件，因此本 slice
没有可计算的 Python production coverage target，coverage gate 为 `N/A`。本记录不使用
Service/Host/Fins 未修改模块的总平均伪造单文件 coverage；行为改动由上述四组 owner/integration
tests 覆盖。

### Pyright 与静态检查

- focused：
  `python -m pyright dayu/config tests/runtime/test_scene_assets_migration.py tests/service/test_entrypoint_runtime_interactive_path.py tests/runtime/test_scene_prepare.py tests/tools/test_combined_tools_acceptance.py`
  → `0 errors, 0 warnings, 0 informations`。
- full：`python -m pyright dayu/ tests/ utils/`
  → `0 errors, 0 warnings, 0 informations`。
- focused Ruff：四个修改测试文件 `All checks passed!`。
- `git diff --check`：通过。

### Frozen truth、zero-diff 与 working hashes

Frozen/read-only truth digest 均与 accepted plan 基线一致：

- `docs/cli_ci_oracles.json`：
  `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`
- `docs/cli_ci_scenarios.json`：
  `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`
- `docs/cli_ci.md`：
  `a241182d4d09e8843ea647947777bc7f6f71c5532fa148e2abb87ede3e748b82`
- `docs/host/design.md`：
  `7bd4059f7f4c43dcc9e6ab1e7a650c950c9724283d568137c3d98f6e4be127a0`

Manifest SHA-256 从 entry baseline
`050800d1dfd4d31a28d89b5069132fa803195192ac7b27a929cc3aefe94815bf`
变为
`69339ac8dbcdd3779b710140400037294458fff564048e80423b3474790426e7`。

测试文件当前 SHA-256：

- `tests/runtime/test_scene_assets_migration.py`：
  `d531e882d9160b1247fb5d623344e248eea93b6ff318cc530e482c6beba1c916`
- `tests/service/test_entrypoint_runtime_interactive_path.py`：
  `eef1705000de3ba01a007b3da2a0483c829df94992db27cf8276ac89f8a84675`
- `tests/runtime/test_scene_prepare.py`：
  `8b70464dc1d4b37c3ceb5ee49bc6328430b278962337fa1002aee888867f0a17`
- `tests/tools/test_combined_tools_acceptance.py`：
  `efdb97a37533b64eadfccd7e9d3f65660ca4d879f71f823a2a42c11cb1b114f0`

保留实现/provider SHA-256：

- `dayu/fins/tools/preprocess_tools.py`：
  `f258bd658109e1194632d111663c7758b2408c07c05b20d0dafa144f6d36da7a`
- `dayu/fins/tools/preprocess_provider.py`：
  `38b8fbd0560ad2a4f9e31878f894bdfdfc346c9468d0787fe615d54698225e96`

对 `dayu/fins/tools/preprocess_tools.py`、`preprocess_provider.py`、`dayu/cli`、
`dayu/service`、`dayu/host`、`dayu/engine` 执行 `git diff --exit-code` 均为零 diff。
artifact 创建前的 working diff 精确为 manifest 加四个测试文件，index 为空；frozen registry
既不 dirty 也未 staged。

## Docs decision

用户明确要求 README 延迟到 S8，accepted plan §7.1/§7.2 也冻结本 slice 不修改
`dayu/config/README.md`、根 `README.md` 或其它 README。当前只实现已裁决的 scene capability
边界，不在 S5 重写最终用户工作流说明；README/design/registry 均保持不变。

## Residual risks 与未覆盖项

- `LOW / covered by later approved slice S8`：frozen scenario 要求在 fixed clean commit 上重跑
  真实 provider 的 interactive effective tool set 与 download/list/read 跨轮链。本 S5 已以真实
  manifest/discovery/Service/Host/Engine owner test闭合静态与本地 integration contract，但未
  越权执行或更新 S8 的 immutable CLI evidence bundle。
- `LOW / covered by later approved slice S8`：真实 LLM 是否在 download 后选择正确 list/read
  路径属于 provider/evidence 稳定性，不是本 slice 的 tool registration owner。最终 schema 已
  证明能力存在；真实模型行为留给 frozen scenario 重跑。
- 没有未分类 residual risk、design/oracle 冲突、implementation blocker 或需删除实现/下游
  name filtering 的条件。后续独立 code-review findings 尚未产生，本 artifact 不预判或裁决
  review finding。

## Completion 与下一入口

S5/F05 implementation、owner/integration tests、focused/full pyright、JSON、Ruff、diff、
allowlist 与 frozen hash 检查均完成。工作树保持未 staged；未 commit、push 或操作 PR。
按用户要求在 implementation gate 停止，下一合法入口是独立 code review。
