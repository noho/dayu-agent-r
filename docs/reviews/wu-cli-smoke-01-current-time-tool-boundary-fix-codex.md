# WU-CLI-SMOKE-01 current_time / get_current_time 语义边界修正

## Gate: goal confirmation

### Work unit

实现 `current_time` 与 `get_current_time` 的 LLM-facing 语义边界修正。

### 第一性原理判断

动机成立。系统同时向模型提供静态的当前时间文本和可调用的实时时钟工具时，二者必须有清晰边界；否则模型会把普通“现在/今天”问题误升级为工具调用，或把对话开始时刻的静态文本误认为会自动刷新。当前代码证据显示：

- `dayu/config/prompts/manifests/prompt.json` 的 `tool_tags_any` 包含 `"utils"`，而 `dayu.tools.utils` provider 用 `"utils"` 暴露 `get_current_time`，导致单轮 `prompt` 会选择该工具。
- `dayu/config/prompts/manifests/interactive.json` 与 `dayu/config/prompts/manifests/wechat.json` 也通过 `"utils"` 选择该工具，符合用户裁决中交互入口保留实时时钟工具的边界。
- `dayu/service/scene_context.py` 的 `current_time()` 当前只输出 `# 当前时间` 和具体时间，没有说明这是对话开始时刻、普通“现在/今天”默认使用它、且不会自动更新。
- `dayu/tools/utils/provider.py` 的工具 description 只说明“获取当前日期和时间”，没有说明“只有明确要求此刻最新时间或动作完成后再确认时间时调用；普通问题不重新确认则使用上下文时间”。
- `tests/runtime/test_scene_assets_migration.py` 目前把 `prompt`、`interactive`、`wechat` 都列入 `_TIME_TOOL_SCENES`，并断言 `prompt` 选择 `get_current_time`，与本轮裁决冲突。

### 目标

- `prompt` 默认只消费 `{{current_time}}`，不选择 `get_current_time`。
- `interactive` 与 `wechat` 同时保留 `{{current_time}}` 和 `get_current_time`，并通过 LLM-facing 文本说明边界。
- 所有非 compact prompt 场景继续注入 `{{current_time}}`。
- 不改变既有 `fins_default_subject` 规则。
- LLM-facing 文本不得出现 Host、run input、context slot、scene、tool selection、内部模块名等内部术语。

### 非目标

- 不扩展 `get_current_time` 支持的时区；仍只支持 `Asia/Shanghai`。
- 不改变财报、网页、文件等其它工具选择策略。
- 不改变 compact prompt 机制。
- 不为旧 manifest 或旧测试保留兼容逻辑。
- 不新增抽象层或运行时机制。

### 成功信号

- 真实 ScenePrepare 装配中，`prompt` 不选择且不渲染 `get_current_time` 指引。
- `interactive` 与 `wechat` 继续选择并渲染 `get_current_time` 指引。
- 渲染后的 `current_time` 文本包含静态时间边界，且不含禁止暴露的内部术语。
- `get_current_time` 工具 description 包含调用条件与普通问题不调用的边界。
- 受影响测试、pyright、`git diff --check` 通过；README 触发项已检查并按需更新。

### Scope boundary

预计只触及：

- `dayu/config/prompts/manifests/prompt.json`
- `dayu/config/prompts/base/tools.md`
- `dayu/service/scene_context.py`
- `dayu/tools/utils/provider.py`
- `tests/runtime/test_scene_assets_migration.py`
- `tests/service/test_entrypoint_runtime.py`
- 必要时更新 `dayu/config/README.md` 与 `tests/README.md`

### 不做的过度设计

本轮不引入按入口类型动态生成工具描述、不新增时间策略配置、不把静态时间和实时时钟抽象成新的公共接口。现有 manifest tag、prompt 条件块、Service slot 文本生成和 tool schema 已能表达用户裁决，最小可维护修正是收窄 `prompt` 的 `"utils"` tag 并补足 LLM-facing 文案与测试。

### Blocking open questions

无。当前需求、代码证据和用户裁决足以进入 plan。

### Gate status

