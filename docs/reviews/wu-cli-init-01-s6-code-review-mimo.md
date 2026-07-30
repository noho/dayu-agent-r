# WU-CLI-INIT-01 S6 Code Review（re-review）

## Scope

- Mode: current changes
- Branch: `ci/pr-179-first-ci-readiness`
- Base: `48567008`
- Output file: `docs/reviews/wu-cli-init-01-s6-code-review-mimo.md`
- Included scope:
  - `README.md`
  - `dayu/config/README.md`
  - `dayu/service/README.md`
  - `tests/README.md`
  - `tests/cli/test_prompt_command.py`
  - `tests/cli/test_interactive_command.py`
  - `docs/reviews/wu-cli-init-01-s6-implementation-codex.md` (S6 implementation artifact)
  - `docs/reviews/wu-cli-init-01-s6-code-review-ds.md` (DS finding)
- Excluded scope: none
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Codex Follow-up 复核

### 1. README 跨 provider-family --model/compactor 描述

**DS Finding 2**：根 README 中 `--model/-m` 说明未显式记录跨 family override 的合法性和 compactor 解耦边界。

**Codex Follow-up**（`README.md:203-206`）：
```markdown
- `--model ID` / `-m ID`：只覆盖本次主 Run 的模型配置；不写入 workspace，也不改变
  会话压缩模型。即使本次主 Run 显式选择不同的 provider family，会话压缩仍使用
  `init` 选择的 family；未执行 `init` 时使用包内默认 family，不跟随单次 override。
  `interactive` 与 `session resume` 使用相同参数。
```

**复核结论**：
- ✅ 正确说明了跨 family override 合法
- ✅ 正确说明了 compactor 不跟随单次 override
- ✅ 正确说明了未执行 `init` 时使用包内默认 family
- ✅ 与 Service README 的描述一致（`dayu/service/README.md:34`："跨 family 的单次 ordinary override 合法，只改变该次 ordinary selection，不写配置，也不改变 compactor selection"）
- ✅ 与 Tests README 的描述一致（`tests/README.md:286`："单次跨 family ordinary override 不改变 compactor"）

**符合 DS Finding 2 建议**。

### 2. 两个 _runtime_assembly_env docstring

**DS Finding 1**：test fixture 存在双 credential 模式，不含编译期防护。建议在 `_runtime_assembly_env()` 的 docstring 中明确说明它适用于"经过完整 `prepare_entrypoint_runtime` → Service assembly 的测试"。

**Codex Follow-up**（`tests/cli/test_prompt_command.py:122-133` 和 `tests/cli/test_interactive_command.py:105-116`）：
```python
def _runtime_assembly_env() -> dict[str, str]:
    """构造 prompt 测试完整 runtime assembly 所需的环境输入。

    本 helper 仅供经过完整 ``prepare_entrypoint_runtime -> Service assembly ->
    compactor`` 装配路径的测试使用；mock-assembly 测试继续只声明自身消费的输入。

    :returns: 同时满足单次 DeepSeek ordinary override 与 package Mimo compactor
        baseline 的环境变量映射。
    :raises Exception: 本函数不主动抛出异常。
    """
```

**复核结论**：
- ✅ 两个文件的 docstring 一致
- ✅ 明确说明了 helper 的使用范围："经过完整 `prepare_entrypoint_runtime -> Service assembly -> compactor` 装配路径的测试"
- ✅ 明确说明了 mock-assembly 测试的处理方式："mock-assembly 测试继续只声明自身消费的输入"
- ✅ 符合 DS Finding 1 建议

**符合 DS Finding 1 建议**。

### 3. mock/production 零扩散

**检查项**：
- ✅ 测试修改只涉及将 `env={"DEEPSEEK_API_KEY": _API_KEY}` 替换为 `env=_runtime_assembly_env()`
- ✅ 没有修改 production code
- ✅ 没有修改 ConfigLoader、Service assembly、package config、provider harness、retained evidence 或 frozen manifest
- ✅ 没有逐测试 monkeypatch
- ✅ 没有降低 secret resolution

