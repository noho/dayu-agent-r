# WU-CLI-SMOKE-01 context slot placement fix

- 执行人：AgentCodex
- 日期：2026-07-07
- 范围：用户确认的 `{{fins_default_subject}}` scene placement 修复
- 约束：不修改 Host/Engine 状态机、durable schema、Fins storage 协议；不 commit、不 push、不创建 issue/PR

## 动机

用户指出 `{{fins_default_subject}}` 会展开为完整 Markdown 块：

```markdown
# 当前分析对象
你正在分析的是 V（Visa Inc.）。
```

因此把占位符放在 scene H1 标题下会把 `# 当前分析对象` 插入到 scene 执行契约标题和主要任务/行为/输出规则之间，破坏 LLM-facing 契约结构。这个问题基于占位符展开形态和当前 scene 文本位置同源成立，需要在 S3 placement 层修复。

## 改动

- 只处理声明 `fins_default_subject` 的 11 个 scene：
  - `audit`
  - `confirm`
  - `decision`
  - `fix`
  - `infer`
  - `overview`
  - `prompt`
  - `regenerate`
  - `repair`
  - `smoke_host_public_multiturn`
  - `write`
- 将上述 scene 的 `{{fins_default_subject}}` 统一作为独立行移动到主要执行契约正文之后，并作为最后一个非空内容行。
- 保留用户已手工调整的 `dayu/config/prompts/scenes/prompt.md` 方向，只补齐 final newline。
- 未向 `interactive` / `wechat` 增加 manifest slot 或 scene placeholder。
- 更新 `tests/runtime/test_scene_assets_migration.py`：
  - 声明 `fins_default_subject` 的 scene 必须有且只有一个占位符。
  - 占位符必须是独立行。
  - 占位符必须晚于首个执行契约正文行。
  - 占位符必须是最后一个非空内容行，用于防止回归到 H1 标题下第 3 行。
  - Placement review accepted test fix：新增真实 packaged `ScenePrepare` 展开后 system prompt 顺序测试，对所有声明 `fins_default_subject` 的 scene 使用 `# 当前分析对象\n你正在分析的是 V（Visa Inc.）。` 作为 context slot value，并断言 scene H1、首个执行契约正文、`# 当前分析对象` 的顺序为标题在前、契约正文在中、默认研究主体块在后。
  - 对 `prompt` 额外断言 `- 输出 Markdown 格式。` 位于 `# 当前分析对象` 之前。

## README 判断

本次改动只调整已有 prompt asset 的 placement 和已有 migration invariant，没有改变 `dayu/config/` 的目录职责、manifest schema、ScenePrepare API、CLI 用户流程或测试分层边界。按 `dayu/config/README.md` 与 `tests/README.md` 当前职责，不做机械 README 更新。

## 验证

```bash
source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_scene_prepare.py
```

- 结果：51 passed。

```bash
source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime_prompt_path.py tests/cli/test_prompt_command.py
```

- 结果：41 passed，3 个来自 `edgar` 依赖的 deprecation warnings。

```bash
source .venv/bin/activate && pyright
```

- 结果：0 errors, 0 warnings, 0 informations。
- 附带提示：pyright 有新版本可用。

```bash
git diff --check
```

- 结果：通过，无输出。

## 风险与未覆盖

- 本次没有重跑真实 provider smoke；该修复只改变 scene asset 文本位置，已通过 source placement invariant、ScenePrepare 展开后 system prompt 顺序、prompt path 和 CLI prompt 单元测试覆盖。
- placement invariant 当前要求声明 `fins_default_subject` 的 scene 以该占位符作为最后一个非空内容行；这是对当前 scene 结构的有意收紧，若未来确需在主体上下文之后追加新契约文本，应先重新裁决 LLM-facing 顺序。