- Decision: goal confirmation ready for user confirmation
- Controller confirmation: user has instructed continuing without waiting for another confirmation
- Next entry point: plan

## Gate: plan

### Goal / motivation / success signal

目标是修正静态 `current_time` 文本与可调用 `get_current_time` 工具的模型可见边界。成功信号：

- `prompt` 装配后不选择 `get_current_time`，系统提示中也不出现该工具指引。
- `interactive` 与 `wechat` 装配后仍选择 `get_current_time`，系统提示中保留该工具指引。
- 所有非 compact prompt 场景继续渲染 `{{current_time}}`；`fins_default_subject` 规则不变。
- `current_time` 渲染文本说明“对话开始时的当前时间”“普通现在/今天/当前时间默认使用它”“不会自动更新”，且不含禁止暴露的内部术语。
- `get_current_time` 工具 description 与 prompt 指引说明“调用这一刻”“明确要求此刻最新时间或动作完成后再确认时间才调用”“普通问题不需要重新确认就不用调用”。

### Non-goals / scope boundary

- 不扩展时区、返回字段或工具执行语义。
- 不改 compact prompt。
- 不改财报下载、预处理、上传、网页或文件工具选择策略。
- 不改变 `fins_default_subject` 的声明、生成或放置规则。
- 不引入新配置 schema、新 runtime 抽象或兼容旧接口。

### Design document alignment

无单独 design document。本轮以用户裁决、AGENTS.md 约束和代码真源为依据。

### First-principles judgment and direct code evidence

动机成立：静态时间与实时工具同时存在时，如果边界不清晰，模型会过度调用工具或误读静态时间。直接证据：

- `prompt.json` 当前 `tool_tags_any` 含 `"utils"`，因此通过 utils provider 选中 `get_current_time`。
- `interactive.json` 与 `wechat.json` 也含 `"utils"`，符合保留工具的目标。
- `current_time()` 当前输出只包含标题和具体时间，不说明静态边界。
- `build_get_current_time_tool_definition()` 当前 description 只描述字段，不说明调用时机边界。
- `tests/runtime/test_scene_assets_migration.py` 当前 `_TIME_TOOL_SCENES` 含 `prompt`，需要随新裁决更新。

### Affected files/modules

- `dayu/config/prompts/manifests/prompt.json`
- `dayu/config/prompts/base/tools.md`
- `dayu/service/scene_context.py`
- `dayu/tools/utils/provider.py`
- `tests/runtime/test_scene_assets_migration.py`
- `tests/service/test_entrypoint_runtime.py`
- `dayu/config/README.md`
- `tests/README.md`
- `docs/reviews/wu-cli-smoke-01-current-time-tool-boundary-fix-codex.md`

### Contract/schema/state-machine/public-interface changes

- Manifest tool selection 行为变化：`prompt` 不再通过 `"utils"` 暴露 `get_current_time`。
- LLM-facing 文本语义变化：`current_time` 是对话开始时刻的静态文本；`get_current_time` 是明确刷新时钟的工具。
- 无 JSON schema、存储 schema、公共 Python API 或状态机变化。

### Implementation decisions

- 从 `prompt.json` 的 `tool_tags_any` 删除 `"utils"`；保留 `fins-read` 与 `web`。
- 保持 `interactive.json` 与 `wechat.json` 不变。
- 在 `current_time()` 返回的 Markdown 中追加短句说明静态时间边界，不使用内部术语。
- 将 `get_current_time` tool description 改为完整 LLM-facing 调用规则；同步 `base/tools.md` 的条件块指引。
- 更新测试常量和断言：`_TIME_TOOL_SCENES` 只包含 `interactive`、`wechat`；新增或调整断言覆盖 prompt 不选、交互入口选择、渲染文本无内部术语、工具 description 规则存在。
- 按 README 触发规则检查并更新 `dayu/config/README.md` 与 `tests/README.md`。

### Small implementation slices

本 work unit 改动面小且同属一个 LLM-facing 边界，采用单 slice。

Slice S1:

- Objective: 完成配置选择收窄、LLM-facing 文案修正、测试和 README 同步。
- Allowed files: 上述 affected files。
- Exact changes: 仅修改 `prompt` 的 utils tag、`current_time` 文本、`get_current_time` 描述/指引、对应测试断言和 README 描述。
- Non-goals: 不改工具执行函数、时区支持、其它 scene 工具 tag。
- Completion signal: 受影响测试、pyright、`git diff --check` 通过，artifact 记录验证与风险。

### Tests/validation commands and expected assertions

- `source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py tests/service/test_entrypoint_runtime.py -q`
  - 期望：`prompt` 不选择 `get_current_time`；`interactive` / `wechat` 选择；`current_time` 文本与无内部术语断言通过。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 期望：无新增或扩散类型错误。
- `git diff --check`
  - 期望：无 whitespace error。

必要时增加组装级验证：用真实 `prepare_scene` 测试覆盖装配输出，无需真实 LLM 调用。

### Docs decision

修改 `dayu/config/` 和 `tests/`，触发检查 `dayu/config/README.md` 与 `tests/README.md`。本轮行为属于配置和测试手册职责范围，计划按实际变化更新。

### Risks/open questions

- 风险：已有 smoke 文档中提到 prompt 可使用 `get_current_time` 的历史描述会过期；这些是历史 artifact，不作为当前说明真源，本轮不回写旧 review。
- Open questions: 无。

### Completion report format

最终说明包含：改了什么、验证了什么、README/design 更新、finding 状态、残余风险或未覆盖项。

### Gate status

- Decision: plan ready for plan review
- Plan review artifact: `docs/reviews/plan-review-20260707-214653.md`
- Plan review decision: pass
- Next entry point: implementation

## Gate: implementation

### Slice S1 summary

完成配置选择收窄、LLM-facing 文案修正、测试和 README 同步。

### Changed files

- `dayu/config/prompts/manifests/prompt.json`
  - 从 `tool_tags_any` 删除 `"utils"`，使 `prompt` 不再选择 `get_current_time`。
- `dayu/config/prompts/base/tools.md`
  - 更新 `get_current_time` 条件块，说明工具获取调用这一刻的当前时间，并限制调用条件。
- `dayu/service/scene_context.py`
  - 更新 `current_time()` 渲染文本，说明这是对话开始时的当前时间、普通“现在/今天/当前时间”默认使用它、该时间不会自动更新。
- `dayu/tools/utils/provider.py`
  - 更新 `get_current_time` tool schema description，说明调用边界和普通问题不调用规则。
- `tests/runtime/test_scene_assets_migration.py`
  - 更新 `_TIME_TOOL_SCENES` 为 `interactive` / `wechat`。
  - 覆盖 `prompt` 不选择且不渲染 `get_current_time`。
  - 覆盖 `interactive` / `wechat` 继续选择并渲染 `get_current_time`。
  - 新增 `current_time` 文本边界和禁止内部术语断言。
  - 新增 tool description 边界断言。
- `tests/service/test_entrypoint_runtime.py`
  - 更新 `current_time()` 与入口 slot builder 的固定文本断言。
- `tests/service/test_entrypoint_runtime_prompt_path.py`
  - 更新真实 prompt runtime 断言，确认 `get_current_time` 不进入 prompt 工具集合或 system prompt。
- `tests/service/test_entrypoint_runtime_interactive_path.py`
  - 同步 current_time 样本文本，保留 interactive 选择 `get_current_time` 的断言。
- `tests/cli/test_prompt_command.py`
  - 更新 prompt CLI submit request 断言，确认 Host 提交工具集合不含 `get_current_time`。
- `tests/cli/test_interactive_command.py`、`tests/runtime/test_scene_prepare.py`、`tests/service/test_host_assembly.py`
  - 同步 current_time 样本文本。
- `dayu/config/README.md`
  - 更新 `current_time` 静态边界和 `interactive` / `wechat` 才选择 `get_current_time` 的说明。
- `tests/README.md`
  - 更新 scene asset migration 测试覆盖说明。

### Implementation decisions

