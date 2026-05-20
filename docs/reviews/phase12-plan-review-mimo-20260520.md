# Phase 12 Plan Review — AgentMiMo

- Date: 2026-05-20
- Plan artifact: `docs/host/phase12-runtime-assembly-plan.md`
- Design truth: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`

## Verdict: BLOCKED

Blocking findings count: 3

---

## Blocking Findings

### B1: Source ref contract type location migration path not resolved

Severity: HIGH

Evidence:
- `ToolBundleSourceKind` / `ToolBundleSourceRef` currently live in `dayu/host/tooling.py` (line 27, 47) and are exported from `dayu/host/__init__.py` (line 92-98, 170-171).
- Design doc §18.1 states: "`ToolBundleSourceKind` 与 `ToolBundleSourceRef` 是跨 Host、runtime assembly、diagnostic、audit 与后续 attempt snapshot refs 的公共契约，应位于 `dayu.contracts`。"
- Plan Slice 1 says: "必要时新增 `dayu/contracts/runtime_assembly.py` 承载层中立 source ref / provider report 契约" — acknowledges the need but doesn't resolve the migration.
- Plan stop condition says: "如果 source ref 契约必须改 Host public API 才能闭环，停止并回设计讨论" — but the plan already acknowledges this may be needed ("必要时").
- `dayu.runtime` cannot import `dayu.host` (architecture hard constraint).

Why it violates design/control goals:
`dayu.runtime` needs `ToolBundleSourceRef` to produce source refs from `ToolsDiscovery`. The type currently lives in `dayu.host`, which `dayu.runtime` cannot import. Without resolving the type location, ToolsDiscovery cannot produce `ToolBundleSourceRef` objects that `HostToolingOptions` expects. The plan's stop condition is self-contradictory: it acknowledges the need for a new contracts file but also says to stop if Host public API must change.

Required fix:
The plan must explicitly decide one of:
- (a) Create `ToolBundleSourceKind` / `ToolBundleSourceRef` in `dayu.contracts.runtime_assembly` as the canonical definition; update `dayu.host.tooling` to import from `dayu.contracts`; keep `dayu.host.__init__` re-exporting from the new location. This changes the import source but preserves the public surface shape. The re-export is justified by the type location migration, not backward compatibility with an old API.
- (b) Explicitly decide these types stay in `dayu.host` and create a parallel set in `dayu.contracts` for runtime use — but this creates type duplication and the plan must explain how `HostToolingOptions` accepts the `dayu.contracts` variant.
- (c) Move the canonical definition to `dayu.contracts` and stop — if the plan decides this IS a Host public API change that requires a design gate.

The plan must pick one, explain why it doesn't violate the "禁止兼容性 re-export" constraint, and remove the self-contradictory stop condition.

### B2: ConfigLoader execution_profiles.json schema under-specified

Severity: MEDIUM

Evidence:
- Plan §3 Slice 3 describes `execution_profiles.json` fields at a high level: "默认 profile、ordinary model id / runner options / agent policy、compactor model id / runner options / artifact root、context budget、memory projection、truncation 配置，以及 scene hints 到 typed execution inputs 的映射边界。"
- Design doc §3 (line 85) describes the mapping: "scene 的 `model.default_name`、temperature profile 与 `runtime.agent` / `runtime.runner` hints 只覆盖 execution profile 中的对应 typed fields，最终由 Service 产出完整 `RunnerSpec`、`RunnerCallOptions` 与 `AgentPolicy`。"
- The plan does not include a concrete JSON schema sketch or typed config view dataclass shape for this file.
- Slice 3 test says "四个新配置文件可加载并产出 typed config view" but the view shape is unspecified.

Why it violates design/control goals:
The control doc requires "可独立验证的行为闭环" for each slice. Without a concrete schema for `execution_profiles.json`, implementation agents cannot produce consistent typed config views, and tests cannot verify that the view correctly maps to `RunnerSpec` / `RunnerCallOptions` / `AgentPolicy`. The scene hints mapping boundary is the most complex part and needs explicit schema definition.

Required fix:
The plan must include at minimum:
- A concrete JSON schema sketch for `execution_profiles.json` showing the scene hints mapping structure.
- The typed config view dataclass shape that ConfigLoader outputs for this file.
- How `model.default_name`, temperature profile, `runtime.agent`, and `runtime.runner` hints map to execution profile fields.

### B3: ScenePrepare context_slots typing and rendering mechanism unclear

Severity: MEDIUM

Evidence:
- Plan §3 Slice 4 says: "manifest 只声明 slot 名称，不携带值" and "Service 调用 `ScenePrepare` 时传入 typed context slot values" and "ScenePrepare 校验 required slots 并渲染 / 拼接 prompt fragments".
- Plan §6 says: "context_slots 只声明 Service 必须提供的 typed context 名称；Service 调用时传入 typed context slot values；ScenePrepare 校验 required slots 并渲染 / 拼接 prompt fragments。"
- Test says: "required context slot 缺失失败；typed slot value 被渲染到对应 fragment。"
- The plan does not specify: (a) what "typed" means — are slots string-typed, or do they have a type system? (b) how `ScenePrepare` validates that a slot value matches the expected type, (c) the rendering mechanism (template substitution? function call?).

Why it violates design/control goals:
Without a concrete typing and rendering mechanism, implementation agents will make inconsistent assumptions, leading to non-verifiable slices. The `context_slots` mechanism is the primary way Service provides runtime context to ScenePrepare, and its contract must be explicit.

Required fix:
The plan must specify at minimum:
- Slot declaration schema in manifest (name + type hint, or just name?).
- The `ScenePrepare` API signature for receiving slot values (dict[str, str]? dict[str, Any]? typed dataclass?).
- The rendering mechanism (e.g., `{{slot_name}}` template substitution in fragment content, or Python string formatting).

---

## Non-Blocking Findings

### N1: New config file JSON schemas not included in plan

Owner: implementation agent

The plan describes config file contents at a high level but doesn't include concrete JSON schema sketches for `models.json`, `host_runtime.json`, or `tool_discovery.json`. This is acceptable for a plan-level document but will need to be resolved during implementation. The `tool_discovery.json` schema is relatively straightforward (provider id, import path, source kind, enabled, allow_empty). The `models.json` schema is also well-described in the design doc. The `host_runtime.json` schema is the most deployment-specific and may benefit from a sketch.

Suggested handling: Implementation agent should produce concrete JSON schema sketches before writing config loading code. Consider adding schema sketches to the plan during fix pass.

### N2: Slice 5 migration source path hardcoded

Owner: plan author

The plan hardcodes `/Users/leo/workspace/dayu-agent/dayu/config/prompts/manifests/*.json` as the migration source. This is acceptable for a one-time migration but should be documented as a known limitation. The migration is a one-time operation, not a runtime dependency.

Suggested handling: Document in the plan that this is a one-time migration from a specific local path. No code change needed.

### N3: `@tool` decorator provider output contract not detailed

Owner: implementation agent

The plan says "ToolsDiscovery provider 输出应使用该契约或直接返回等价 `ToolDefinition`". The `@tool` decorator exists in `dayu.contracts.tool_declaration` and returns `ToolDefinition`. The plan doesn't specify whether providers should return `ToolDefinition` objects directly or use some other mechanism. This is a minor gap — providers returning `ToolDefinition` objects is the natural contract.

Suggested handling: Implementation agent should document that providers return `tuple[ToolDefinition, ...]` or equivalent. No plan change needed.

### N4: Fragment path escape prevention mechanism not specified

Owner: implementation agent

The plan says "fragment path 从 prompt asset root 解析，不允许逃逸 asset root" but doesn't specify the mechanism (e.g., `pathlib.Path.resolve()` check, `os.path.commonpath()` check). This is a security concern that should be addressed during implementation.

Suggested handling: Implementation agent should use `pathlib.Path.resolve()` and verify the resolved path is within the asset root. No plan change needed.

### N5: `content_digest` algorithm not specified

Owner: implementation agent

The plan says digest covers "tool name、LLM-facing schema、truncate spec、tags、display metadata" and "manifest、直接引用 fragment 内容与 assembly 输入" but doesn't specify the algorithm (e.g., SHA-256 of canonical JSON, stable serialization). This is acceptable for a plan but will need to be resolved during implementation.

Suggested handling: Implementation agent should use a deterministic serialization (e.g., `json.dumps(sort_keys=True)`) and SHA-256. No plan change needed.

---

## What I Checked

1. ✅ **ToolsDiscovery remains dayu.runtime**: Plan correctly places ToolsDiscovery in `dayu.runtime`. Explicit provider callable or entry point only, no package scanning. No Host/Engine/Service/UI/Fins imports required by the plan itself (source ref type location is the blocking issue B1). Digest semantics are implementable.

2. ✅ **ConfigLoader schema coverage**: Plan covers all four config files. Overlay whole-record replacement and single extends are clearly specified. Old `dayu/config/llm_models.json` and `dayu/config/run.json` deletion has no compatibility path. Schema under-specification is B2.

3. ✅ **ScenePrepare manifest schema**: All required fields listed. Single extends with clear semantics. Prompt fragment loading from asset root. `system_messages` output. Source refs/digest computed at assembly time. `tool_selection` `all`/`none`/`select` modes are sufficient and not workflow semantics. Context slots typing is B3.

4. ✅ **No Host public API / Engine / Fins / ToolRuntime / Service / Skill changes**: Plan explicitly states non-goals for all of these. The only potential Host public surface change is the source ref type location (B1), which the plan's stop condition acknowledges but doesn't resolve.

5. ✅ **Per-run override fields**: Plan correctly uses only existing `SubmitFollowupRequest` fields (`system_prompt`, `tool_names`, `runner_spec`, `runner_options`, `agent_policy`). No new fields proposed.

6. ✅ **Slice write scopes**: Each slice has clear write scope, test list, README triggers, acceptance criteria, and stop conditions. Slice sequencing is logical: ToolsDiscovery → source refs/digest → ConfigLoader → ScenePrepare → migration → import boundary tests.

7. ✅ **Architecture boundaries**: Plan maintains `dayu.runtime` as layer-neutral. Three components are independent (ConfigLoader doesn't explain scene manifest, ScenePrepare doesn't do tool discovery, ToolsDiscovery doesn't read config models). Service/composition root is the sole mapping agent.

8. ✅ **Legacy config deletion**: Plan explicitly deletes `dayu/config/llm_models.json` and `dayu/config/run.json` with no compatibility path. This aligns with the "schema 变更" constraint.

---

## Final Blocking Findings Count

**3** (B1, B2, B3)