**结论**：mock/production 零扩散。

### 4. S6 Implementation Artifact 的裁决与验证

**S6 Implementation Artifact 裁决**：PASS

**DS Finding 验证**：
- ✅ Root Cause Verification：16 个失败全部为 `missing env MIMO_PLAN_API_KEY`，root cause 是 S3 package compactor baseline 从 DeepSeek 迁移到 Mimo Token Plan 后，测试 fixture 未随 credential 需求迁移
- ✅ 修复验证：`_runtime_assembly_env()` helper 被 4 处使用，修复后原 16 个失败节点精确复跑：`16 passed`
- ✅ Aggregate Validation：完整 focused suite `740 passed, 5 skipped, 3 warnings`，coverage 和 pyright 均通过
- ✅ Host SQLite Accepted Oracle：retained provider report SHA-256 匹配，Host SQLite observation 正确分类为 accepted observation
- ✅ Semantic Ownership Check：四份 README 的架构边界描述与代码实现一致，没有语义漂移、错误归属或 stale surface

**结论**：S6 Implementation Artifact 的裁决与验证正确。

## 详细审查

### 1. README 更新约束合规性

#### 1.1 根 README (`README.md`)

**更新约束**：只写用户完成安装、初始化、配置、财报下载 / 上传 / 预处理、提问、交互式分析、Session 管理、查看日志与排障所需的当前可用操作；不写 Host / Engine / Service / Runtime / Fins 内部架构、公共契约细节、状态机、测试清单、代码阅读顺序、review / work unit 过程状态或开发者迁移计划。

**变更内容**：
- `init` 不接受 `--config` 的说明（面向用户命令参数）
- PRESERVE 补齐五个根配置文件（面向用户初始化行为）
- 普通文件占据的拒绝/修复规则（面向用户排障）
- 模型选择、动态模型名、endpoint、上下文窗口、secret 与 yes/no 输入不合法时重新输入（面向用户交互行为）
- RESET 确认输入与退出码（面向用户交互行为）
- 环境变量示例从 `DEEPSEEK_API_KEY` 改为 `MIMO_PLAN_API_KEY`（面向用户配置）
- 包内默认模型家族说明（面向用户配置）
- `--config` 参数说明更新为"除 `init` 外"（面向用户命令参数）
- `--model-name` 改为 `--model` / `-m`（面向用户命令参数）
- **新增**：跨 provider family override 的合法性和 compactor 解耦边界说明（面向用户配置）

**结论**：所有变更均在用户可见操作范围内，不涉及内部架构或治理术语。符合更新约束。

#### 1.2 Config README (`dayu/config/README.md`)

**职责边界**：说明当前 `dayu/config/` 的默认配置、workspace root 下 `config/` 覆盖关系与 prompts 目录职责。

**变更内容**：
- PRESERVE 补齐五个根配置文件（配置 schema 与有效值）
- 普通文件占据的拒绝/修复规则（配置初始化行为）
- 15 个 init choice 的 ordinary / thinking pair 必须解析到相同 provider/model/endpoint/credential ref（配置 schema 有效值）
- 动态模型 context window 约束（配置 schema 有效值）
- 四个 package execution profile 的 baseline model id（配置 schema 有效值）
- `conversation_compaction` manifest 的 model.default_model_id（配置 schema 有效值）

**结论**：所有变更均在配置 schema 与有效值范围内，不涉及 Engine、Host、Service 内部机制。符合职责边界。

#### 1.3 Service README (`dayu/service/README.md`)

**职责边界**：说明 Service 如何把 runtime typed config、locations、工具发现、prepared scene、显式 override 与 env/secret mapping 映射为 Host public typed inputs。

