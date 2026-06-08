# WU-TOOLS-01-F01 Plan Review Controller Adjudication

## Metadata

- Gate: plan review controller adjudication.
- Work unit: `WU-TOOLS-01-F01`.
- Plan artifact: `docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md`.
- Review artifacts:
  - `docs/reviews/wu-tools-01-f01-plan-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-plan-review-ds.md`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`.
- Control source: `docs/host/issues-implementation-control.md`.

## Overall Decision

Plan direction is accepted, but the plan must enter fix gate before implementation.

The core goal remains unchanged: build one shared Fins service/runtime business foundation for read, download and preprocess/process. Tool providers, Service assembly and future CLI are adapters only; they must not duplicate download/process business logic.

The accepted fix is a plan clarification, not a scope expansion. Host and Engine awaiting contracts remain unchanged.

## Findings Adjudication

| Finding | Source | Decision | Controller reasoning | Required plan fix |
|---|---|---|---|---|
| Mimo F01 / DS F02: S3 download runtime scope | both | accepted | Current repo has no NEW source-specific SEC/CN/HK downloader implementation. F01 must not rebuild broad real-network downloader parity as an incidental side effect. The user-confirmed target is shared service/runtime, so S3 should define the adapter protocol and deterministic no-network representative path; real SEC/CN/HK adapter breadth must be deferred unless the user explicitly expands scope. | Rewrite S3 completion signal and non-goals: S3 implements typed download runtime, adapter protocol, fake/no-network adapter test path, storage write path, and explicit unsupported-source failure. No real SEC/CN/HK network adapter implementation in F01. |
| DS F01: Provider/runtime sharing semantics unclear | DS | accepted | Shared runtime means shared Fins business code and shared workspace-scoped durable state, not necessarily one Python object singleton. A module singleton in `dayu.fins` would be a hidden lifecycle owner and conflicts with explicit composition. Separate provider-created runtime instances are acceptable only if they use the same workspace-derived job store path and the job store has cross-instance file safety. | Clarify that `DefaultFinsRuntime.create(workspace_root=...)` may return separate instances, but all instances for the same workspace must use the same workspace-derived Fins job store path and safe atomic/locked writes. Do not introduce a module-level singleton. |
| DS F03: S5 provider detection mechanism missing | DS | accepted | Service cannot depend on opaque diagnostic strings. The least invasive path is a Service-owned mapping from explicit provider ids/config ids already visible in assembly, without changing `ToolsDiscoveryProviderOutput`. Avoid new generic runtime/tool discovery contract. | Add S5 decision: Service assembly detects Fins awaiting providers from explicit configured provider ids/import paths known in `tool_discovery.json` / binding specs, validates matching `workspace_root`, and builds the Fins wait adapter registry. No `ToolsDiscoveryProviderOutput` shape change. |
| DS F04 / Mimo F03: job store path underspecified | DS/Mimo | accepted | Path choice affects provider instance sharing and reviewability. It must be deterministic and workspace-scoped. | Add S1 invariant: Fins job store lives under a workspace-derived runtime path such as `<workspace_root>/.dayu/fins_ingestion/jobs` or an equivalent explicit Fins runtime directory, stores only job governance records, and uses atomic/locked writes. |
| DS F05 / Mimo F05: `include_ingestion_tools` removal semantics | DS/Mimo | accepted | Transitional fail-closed config is not target architecture. Keeping a compatibility no-op would preserve an old mixed provider mental model. | Add S4/S6 decision: remove read-provider ingestion parsing and tests after split providers exist; `include_ingestion_tools` is not a supported target config. Workspace overlays must enable download/preprocess through independent providers. |
| Mimo F02: S5 wiring location specificity | Mimo | accepted as non-blocking evidence | The plan is specific enough on file ownership, but DS F03 clarifies the detection mechanism needed before implementation. | Covered by DS F03 fix. |
| Mimo F04: processor boundary | Mimo | accepted as already sufficient | Existing processor registry reuse is adequate for plan gate. | No additional fix required beyond preserving S2 storage/processor boundaries. |
| Mimo F06: LLM-facing schema self-containment | Mimo | accepted as already sufficient | The plan correctly forbids exposing Host internals, digest, cursor, raw job paths or tool call ids in LLM-facing schema. | No additional fix required. |

## Residual Risk Classification

| Risk | Classification | Owner / Destination |
|---|---|---|
| `WU-TOOLS-01-S4-R1` | fixed in current slices after plan fix and implementation | `WU-TOOLS-01-F01` |
| Real SEC/CN/HK network downloader breadth | deferred-with-owner | Later Fins source-adapter work unit or explicit user-approved F01 scope expansion |
| Upload ingestion | assigned to later work unit | `WU-TOOLS-01-F09` |
| SEC/Fins CI pipeline | assigned to later work unit | `WU-TOOLS-01-F04/F05` |
| CN/HK Docling CI pipeline | assigned to later work unit | `WU-TOOLS-01-F06/F07` |
| Future CLI download/process wrapper | assigned to later work unit | Future CLI/package work unit unless user explicitly expands F01 |
| `include_ingestion_tools` transition | fixed in current slices | `WU-TOOLS-01-F01` S4/S6 |
| Fins wait adapter assembly | fixed in current slices | `WU-TOOLS-01-F01` S5 |

## Next Gate

Enter plan fix gate. The fix agent must update only `docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md` according to accepted findings above, then report the modified sections and remaining residual risks.
