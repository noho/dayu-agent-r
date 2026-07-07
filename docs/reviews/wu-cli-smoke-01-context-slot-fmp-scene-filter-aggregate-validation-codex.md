# WU-CLI-SMOKE-01 context slot / FMP / scene filtering aggregate validation

- 执行人：AgentCodex
- 日期：2026-07-07
- 范围：S1/S2/S3 accepted 后的真实 `dayu-cli prompt` 路径自动验证
- 工作目录：`workspace/tmp/wu-cli-smoke-context-slot-aggregate/`
- 约束：只做验证和 artifact，不修改生产代码，不 commit、不 push、不创建 issue/PR

## 动机核对

S1/S2/S3 的核心 contract 已从静态测试推进到真实 CLI 路径：`prompt` scene 需要按 manifest/context slot 注入当前分析对象；`base_user` 不应继续进入 LLM context slot；prompt scene 应过滤掉 download/preprocess/upload 长事务工具；`get_current_time` 在 prompt 场景仍应可用。真实 CLI smoke 可以验证 Service/CLI/Host/Engine 串联后的实际可见行为，动机成立。

## 命令结果

### 1. prompt with ticker V

命令：

```bash
source .venv/bin/activate && dayu-cli --log-level debug --log-file workspace/tmp/wu-cli-smoke-context-slot-aggregate/prompt-v.log prompt --base workspace/tmp/wu-cli-smoke-context-slot-aggregate/prompt-v --ticker V "现在是什么时间，并说明当前分析对象。"
```

- Exit code：0
- Debug log：`workspace/tmp/wu-cli-smoke-context-slot-aggregate/prompt-v.log`
- Workspace：`workspace/tmp/wu-cli-smoke-context-slot-aggregate/prompt-v/`
- Provider 证据：debug log 记录 `provider=mimo model=mimo-v2.5-pro`，HTTP `status=200`。
- stdout/stderr 摘要：
  - run 进入 `in_progress`。
  - 模型推理明确表示需要调用 `get_current_time`，并表示系统提示中当前分析对象是 `V（Visa Inc.）`。
  - CLI 展示工具调用 `get_current_time` 完成。
  - 最终回答包含：`当前时间：2026年7月7日 17:20:36（北京时间，星期二）。` 和 `当前分析对象：V（Visa Inc.）`。
- Debug/workspace 摘要：
  - `prompt-v.log` 109 行，约 30K。
  - engine run `tool_schema_count=12`。
  - event log 中有 2 条 `get_current_time` 相关 `TOOL_CALL_REQUESTED` 记录（engine ingest 与 tool runtime 接受路径）。
  - Host terminal payload 保存最终内容：当前时间与 `V（Visa Inc.）`。
  - `event_log` 与 `host_sqlite_payloads` 对 `base_user`、`未指定具体公司`、`start_fins_download`、`start_fins_preprocess`、`start_fins_upload` 的匹配数均为 0。

判断：符合预期。真实 CLI/provider 路径成功；ticker V 被解析为 LLM 可消费的当前分析对象；`base_user` 未出现在 debug/workspace 文本 payload；prompt scene 没有暴露长事务工具名；`get_current_time` 可见且被调用。

### 2. prompt without ticker

命令：

```bash
source .venv/bin/activate && dayu-cli --log-level debug --log-file workspace/tmp/wu-cli-smoke-context-slot-aggregate/prompt-no-ticker.log prompt --base workspace/tmp/wu-cli-smoke-context-slot-aggregate/prompt-no-ticker "总结你能做什么。"
```

- Exit code：0
- Debug log：`workspace/tmp/wu-cli-smoke-context-slot-aggregate/prompt-no-ticker.log`
- Workspace：`workspace/tmp/wu-cli-smoke-context-slot-aggregate/prompt-no-ticker/`
- Provider 证据：debug log 记录 `provider=mimo model=mimo-v2.5-pro`，HTTP `status=200`。
- stdout/stderr 摘要：
  - run 进入 `in_progress`。
  - 模型推理认为用户只要求总结能力，不需要调用工具。
  - 最终回答说明其作为买方分析师可访问/解析公司文档、提取结构化财务数据并结合公开网络信息支持投资决策。
  - 输出未出现 `未指定具体公司`。
- Debug/workspace 摘要：
  - `prompt-no-ticker.log` 70 行，约 17K。
  - engine run `tool_schema_count=12`。
  - event log 中 `TOOL_CALL_REQUESTED` 数量为 0。
  - Host terminal payload 保存的最终内容不包含 `未指定具体公司`。
  - `event_log` 与 `host_sqlite_payloads` 对 `base_user`、`未指定具体公司`、`start_fins_download`、`start_fins_preprocess`、`start_fins_upload` 的匹配数均为 0。

判断：符合预期。no-ticker prompt 没有向用户暴露“未指定具体公司”；没有工具调用；debug/workspace 文本 payload 未出现 `base_user` 或长事务工具名。

## 静态 sanity

命令：

```bash
git status --short
```

- 运行于写入本 artifact 前，输出为空。

命令：

```bash
git diff --check
```

- Exit code：0，无输出。

命令：

```bash
/usr/bin/grep -rn "BASE_USER\|base_user" dayu/config/prompts dayu/cli tests utils || true
```

- Exit code：0。
- 仅命中测试 pyc 缓存：
  - `tests/cli/__pycache__/test_interactive_command.cpython-311.pyc`
  - `tests/cli/__pycache__/test_prompt_command.cpython-311.pyc`
  - `tests/service/__pycache__/test_entrypoint_runtime.cpython-311.pyc`
  - `tests/service/__pycache__/test_host_assembly.cpython-311.pyc`
- 追加源码文本核验：

```bash
/usr/bin/grep -rn --exclude='*.pyc' "BASE_USER\|base_user" dayu/config/prompts dayu/cli tests utils || true
```

- 无输出，源码文本范围无残留。

## 证据边界与剩余风险

- Debug log 与 Host sqlite runner-call manifest 保存了 message digest、size、role sequence 与 terminal payload，但没有保存完整 system prompt 正文；因此“LLM-facing prompt 完整正文包含当前分析对象”的直接文本证据来自模型推理输出与最终回答，而不是完整 prompt dump。
- 本次真实 provider 可用，不属于 mock/不可用环境；但只覆盖 `prompt` 场景的两条代表路径，没有覆盖 interactive/wechat 或真实 FMP 网络烟测。
- `get_current_time` 在 prompt with ticker 路径被实际调用；no-ticker 路径中模型未调用该工具，符合用户问题不需要时间的行为。

## 结论

aggregate smoke 未发现 blocker。真实 `dayu-cli prompt` 路径与已接受设计一致：ticker 注入可被模型消费，no-ticker 不暴露“未指定具体公司”，`base_user` 源码文本无残留，prompt 场景未暴露 download/preprocess/upload 长事务工具名，`get_current_time` 在需要时可见并可调用。
