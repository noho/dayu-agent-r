# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B S3 Implementation — AgentCodex

## Gate result

- Gate：S3 — JSON Schema Bounds And Typed Enum Equality
- Status：`implementation-complete`
- Accepted baseline：R3-B plan `d1cdfca4`；S1 `791ed144`；S2 `50ed754e`
- Scope：仅修改 S3 获准的 2 个 production owner、2 个 owner test 文件和 3 个获准文档；Doc/Web/Fins 测试只读运行
- Stop：本 artifact 完成后停止；未 commit、未进入 aggregate review、未请求 code review

## First-principles / owner evidence

S3 动机经当前基线直接复现，成立：

- `ToolParametersSchema` 构造可接受四种 count bound 的 `-1`；非法 schema 可能延迟到工具调用时才被伪装成 LLM 参数错误。
- `validate_and_project_arguments()` 使用 Python membership；`boolean true + enum [1]` 被错误接受为 `ValidatedToolArguments`。

唯一 owner 保持不变：

- `dayu.contracts.tool_schema.ToolParametersSchema` 拥有 schema 声明期 count-bound 合法性；
- `dayu.runtime.tool_call_projection` 拥有当前 `ToolCallable` 的实例投影与 enum JSON equality；
- runtime bound check 只作为 frozen dataclass 内部仍引用外部 mutable mapping 时的防御，不把 schema 声明错误改写为业务工具或 LLM 的责任。

本 slice 没有引入完整 JSON Schema draft validator、第三方依赖或通用 schema engine。

## Production changes

### `dayu/contracts/tool_schema.py`

- `ToolParametersSchema.__post_init__()` 在声明边界递归检查 property schema 与 array `items` schema。
- `minLength`、`maxLength`、`minItems`、`maxItems` 必须是非 bool `int` 且 `>= 0`。
- bool、float、string及其它非整数值抛 `TypeError`；负整数抛 `ValueError`；`0` 合法。
- helper 只处理当前 finding 的 count bounds，不扩大为完整 JSON Schema validator。

### `dayu/runtime/tool_call_projection.py`

- runtime 在字段投影前递归检查 property/items count bounds；构造后外部 mutable mapping 把任一 bound 篡改为负数时，返回 schema-bound failure，不接受参数，也不把它报告成普通 range failure。
- 新增私有递归 JSON equality helper：
  - null 只等于 null；string/boolean 按同一 JSON 类型和值比较；
  - boolean 与 number 永不相等；
  - 非 bool 的有限 int/float 都是 JSON number，按数学值比较；
  - array 按长度与位置递归；object 按相同 key 集合与成员递归；
  - 非有限 float 不参与相等判断。
- `_validate_enum()` 使用该 helper 的 `any(...)`，删除 Python `in` / `not in` equality。
- schema default 与显式 argument 仍统一进入 `_project_field()`，没有第二套 enum path。

## Test changes

### Owner contract tests

- `tests/contracts/test_tool_schema.py`：覆盖四个 bounds 的 bool/float/string `TypeError`、负数 `ValueError`、`0` positive，以及 array items string bounds 的同类 construction matrix。
- `tests/runtime/test_tool_call_projection.py`：覆盖：
  - `True/False` 与 int/float enum 永不相等；
  - `1` 与 `1.0` 双向等价；
  - nested array/object 的 number equivalence 与 boolean/number separation；
  - default 与显式参数产生同一 typed enum failure；
  - 四种 field count bounds 被 mutable mapping 改为 `-1` 后 runtime fail closed；
  - 空 array 也不能绕过被篡改的 `items.minLength` defense。

### Read-only consumer validation

以下测试只作为共享声明 smoke 运行，没有修改对应测试或业务生产 schema：

- `tests/tools/test_doc_tools_provider.py`
- `tests/tools/web/test_web_tools_provider.py`
- `tests/fins/test_fins_ingestion_tools.py`

现有 Doc/Web/Fins tool schema 全部通过新 construction contract，未触发跨 owner stop condition。

## Validation

最终验证均在 `source .venv/bin/activate` 后执行：

- S3 plan focused matrix（5 files）：`225 passed, 1 skipped, 3 warnings`
  - skip 与 warnings 来自既有环境/第三方 Edgar deprecation，不是本 diff 失败；
- owner tests + coverage：`76 passed`
  - `dayu/contracts/tool_schema.py`：`91%`
  - `dayu/runtime/tool_call_projection.py`：`90%`
  - 合计：`91%`
- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`
- `git diff --check`：pass，无输出

## Source scans

- `rg -n 'value not in enum_value|value in enum_value' dayu/runtime/tool_call_projection.py`：无结果；不存在 Python enum membership comparison。
- `rg -n '"(minLength|maxLength|minItems|maxItems)"\s*:\s*-' dayu tests`：无结果；negative matrix 通过参数化变量构造，不留下 production negative literal。
- 同一 negative-bound scan 限定 `dayu`：无结果。

## README / design sync

### `docs/engine/design.md`

- 同步 AgentMessage role / AgentRunRequest union construction contract；
- 同步 EngineEvent discriminator/data owner validation；
- 同步 RunnerDone typed commit 与 first-accepted failure candidate；
- 同步 tool-call identity、strict finish/tool presence、non-stream string-only arguments；
- 同步 ToolParametersSchema count bounds 与 runtime typed enum equality；
- 删除 cancellation section 中重复的 final-answer commit bullet。

### `dayu/engine/README.md`

遵守其 Agent 更新约束，只记录当前稳定开发契约与关键机制：补充 message/event construction、Runner protocol normalization、RunnerDone commit、first failure candidate 和共享 ToolSchema count/enum 边界；未写测试清单或 WU 过程状态。

### `tests/README.md`

遵守其“仅描述现有测试事实”边界，更新 contracts/runtime/Engine/OpenAI 测试覆盖描述：non-negative bounds、typed enum recursion、mutable defense、EngineEvent/message contract、RunnerDone cancellation ordering、identity-conflict matrix、strict terminal parity 与 string-only non-stream arguments。

Host、根目录、`dayu/README.md`、Fins/Config README 未修改：分层、Host durable/ingest、安装/CLI/用户工作流与对应业务 production owner均未变化。

## Unchanged scope

- 未修改 Doc/Web/Fins production schema、工具参数或业务实现。
- 未修改 Host、Engine Agent/Runner、Service、CLI、配置、durable schema、error envelope 或工具结果公共形状。
- 未修改三个 read-only consumer test 文件。
- 未实现 schema migration、旧 schema compatibility、provider discovery、完整 JSON Schema draft 或序列化字符串 equality。
- 未 commit、未 push、未进入 aggregate review、未请求 code review。

## Residual risks

无新增未分类 residual。`ToolParametersSchema` 仍是有意收窄的 schema contract，不承诺完整 JSON Schema draft；未支持关键字继续由现有 runtime fail-closed 路径负责。该边界是当前设计事实，不是本 slice 遗留缺陷。
