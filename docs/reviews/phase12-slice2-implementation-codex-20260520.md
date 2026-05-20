# Phase 12 Slice 2 Implementation Artifact

## Gate

- 当前 gate：Phase 12 Slice 2 implementation
- 角色：AgentCodex implementation worker
- 已接受计划：`docs/host/phase12-runtime-assembly-plan.md`
- Slice：Source refs / digest and reserved framework tool validation
- 非目标：未修改 Host durable state、Host command path、ToolRuntime accept barrier、Engine、Service、UI、Fins、ConfigLoader、ScenePrepare、prompt assets、config schema 或业务工具；未提交、未 push、未开 PR。

## Changed Files

- `dayu/runtime/tools_discovery.py`
- `tests/runtime/test_tools_discovery.py`
- `tests/runtime/test_tools_discovery_digest.py`
- `docs/reviews/phase12-slice2-implementation-codex-20260520.md`

## Design Decisions

- 在 `dayu.runtime.tools_discovery` 内新增私有 canonical JSON / digest helper，仅使用 stdlib `json` 与 `hashlib`，不 import Host durable codec。
- `content_digest` 采用 `sha256:<hex>`，digest 输入只包含 provider 按声明顺序返回的工具声明内容：工具名、LLM-facing schema、truncate spec、tags、display metadata。
- digest 明确不包含 callable 引用、provider callable identity、模块路径对象身份、权限、lease、fencing、Host truth 或 owner 信息；source refs / digest 仅用于解释、诊断、trace、audit 与后续 snapshot refs。
- provider 返回的每个 `ToolBundleSourceRef` 都会被规范化为新的 source ref：保留 `source_kind`、`source_id`、`version_ref`，并用 discovery 计算出的 provider digest 填充或替换 `content_digest`。即使 provider 预填 digest，也以 runtime discovery 的声明投影为真源。
- 保留名校验放在 runtime assembly 阶段，业务工具名等于 `fetch_more` 时抛出 `ToolsDiscoveryError`。实现未 import Host `FrameworkToolName`，也未改变 ToolRuntime framework tool 注入或 accept barrier。

## Tests

- 新增 `tests/runtime/test_tools_discovery_digest.py`，覆盖：
  - 同一 provider 声明顺序下 digest 稳定。
  - callable 引用变化但声明内容不变时 digest 不变。
  - schema、truncate spec、tags、display metadata 改变时 digest 改变。
  - `EXPLICIT_PROVIDER`、`CONFIG_BINDING`、`PACKAGE_ENTRYPOINT` source refs 保留 kind/id/version，并替换为计算 digest。
  - 业务工具名 `fetch_more` 被 `ToolsDiscovery` 拒绝。
- 更新 `tests/runtime/test_tools_discovery.py` 中 source ref 断言，适配 discovery 现在会填充 `content_digest` 的行为。

## Validation

```text
source .venv/bin/activate && pytest tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q
...................................                                      [100%]
35 passed in 0.81s
```

```text
source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q
......                                                                   [100%]
6 passed in 0.62s
```

```text
source .venv/bin/activate && python -m pyright dayu/contracts dayu/runtime dayu/host tests/runtime tests/host
0 errors, 0 warnings, 0 informations
```

```text
source .venv/bin/activate && git diff --check
```

结果：通过，无输出。

## README Sync Decision

- 本 slice 只为 `ToolsDiscovery` source refs 增加 digest 规范化和 reserved name 校验；`dayu/README.md` 现有 Runtime / contracts 边界说明仍然准确，没有残留旧入口、旧术语或错误架构表述。
- 未更新 README，避免把实现细节写入总览文档。

## Residual Risks

- digest 是 provider 级声明摘要，同一 provider 的多个 source refs 共享同一 digest；如果后续需要 per-tool source refs，需要在后续 slice 或 phase 明确契约。
- canonical JSON helper 当前服务于 runtime discovery 私有投影；如后续 ScenePrepare 或 ConfigLoader 需要共享同类摘要，应在 `dayu.runtime` 内抽取层中立 helper，不能复用 Host durable codec。
- 本 slice 未改变 Host 对 `HostToolingOptions.source_refs` 的消费语义；source refs 仍然只是 provenance，不是 Host truth。

## Completion Status

Slice 2 assigned implementation completed. 未触发停止条件：实现不需要 Host 保存 provider callable、discovery adapter、配置路径本体，也不需要 ToolRuntime 行为变化。

## Fix Addendum: P12-S2-F1

- 日期：2026-05-21
- 当前 gate：Phase 12 Slice 2 fix
- 角色：AgentCodex implementation/fix worker
- 来源裁决：`docs/reviews/phase12-slice2-code-review-controller-adjudication-20260521.md`
- Accepted finding：P12-S2-F1

### Changed Files

- `dayu/runtime/tools_discovery.py`
- `tests/runtime/test_tools_discovery_digest.py`
- `docs/reviews/phase12-slice2-implementation-codex-20260520.md`

### Fix Summary

- `_normalize_json_value` 在处理 `Mapping` 时新增运行时 key 类型校验；发现非 `str` key 立即抛出 `TypeError`，避免 `json.dumps` 在 canonical digest 序列化阶段把 malformed JSON object key 静默转成字符串。
- `tests/runtime/test_tools_discovery_digest.py` 新增 focused coverage：通过工具 schema declaration 注入带非字符串 key 的 malformed `properties` mapping，并断言 `ToolsDiscovery` 在 digest 生成路径上快速失败。
- 未处理 deferred notes：未新增 `SERVICE_COMPOSITION` 额外覆盖、未新增 empty digest golden、未新增专用 import-boundary assertion、未重设计 reserved framework tool。

### Validation

```text
source .venv/bin/activate && pytest tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q
....................................                                     [100%]
36 passed in 0.59s
```

```text
source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q
......                                                                   [100%]
6 passed in 0.58s
```

```text
source .venv/bin/activate && python -m pyright dayu/contracts dayu/runtime dayu/host tests/runtime tests/host
0 errors, 0 warnings, 0 informations
```

```text
source .venv/bin/activate && git diff --check
```

结果：通过，无输出。

### README Sync Decision

- 本 fix 只收紧 runtime digest canonicalization 的非法输入失败方式，并补充测试覆盖；不改变用户命令、配置入口、分层关系或稳定开发手册表述。
- 按 handoff allowed files 限制，未修改 README。

### Residual Risks

- 运行时仍只在 digest canonicalization 消费边界校验 malformed mapping key；未把 `ToolParametersSchema` 扩展成完整 JSON Schema runtime validator。该边界与当前 finding 一致，未扩大 scope。