**变更内容**：
- 模型装配的三个 typed selection：primary default、ordinary effective、compactor effective（Service 装配逻辑）
- primary/compactor resolved family mismatch 在 Host 打开前 fail closed（Service 校验逻辑）
- 单次跨 family ordinary override 不改变 compactor（Service 装配逻辑）

**结论**：所有变更均在 Service 装配与校验逻辑范围内，不涉及 Host、Engine 内部机制。符合职责边界。

#### 1.4 Tests README (`tests/README.md`)

**职责边界**：说明测试覆盖、命令和验证。

**变更内容**：
- 完整 focused/coverage 命令（测试命令）
- 冻结的 5-directory / 43-file / 16-pointer publication manifest（测试真值）
- 真实 15-choice provider matrix 命令与验证（测试命令与验证）
- CLI 测试覆盖更新：新增 `init` 拒绝 `--config`、Agent surfaces 使用 `--model/-m` 且拒绝旧 `--model-name`、PRESERVE 根配置/prompt 补缺、ordinary-root repair、target effective profile context minimum、可恢复输入原步骤 retry、EOF/confirmation exit（测试覆盖说明）
- host assembly 测试覆盖更新：primary default、ordinary invocation override 与 compactor selection 各自独立求值，primary/compactor resolved family mismatch 在 Host 打开前 fail closed，单次跨 family ordinary override 不改变 compactor（测试覆盖说明）

**结论**：所有变更均在测试覆盖与验证范围内。符合职责边界。

### 2. Stale 参数检查

**检查项**：
- `--model-name`：仅在 tests/README.md 中出现，且是说明"拒绝旧 `--model-name`"，为当前负向测试事实，非 stale 参数。
- 旧"PRESERVE 只补 prompt"：零命中。
- `conversation_compaction` / run / compactor baseline 使用旧 DeepSeek package default：零命中。
- `DEEPSEEK_API_KEY` 作为默认环境变量：已在 README 示例中更新为 `MIMO_PLAN_API_KEY`。

**结论**：无 stale 参数。

### 3. 测试 Fixture Migration 检查

**变更内容**：
- `tests/cli/test_prompt_command.py`：新增 `_runtime_assembly_env()` helper，返回 `{"DEEPSEEK_API_KEY": _API_KEY, "MIMO_PLAN_API_KEY": _API_KEY}`，被 `_prepare_prompt_runtime()`、`test_prompt_sigint_after_run_id_cancels_host_run()`、`test_prompt_sigint_before_run_id_returns_local_interrupt()` 三处使用。
- `tests/cli/test_interactive_command.py`：新增 `_runtime_assembly_env()` helper，返回相同映射，被 `_prepare_interactive_runtime()` 一处使用。

**检查项**：
- 唯一共享 env owner：两份测试文件各自有唯一的 `_runtime_assembly_env()` helper，所有需要 runtime assembly env 的测试都复用该 helper。
- 最小迁移：只增加 `MIMO_PLAN_API_KEY`，保留 `DEEPSEEK_API_KEY`，满足单次 DeepSeek ordinary override 与 package Mimo compactor baseline。
- 无逐测试补丁：所有修改都是将 `env={"DEEPSEEK_API_KEY": _API_KEY}` 替换为 `env=_runtime_assembly_env()`，没有逐测试 monkeypatch。
- 无生产兼容：没有修改 production、ConfigLoader、Service assembly、package config、provider harness、retained evidence 或 frozen manifest。
- **新增**：docstring 明确说明 helper 使用范围，mock-assembly 测试继续只声明自身消费的输入。

**结论**：符合"唯一共享 env owner 最小迁移 MIMO_PLAN_API_KEY+DeepSeek、无逐测试补丁/生产兼容"要求。

### 4. 740 passed/coverage/pyright 证据检查