- 用 manifest tag 收窄 `prompt` 暴露面，不新增运行时过滤分支。
- 保持 `interactive` / `wechat` 的 `"utils"` tag 不变。
- 工具执行函数、参数 schema、tags、display name 和返回 payload 不变；只更新 LLM-facing description。
- `current_time` 文本不使用 Host、run input、context slot、scene、tool selection 或内部模块名。
- 未改变 `fins_default_subject` 的声明、生成、放置或测试断言。

### Implementation validation

- `source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/runtime/test_scene_prepare.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q`
  - Result: 179 passed, 3 dependency deprecation warnings.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.

### Docs decision

- `dayu/config/README.md`: 已更新，因修改 `dayu/config/` 且内容属于配置、prompt 和工具选择职责范围。
- `tests/README.md`: 已更新，因新增/调整测试覆盖说明且内容属于测试手册职责范围。
- 根 README、`dayu/README.md`、Engine / Host / Fins README：本轮没有改变用户可见安装、CLI 参数、分层关系、Host/Engine/Fins 内部机制或财报存储边界，未触发更新。

### Residual risks

- 未运行真实 LLM 端到端 smoke；当前风险主要是模型可见输入装配，已由真实 `ScenePrepare`、CLI prompt 和 Service runtime 测试覆盖。分类：accepted residual risk for local validation scope。
- 历史 `docs/reviews/` artifact 中仍可能描述旧行为；历史 artifact 不作为当前用户文档真源，本轮不回写。分类：assigned to historical artifact archive。

### Gate status

- Decision: implementation complete
- Next entry point: code review

## Gate: code review

### Artifact

- `docs/reviews/code-review-20260707-215217.md`

### Findings

未发现实质性问题。

### Residual risk classification

- 未执行真实 LLM 端到端调用：accepted residual risk for local unit/integration scope。

### Gate status

- Decision: code review pass, no fix required
- Next entry point: aggregate deepreview

## Gate: aggregate deepreview

### Artifact

- `docs/reviews/code-review-20260707-215256.md`

### Findings

未发现实质性问题。

### Validation reviewed

- 受影响 pytest：179 passed。
- pyright：0 errors。
- `git diff --check`：passed。

### Residual risk classification

- 未运行真实 LLM 端到端 smoke：accepted residual risk for local validation scope。

### Gate status

- Decision: aggregate deepreview pass
- Next entry point: final closeout

## Gate: final closeout

### What changed

- `prompt` 不再选择 `get_current_time`，默认只使用渲染进提示词的 `current_time` 文本。
- `interactive` 与 `wechat` 继续选择 `get_current_time`，并保留 `current_time` 文本。
- `current_time` 文本明确为对话开始时的当前时间，普通“现在 / 今天 / 当前时间”问题默认使用它，且不会自动更新。
- `get_current_time` 工具 description 和 prompt 指引明确：只有明确要求此刻最新时间，或要求在等待、查询、下载、上传、处理等动作完成后再确认时间时才调用。
- 测试和 README 已按新边界同步。

### What was verified

- `pytest tests/runtime/test_scene_assets_migration.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/runtime/test_scene_prepare.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q`: 179 passed, 3 dependency deprecation warnings.
- `python -m pyright dayu/ tests/ utils/`: 0 errors, 0 warnings, 0 informations.
- `git diff --check`: passed.

### Docs updates

- Updated `dayu/config/README.md`.
- Updated `tests/README.md`.

### Finding status

- Plan review: pass, no findings.
- Code review: pass, no findings.
- Aggregate deepreview: pass, no findings.

### Remaining risks / owners

- 未运行真实 LLM 端到端 smoke；owner: 当前 work unit 接受为本地验证残余风险。
- 历史 review artifact 仍可能含旧行为描述；owner: historical archive，不作为当前说明真源。

### Draft PR URL

未创建 draft PR。本轮按用户最新要求完成本地 implementation / tests / pyright / `git diff --check` / README 触发检查和 artifact 更新。

### Issue link status

本 work unit 未提供 issue number，不适用。

### Issue closeout comment status

本 work unit 未提供 issue number，不适用。

### Next entry point

final closeout pass；如需要发布，下一步是由用户决定是否 commit / push / draft PR。