**S6 Implementation Artifact 声明**：
- 首次完整 focused suite：`16 failed, 724 passed, 5 skipped, 3 warnings`
- 16 个失败全部为 `missing env MIMO_PLAN_API_KEY`
- 原 16 个失败节点精确复跑：`16 passed, 3 warnings`
- 两份完整测试文件：`93 passed, 3 warnings`
- 第 12 节完整 focused suite：`740 passed, 5 skipped, 3 warnings`
- Coverage：完整 focused coverage 同样为 `740 passed, 5 skipped`，所有列入计划的 owner 文件达到不低于 80% 的目标
- Pyright：`0 errors, 0 warnings, 0 informations`

**检查项**：
- 证据完整性：S6 Implementation Artifact 记录了首次失败、修复后复跑、完整 suite、coverage 和 pyright 的完整证据链。
- 证据一致性：首次失败的 16 个节点与修复后复跑的 16 个节点精确对应，没有隐去或改写失败证据。
- 证据可信度：所有命令均在 `source .venv/bin/activate` 后运行，符合项目测试规范。

**结论**：740 passed/coverage/pyright 证据完整、一致、可信。

### 5. Host SQLite Accepted Oracle 检查

**S6 Implementation Artifact 声明**：
- Host SQLite retained resolved credential 属于 accepted canonical observation，不是 violation 或 deferred finding。
- 非 Host SQLite artifact 与 canary 仍由 harness fail closed。

**检查项**：
- Host SQLite accepted observation records：10，分布于 10 rows；exact-byte match count 合计 20，只表示 bounded scanner match，不表示业务事件数量。
- 外部 unavailable 分类不构成 product failure。
- report 中没有 `internal_product_bug`、unclassified row、fallback 或 secret-scan failure。

**结论**：Host SQLite accepted oracle 没有被误写。

### 6. Provider 重跑检查

**S6 Implementation Artifact 声明**：
- 按用户要求没有重新调用 provider。只读复用 S5-B 已验证的正式 report。

**检查项**：
- Retained provider report：`workspace/tmp/wu-cli-init-01/20260730T112936Z-a86f5ccdeab5/matrix-report.json`
- SHA-256：`b3eb7a1a83f384a7274c9ad253d221d5dfd5dbd61e763830859397d59c6786c0`
- rows：15，`available`：7，`credential_missing`：3，`endpoint_unconfigured`：1，`provider_rejected`：2，`rate_limited`：2
- internal contract valid：15/15
- canonical no-fallback valid：15/15
- report secret scan：pass
- overall exit：0
- persistence violations：0

**结论**：没有要求 provider 重跑，只读复用 S5-B 已验证的正式 report。

## Open Questions

无。

## Residual Risk

S6 Implementation Artifact 已识别的 residual risks：

1. Retained provider availability 是该次真实 run 的环境事实，没有在 S6 重试。
   - classification：`assigned to environment/provider owner`
   - 当前证据：15/15 internal/no-fallback valid，overall exit 0
2. 真实 Windows junction/reparse 与 `setx` nodes 未在本地 Darwin 执行。
   - classification：`tracked by existing issue`
   - owner：GitHub Issue #184 的跨平台 CI
3. Host SQLite retained resolved credential 属于 accepted canonical observation，不是 violation 或 deferred finding；非 Host SQLite artifact 与 canary 仍由 harness fail closed。

这些 residual risks 均已明确分类和归属，不构成 blocking issue。

## Review Conclusion

**PASS**

本次 re-review 检查了以下重点：
1. README 跨 provider-family --model/compactor 描述 → **通过**（Codex Follow-up 正确）
2. 两个 _runtime_assembly_env docstring → **通过**（Codex Follow-up 正确）
3. mock/production 零扩散 → **通过**
4. S6 implementation artifact 的裁决与验证 → **通过**（裁决正确，验证完整）

未发现 blocking findings。Codex 的 follow-up 改动精准、可验证、符合 DS finding 建议。S6 implementation 的所有改动都符合设计意图和项目约束。
