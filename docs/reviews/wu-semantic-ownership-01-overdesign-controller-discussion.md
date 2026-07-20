# WU-SEMANTIC-OWNERSHIP-01 Overdesign Controller Discussion

## Scope

- Review range: `b1a0631f397967e7530b676a90ef7467d83a1817^..HEAD`
- Final design truth set: `docs/host/design.md`, `docs/engine/design.md`,
  `docs/tool/design.md`, `docs/fins/design.md`, `docs/ui/design.md`
- Source reviews:
  - `docs/reviews/wu-semantic-ownership-01-overdesign-designtruth-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-overdesign-designtruth-review-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-overdesign-designtruth-review-codex.md`

## Discussion State

This artifact records controller/user discussion decisions. It does not itself fix code.

All nine merged topics have completed user adjudication. Implementation must continue inside the
existing `WU-SEMANTIC-OWNERSHIP-01` umbrella; it is not a new WU. Final disposition:

| Topic | Final disposition |
| --- | --- |
| 1 Doc input budgets | accepted code fix; remove unrequested 32 MiB / 10,000-entry failure/partial semantics; full TruncationManager connection remains Issue #177 |
| 2 Web policy | accepted mixed code/design fix; retain configured safety/capabilities under adjudicated defaults and remove current storage-state lifecycle implementation to Issue #178 |
| 3 Host LLM-safe arguments | accepted code fix; remove downstream normalized/blacklist repair and audit/fix LLM-facing sources |
| 4 OpaqueEvidenceRef | accepted code fix; opaque refs never become guessed business sources |
| 5 Wait poller | accepted code/config fix; explicit provider resolution mode and Host runtime policy, observation timeout retries rather than fabricating LOST; Issue #175 remains separate process-isolation owner |
| 6 Fins contracts | accepted code fix across the seven owner boundaries recorded below and in `docs/fins/design.md` |
| 7 Public entrypoints/init | accepted code fix; complete OLD-aligned `upload_filings_from`, remove unimplemented placeholder grammar, restore OLD-aligned init behavior under current architecture |
| 8 Engine 240 chars | accepted as-is; no code fix |
| 9 Tool security wording | design clarification only; keep current safety mechanisms and defer unified Host tool authorization framework |

The implementation controller must not reopen these decisions merely because older discussion text
below preserves the evidence trail. Only a direct contradiction in current code/design evidence may
be escalated to the user.

## Topic 1: Doc File Read And Directory Scan Limits

### User Decision

Accepted as a real defect.

The user explicitly rejected the product semantics:

- Single document source hard-fails above `32 MiB`.
- Directory scanning stops after `10,000` observed entries and returns partial results.
- These limits are not product requirements.

### Controller Interpretation

The fix should remove or sharply narrow user-visible input ceilings and partial directory-scan semantics. Output truncation remains legitimate, but input file size and directory size must not become unrequested product behavior.

### Fix Direction

- Remove `DocResourceBudget.max_source_bytes` as a public/user-visible hard failure for normal `read_file`, `search_files`, `get_file_sections`, and `read_file_section` paths unless a later design explicitly reintroduces it.
- Remove `max_directory_entries` as a user-visible directory completeness rule for `list_files` / `search_files`.
- Remove or rewrite LLM-facing references to `directory_entry_limit`, `source_limit`, `skipped_oversized_files`, and “use smaller file” guidance if those semantics disappear.
- Keep result-size controls such as `limit`, `max_chars`, returned match limits, and cooperative cancellation.
- Update tests so they assert owner-level behavior requested by product, not the rejected hard caps.

### Output-Limit Ownership Clarification

User decision: the Doc `max` / `limit` values in `dayu/config/tool_discovery.json` are `ToolTruncateSpec` configuration. They bound the first visible page of one tool result; they are not a total tool capability limit or an Agent / Run cumulative quota. `TruncationManager` owns truncation and run-local remainder storage, and the model retrieves the remainder through `fetch_more`.

The Doc producer must not pre-truncate or discard the remainder before ToolRuntime applies the effective spec. Parameter-schema `limit` / `maximum` values may validate the same contract but do not own a second truncation policy. The current Doc integration does not fully satisfy this boundary and is tracked by GitHub Issue [#177](https://github.com/noho/dayu-agent-r/issues/177); it is not part of the rejected `32 MiB` / `10,000 entries` input-budget behavior.

## Topic 2: Web Egress, Browser Capability, Resource Budget, Challenge, Diagnostics

Status: final user adjudication recorded; accepted implementation boundary written to
`docs/tool/design.md`.

### Discussion Record

The user noted that Web tool policy is configured from `dayu/config/tool_discovery.json`. The user suggested adding a dedicated tool design truth file, `docs/tool/design.md`, because current permanent design truth only covers Host and Engine.

### Plain-Language Breakdown For User Decision

#### 2.1 Default Private / Local Network Blocking

Current behavior: Web tools default to public internet only. URLs resolving to localhost, private IP ranges, link-local, metadata endpoints, and similar non-public addresses are rejected unless `allow_private_network_url=true`.

Plain meaning: This is a guardrail against an LLM-controlled web tool reaching the user's local machine, cloud metadata services, internal network, or dev services by accident.

Controller read: This is likely a valid tool-level policy, but it needs permanent design truth. It fits better in `docs/tool/design.md` than Host or Engine, unless the project wants Host to own all tool authority.

Likely decision options:

- Keep and document in `docs/tool/design.md`: recommended if Web tools are intended for public web access by default.
- Remove only if private/local access is a normal expected default, which seems risky and probably not intended.

User decision: keep this as a configurable Web tool policy, but default behavior should allow private/local network URLs. The config owner is `dayu/config/tool_discovery.json`; if the protection is enabled by config, Tool owns enforcement.

#### 2.2 Custom Port Blocking

Current behavior: public Web egress rejects non-default ports in some paths. A URL like `https://example.com:8443` or `http://example.com:8080` can be rejected even if it is otherwise public.

Plain meaning: The code treats custom ports as suspicious infrastructure instead of normal web URLs.

Controller read: This is more questionable than private-network blocking. Public sites and enterprise services often use custom ports. If there is no product requirement, this should probably be removed or moved behind an explicit stricter profile.

Likely decision options:

- Remove custom-port blocking while retaining private/local blocking.
- Keep only under a named strict egress profile documented in `docs/tool/design.md`.

User decision: treat custom-port blocking like private/local network blocking. It must be controlled by Web tool configuration, default allow, and documented in `docs/tool/design.md`.

#### 2.3 Mixed DNS / DNS Pinning / Numeric Peer Proof

Current behavior: the Web client resolves the hostname, approves numeric addresses, connects only to approved addresses, and verifies the connected peer. If DNS answers include disallowed addresses, the request can fail closed.

Plain meaning: This tries to prevent DNS rebinding or redirect tricks where a public hostname eventually connects to a private/internal IP.

Controller read: The peer-proof idea is defensible for LLM-driven web fetch, but the exact fail-closed behavior needs design. A mixed DNS answer may include both public and private records; failing the whole request is safer but may reject some real deployments.

Likely decision options:

- Keep peer proof and document it.
- Decide whether mixed DNS should fail all-or-nothing or connect only to approved public addresses.

Current user question: assess whether DNS pin / peer proof is necessary for a local Agent. Compare against ordinary `curl` / `wget` behavior and explain the security risk of not introducing it.

Controller explanation:

- Ordinary `curl` / `wget` primarily resolve a hostname, connect, and let TLS verify the certificate/hostname for HTTPS. They do not, by default, enforce a product policy such as “this LLM-driven web tool may never connect to localhost, private IP ranges, link-local metadata endpoints, or rebinding targets.”
- DNS pin / peer proof is not about replacing TLS. It closes the gap between “the URL looked public when policy checked it” and “the actual socket connected to a private/internal address.”
- For a local Agent, the risk is still real because the tool runs from the user's machine and can see local or corporate network surfaces that a normal public web service cannot see. Without this check, an attacker-controlled URL can try to reach `127.0.0.1`, LAN devices, cloud metadata IPs, local dev services, or intranet resources through DNS rebinding, redirects, or numeric-address tricks.
- Recommended design direction: if private-network blocking is enabled, keep an owner-level connection proof. The design still needs to decide whether mixed DNS answers should fail closed or whether the tool may filter to approved public addresses and connect only to those.

User decision: accept the controller recommendation. DNS pin / peer proof is Tool config controlled and default off, matching private-network and custom-port policies defaulting to allow/no extra safety enforcement.

#### 2.4 Proxy Ban / `trust_env=false`

Current behavior: Web fetch disables ambient environment proxy behavior and rejects configured proxies in the target-bound transport path.

Plain meaning: Even if the user's environment normally requires `HTTP_PROXY` / `HTTPS_PROXY`, this tool tries to bypass/ignore that proxy.

Controller read: This is a deployment policy, not just an implementation detail. In enterprise environments, proxy is often required. If we keep proxy disabled, design truth must say why. Otherwise Web tools should support an explicit proxy profile owned by tool configuration.

Likely decision options:

- Remove proxy ban and support explicit configured proxy later.
- Keep ambient proxy disabled but add a design-approved explicit proxy profile.
- Keep all proxy disabled only if product explicitly forbids proxy use.

User decision: proxy use should be controlled like the private/custom-port policies, but default should be **not banned**. The tool may emit a warning when proxy behavior is active.

#### 2.5 Browser Capability Coupled To Private-Network Permission

Current behavior: Playwright/browser fallback is not independently enabled for public web. In practice, enabling browser fallback is tied to `allow_private_network_url=true` in current paths.

Plain meaning: To use browser rendering for a public website that needs JavaScript, the operator may need to turn on private-network access too. That mixes two unrelated things: “may use browser” and “may access local/private network.”

Controller read: This is a strong design smell. Browser capability and network authority should be separate switches.

Likely decision options:

- Split into two concepts:
  - `browser_enabled` / browser availability.
  - `allow_private_network_url` / network authority.
- Keep public browser fallback available without granting private-network access.

User decision: `browser_enabled` is required. Browser access must be independent from private-network authority because many public pages need browser rendering.

#### 2.6 Web Resource Budget Complete Object

Current behavior: Web has a seven-field `resource_budget` object for wire bytes, decoded bytes, warmup body, browser DOM chars, browser text chars, diagnostic error chars, and diagnostic event count. If configured, it must be supplied as a complete object.

Plain meaning: One config blob controls several unrelated limits. To change one, the operator must restate all seven.

Controller read: Some limits are probably useful, but the complete-object schema is heavy and brittle. These fields also mix different owners: HTTP transfer, browser rendering, and diagnostics.

Likely decision options:

- Keep resource limits but document them in `docs/tool/design.md`.
- Split by owner, for example HTTP budget, browser budget, diagnostic budget.
- Allow partial override with defaults for omitted fields, unless fail-fast complete object is a deliberate design choice.

Current user question: explain why response-size and DOM-size limits are reasonable at all, not just whether the current seven-field complete-object schema is too heavy.

Controller explanation:

- Web input is untrusted remote content. A URL can return very large bodies, compressed responses that expand dramatically, pages that generate huge DOM/text output, or diagnostic traces that grow without bound.
- Response-size limits protect network, memory, disk, and downstream LLM-context budgets. They are operational safety limits for remote input, unlike the rejected Doc source-size limit that made local user documents unreadable as product behavior.
- DOM/text-size limits are especially relevant for browser fetch because a small HTML page can produce a very large rendered DOM or extracted text after JavaScript runs.
- The current overdesign concern is not “any web budget is bad.” The concern is that one mandatory seven-field complete object mixes HTTP transfer, browser rendering, and diagnostics. These should either be documented as a Tool-owned contract or split into owner-specific budgets with defaults and partial override semantics.

User decision: accept the controller recommendation. Web resource budgets are Tool config controlled, should default larger because financial filings can be large, and should not remain a brittle seven-field complete-object contract.

#### 2.7 Bot Challenge Detection

Current behavior: Web fetch classifies possible anti-bot/challenge pages into `none`, `suspected`, and `confirmed`, then decides whether to continue, try browser fallback, or fail blocked.

Plain meaning: The tool tries to recognize “this page is not the real content; it is a challenge page” instead of pretending the fetch succeeded.

Controller read: The goal is reasonable. The risk is making vendor heuristics and fallback policy into a stable public state machine too early. This can be kept as internal diagnostic behavior, or formalized in tool design if product wants stable challenge semantics.

Likely decision options:

- Keep as internal heuristic and reduce public/LLM-facing commitment.
- Or document the stable challenge decision contract in `docs/tool/design.md`.

User decision: challenge detection is required, not optional. Web CI exists partly to improve challenge behavior, so Cloudflare / Akamai style challenge recognition should be treated as a real Web tool capability, then documented at the tool design layer.

#### 2.8 Web Diagnostics V2 And Storage-State Lifecycle

Current behavior: diagnostics artifacts now have strict v2/revision 2 schema; storage-state output has owner naming, TTL, permissions, atomic publish, and cleanup rules.

Plain meaning: The diagnostic tool now has its own mini persistence and credential-file lifecycle policy.

Controller read: This is useful operationally, but it should not live only in a smoke/diagnostic implementation. If it handles browser login state, it is credential-bearing storage behavior and needs a design owner.

Likely decision options:

- Move durable diagnostic/storage-state rules into `docs/tool/design.md`.
- Or narrow diagnostics to ephemeral test artifacts and remove durable-looking compatibility/lifecycle commitments.

Current user question: explain Web diagnostics v2 and storage-state lifecycle in plain language before final decision.

Controller explanation:

- Web diagnostics v2 means the web diagnostic command writes a stable “fetch lab report” with a versioned shape. CI and humans can read the same fields to know what happened: request policy, redirects, challenge detection, browser fallback, errors, and evidence.
- The benefit is repeatability: tests do not depend on ad hoc logs or message text. The cost is that once a versioned schema exists, it becomes a contract and needs a design owner.
- Storage-state lifecycle means browser session state is treated like credential-bearing material. The implementation decides where it is stored, how it is named, file permissions, TTL/expiry, atomic writes, and cleanup.
- This is useful when browser fetch needs logged-in or challenge-cleared state, but it is not just smoke-test plumbing. If kept, it should be documented as Tool-owned credential/session state behavior in `docs/tool/design.md`; if not kept, diagnostics should be narrowed back to ephemeral test evidence.

User decision: accept Web diagnostics v2 as Tool-owned design. Storage-state lifecycle is a necessary future capability, but it must not be implemented in this WU. Remove already implemented storage-state lifecycle behavior now; GitHub Issue [#178](https://github.com/noho/dayu-agent-r/issues/178) tracks the future design and implementation.

## Final User Adjudication For Web

Current accepted direction:

1. Keep and document configurable private/local network blocking, default allow.
2. Keep and document configurable custom-port blocking, default allow.
3. Fix browser capability/private-network coupling by separating browser enablement from private-network authority.
4. Keep browser access as a required Web capability for modern pages.
5. Keep proxy behavior configurable, default not banned, with warning when proxy behavior is active.
6. Keep challenge detection as a required Web capability and document the stable tool-level contract.
7. Keep DNS pin / peer proof as configurable Tool policy, default off.
8. Keep Web resource budgets as Tool config with large defaults, preferably split by HTTP/browser/diagnostic owner instead of one seven-field complete object.
9. Keep Web diagnostics v2 as Tool-owned design.
10. Remove storage-state lifecycle behavior from this WU; GitHub Issue #178 tracks future design and implementation.

## Topic 3: Host LLM-Safe Argument Projection

### Finding Summary

Source finding: Codex F-01, confirmed by DS.

Current behavior: ordinary `TOOL_CALL_REQUESTED` atoms persist accepted arguments and require their digest to match the raw normalized argument digest. When no semantic query exists, accepted-result projection tries to decide whether arguments can be shown to the LLM by recursively scanning key names such as `api_key`, `token`, `secret`, `password`, and `path`.

### Plain-Language Breakdown For User Decision

The useful question is not “should secrets be hidden?” They should. The drift is “who knows what is safe to show the LLM?”

The projection layer only sees a JSON object after the tool call has already been accepted. It does not know whether `scope_token` is a business token, a pagination token, an auth token, or an opaque internal id. It also does not know whether `file_path` is the actual user question context or a local filesystem path that must never enter LLM memory.

So the current implementation guesses from field spelling:

- false positive: a legitimate business field containing `token` or ending in `path` hides the whole query;
- false negative: a secret named `credential`, `cookie`, `auth`, `session`, `bearer`, or another unlisted alias can still leak;
- information loss: one suspicious key drops the entire query, including harmless fields such as ticker, period, company, form type, or user-visible URL;
- owner split: awaiting tools already use a producer-side `llm_safe_replay_arguments` path, while ordinary tools rely on projection-side blacklist repair.

### Controller Interpretation

This is a real semantic ownership defect. The fix must not introduce a new normalized/safe-arguments semantic layer. The owner is the LLM-facing source contract itself:

- prompts, prompt fragments, tool schemas, and Host/Engine/Tool projections must follow the `AGENTS.md` LLM-facing text constraints;
- tool schema field names and descriptions must be business-readable and self-explaining at the source;
- LLM-returned tool arguments are validated as tool arguments, not reclassified by Host projection through field-name security guesses;
- Host projection may render only task-needed, self-explaining LLM-facing text and must not expose Host internal governance fields.

Projection should therefore remove downstream blacklist repair. It should consume source-owned LLM-facing semantics or render schema-owned accepted arguments directly under the LLM-facing text constraints.

### Candidate Fix Direction

- Do not add a new Host LLM-safe normalization layer.
- Remove existing LLM-facing normalized/safe-argument repair code that tries to make raw arguments safe after the fact. This does not mean deleting internal canonicalization or normalized argument digest logic used for idempotency, audit, payload integrity, and replay.
- Remove projection-layer key blacklist as the owner of safety decisions.
- Keep argument digest / canonicalization concerns internal to idempotency, audit, payload integrity, and replay; they are not LLM-facing safety semantics.
- Enforce LLM-facing safety at source: prompt assets, tool schemas, tool descriptions, parameter descriptions, and projection renderers must follow `AGENTS.md`.
- If a tool schema or prompt exposes Host/internal/security-sensitive wording, fix that schema/prompt at its owner instead of hiding it downstream.
- If a tool result needs request/query text for memory or evidence, render only business-readable, task-needed text; do not expose `tool_call_id`, EventLog ids, payload refs, digests, cursors, Host state, or other internal governance fields.
- Source audit is part of the fix scope, not optional follow-up: inspect prompt assets, tool schemas, parameter descriptions, tool descriptions, tests that simulate LLM prompts, and Host/Engine/Tool LLM-facing renderers touched by this WU for violations of the `AGENTS.md` LLM-facing text constraints.

### User Decision

Accepted with narrowed fix scope: no normalized Host LLM-safe argument projection. The fix must remove downstream normalized/blacklist repair and also check the source inputs. Host inputs, prompts, tool schemas, parameter descriptions, test prompts, and LLM-facing renderers must comply with the `AGENTS.md` LLM-facing text constraints.

### Design Writeback

- Host LLM-facing 参数投影裁决已写回 `docs/host/design.md`。
- Doc tools / Web tools 裁决已写回 `docs/tool/design.md`。

## Topic 4: OpaqueEvidenceRef Guessed As A Business Source

### Finding Summary

Source finding: Codex F-12, confirmed by DS.

`OpaqueEvidenceRef` is defined as a reference whose semantics Host does not interpret. The current accepted-result projection nevertheless maintains a small denylist of internal `ref_kind` values. Every other kind is assumed to be business-readable and rendered as `kind:id`. The resulting text enters the shared accepted-evidence LLM material as a business source.

For example, tests construct `OpaqueEvidenceRef(ref_kind="filing", ref_id="MSFT-10K")`. Because `filing` is not in the internal-kind denylist, Host renders `filing:MSFT-10K` and tests assert it as the available source. An unknown kind or typo such as `paylaod:abc` would pass through the same default branch.

### Reality Check

This is not evidence that the current production Fins path is already mislabelling a real filing. The ordinary ToolRuntime and wait-result producers currently create accepted evidence envelopes with empty `source_refs` and `locator_refs`, so their source projection is unavailable. The current defect is the unsupported default projection rule and the test contract that freezes it: any future producer, malformed value, or typo can become LLM-facing business-source text without an owner that vouches for its meaning.

### Ownership Decision

- `OpaqueEvidenceRef` owns only internal provenance identity. Its `ref_kind`, `ref_id`, and optional digest do not carry a Host-understood business fact.
- Host must not infer business source semantics from opaque refs through a denylist, allowlist, naming convention, or unknown-kind fallback.
- Opaque refs may remain in EventLog, audit, and internal provenance / diagnostic trace where exact internal identifiers are required.
- RunInput, Conversation Memory, Compact, and any other LLM-facing material must not expose opaque refs as business sources.
- Only a concrete Tool / Fins producer may directly provide business-readable, task-needed source semantics through an explicit contract. Without that producer-owned semantic value, the shared source projection is unavailable.
- There is no current production producer requiring a generic business-source contract. Do not introduce a speculative `BusinessSource` abstraction in this fix.

### Candidate Fix Direction

- Remove `_INTERNAL_SOURCE_REF_KINDS` and the unknown-kind `kind:id` rendering rule from accepted-result projection.
- Keep `OpaqueEvidenceRef` and its durable/internal provenance uses; do not delete the type merely because it cannot be shown to the LLM.
- When an accepted evidence envelope has only opaque source or locator refs, project the shared source-unavailable text.
- Remove tests that invent `filing:MSFT-10K` as an implicit Host business-source contract.
- Add owner-level fail-closed tests proving arbitrary, misspelled, and internal opaque refs do not enter RunInput, Conversation Memory, LLM-readable trace material, or Compact as business sources.
- If a later Tool / Fins requirement needs readable source identity, define it at that concrete producer boundary and then let Host consume it mechanically without semantic guessing.

### User Decision

Accepted: `OpaqueEvidenceRef` must not be guessed as a business source.

### Design Writeback

The ownership rule has been written to `docs/host/design.md`.

## Topic 5: Service Implicitly Enables The Wait Poller

### Finding Summary

Source finding: Codex F-02.

The product entrypoint discovers tools and prepares the selected scene. If that scene exposes any configured Fins download, preprocess, or upload awaiting tool, `with_entrypoint_wait_poller_policy(...)` replaces an absent `ServiceAssemblyOverrides.wait_poller_policy` with `WaitPollerRuntimePolicy()`. The ordinary composition path then passes this generated policy to `open_host`.

This is observable drift because `ServiceAssemblyOverrides` documents `wait_poller_policy=None` as “do not start the poller by default,” and Host design says the production poller starts after an explicit registry and policy are configured and is off by default. The product entrypoint silently changes that absence into an enabled default based only on scene tool selection.

### Plain-Language Behavior

Selecting a tool currently has two effects:

1. The LLM is allowed to call the Fins awaiting tool.
2. Service silently starts a Host background poller with a default runtime policy.

The first fact expresses model-visible capability. The second grants runtime behavior that observes durable waits and may submit terminal wait results. They are related, but they are not the same authority. Editing a scene manifest to expose one awaiting tool can therefore start a background runtime and adopt state-changing timeout behavior without changing product runtime configuration.

The generated default policy contains three values highlighted by the finding, but their effects differ:

- `adapter_call_timeout_seconds=30`: a single synchronous adapter observation that does not return within 30 seconds is converted to `ResolveWaitLostOutcome(wait_observation_timeout)`. The common resolver then terminalizes both the wait record and the Run as `LOST`. This is the state-changing value.
- `close_drain_timeout_seconds=5`: Host close waits at most five seconds for the poller and observation threads. Budget exhaustion leaves runtime diagnostics at `CLOSING` and revokes late publication; it does not by itself mark the business wait or Run `LOST`.
- `max_outstanding_adapter_calls=8`: at most eight observation calls may remain live. Capacity exhaustion releases the claimed wait with retry/backoff; it does not directly terminalize the wait.

### Reality Check

Automatic product-entrypoint enablement is not inherently wrong. An awaiting tool needs poll, callback, or manual resolution after it starts an external job. If the normal CLI/product path exposes awaiting tools but provides no callback/manual operator path, automatically starting a poller may be the correct usability default; deleting it blindly can restore the earlier behavior where a Run remains `WAITING` indefinitely.

The Host design already owns the bounded observation mechanism and currently states that an observation timeout becomes `lost(wait_observation_timeout)`. Therefore the finding is not accurately described as all wait semantics being absent from design. The unsupported or ambiguous parts are:

- product entrypoint enablement is inferred from scene selection despite the public override and design saying absent policy means default off;
- the exact `30 / 5 / 8` defaults are hard-coded in Host code and are not supplied by product runtime configuration;
- the product has not separately confirmed whether one timed-out status observation should permanently terminalize the external job's Run as `LOST`.

### Controller Recommendation

- Keep Host's typed wait-poller mechanism and keep scene selection as a necessary “poller may be needed” signal.
- Do not let scene selection be the sole authority. Add one explicit product/runtime configuration owner for wait-poller mode and policy. An `auto` mode may deliberately enable polling only when a selected scene exposes a supported awaiting tool and the matching registry exists.
- Put the effective timeout, close-drain, outstanding-cap, poll cadence, claim, and backoff values under that same configured policy instead of constructing an unreviewed default object in Service.
- Reconsider the current observation-timeout terminal rule separately. Controller recommendation: a single timed-out status check should release/backoff as an observation failure; the durable job deadline should own terminal expiry. If product explicitly wants one observation timeout to mean “abandon this wait,” that behavior and its timeout must be an explicit Host policy decision.
- Preserve callback/manual resolution as valid alternatives when automatic polling is disabled.

### Questions Resolved By Final Decision

1. Should the normal product entrypoint use configured `auto` polling for selected Fins awaiting tools, or require polling to be explicitly enabled every time?
2. Should one adapter observation timeout permanently mark the wait and Run `LOST`, or should it retry/back off until the durable wait deadline or another authoritative terminal result?
3. Should the wait-poller policy live in `host_runtime.json` as Host runtime configuration, with Service only assembling the selected profile?

### Follow-Up: Configuration Ownership

User direction: `wait_poller_policy` must come from configuration, and the awaiting resolution choice between poll and callback must also be configurable. The user asked whether this belongs in a scene and whether poll defaults belong in `host_runtime.json` or `execution_profiles.json`, noting that execution profiles already define `tool_execution_timeout_seconds`.

Controller judgment:

- Do not put wait resolution or poller policy in scene manifests. Scene owns LLM-facing prompt assembly, tool selection, model hints, and per-Run AgentPolicy hints. Wait observation is construction-time Host runtime behavior that persists across Attempts and can survive Host restart through durable wait records.
- Put each awaiting provider's selected resolution mechanism (`poll`, `callback`, or `manual`, validated against what that provider supports) in its provider config under `tool_discovery.json`. The concrete provider/adapter assembly owns this tool-specific fact. Current Fins assembly incorrectly hard-codes `WaitResumePolicy.POLL` in `_binding_for_tool_name(...)`.
- Put wait-poller enablement and generic runtime tuning in the selected Host runtime record in `host_runtime.json`. This includes poll cadence/backoff and bounded observation/close/concurrency settings that are passed to `open_host` once. Service should only map the typed Host runtime config and start a poller when an enabled poller policy, at least one selected poll-configured awaiting tool, and the matching poll adapter registry all exist.
- Do not put wait-poller runtime settings in `execution_profiles.json`. Execution profiles vary the LLM/Agent execution baseline for a Run; a wait poller is a Host process runtime shared across Runs and continues after the originating Engine Attempt has suspended.

`agent_policy.tool_execution_timeout_seconds` cannot own or replace poll observation timeout:

1. Engine applies it while awaiting the initial `ToolExecutor.execute(...)` batch handshake.
2. An awaiting-capable tool must return `ToolAwaitingOutcome` within that handshake budget.
3. Engine then suspends the Attempt; no original ToolExecutor call remains active.
4. Later Host poll observations are separate calls made by the background wait supervisor and are outside Engine/AgentPolicy.

Finite poll observation, close-drain, and outstanding-call bounds still have a real runtime purpose: a blocking adapter must not occupy threads forever, Host close must return within a bound, and repeated stuck observations must not create unbounded threads. Their existence is therefore not duplicated by `tool_execution_timeout_seconds`. Their exact packaged values should come from `host_runtime.json`, while code may retain only validation and invariant-preserving mechanics.

The remaining semantic decision is unchanged: whether an observation-call timeout merely revokes that call and schedules retry/backoff, or permanently resolves the wait and Run as `LOST`. Controller still recommends retry/backoff; a transport/status-check timeout is not proof that the external job is lost.

Current implementation caveat: Host defines `POLL`, `CALLBACK`, and `MANUAL`, but Fins bindings are hard-coded to `POLL`, and the repository currently provides only a framework-neutral callback mapper rather than a registered production HTTP route. A configured callback mode must fail during assembly unless the product runtime also supplies a real authenticated callback transport; configuration must not advertise a non-operational mode.

### Historical Verification And Final Decision

User confirmed that a long-running awaiting tool must not be limited by `tool_execution_timeout_seconds` and asked whether `observation timeout -> LOST` was inherited from the pre-process-based-tool era. The controller checked the GitHub issue chain, control document, accepted artifacts, commit history, and current design/code.

Direct history:

- GitHub Issue #168 / WU-LIFE-04 defined `tool_execution_timeout_seconds` as the original tool-call execution deadline and kept it in execution profiles, while explicitly excluding physical process termination from that WU.
- PR #170 / WU-TOOLS-CANCEL-01 merged process-backed execution for blocking Doc, the nine Fins read tools, and blocking Web tools. It deliberately did not put the long-running Fins download / preprocess / upload operation inside that ToolRuntime process capsule: those start-tool declarations are `async_direct`, register an observation, and return an awaiting `EXTERNAL_JOB` outcome within the Engine handshake.
- After the awaiting outcome is accepted, the Fins ingestion runtime owns the background long transaction. That runtime can dispatch work through its executor, and its synchronous Docling conversion sub-step still runs through a thread boundary that cancellation cannot physically stop. Therefore the statement "Fins tools remained thread-backed" is accurate for this awaiting ingestion execution path, but not for the separate Fins read-tool family, which PR #170 explicitly migrated to `process_backed`.
- Open GitHub Issue #175 exists for this exact remaining boundary: isolate the Docling conversion used by Fins download / upload in a child process or subprocess, let the parent own a hard upper bound and terminate / kill escalation, wire operation cancellation to that handle, and preserve atomic artifacts. It does not replace or reopen the already process-backed Fins read-tool decision.
- The current `observation timeout -> LOST` implementation was added later by commit `3f0d9d8b` on 2026-07-12 in Round3 R3-A S6, after PR #170 merged on 2026-07-05. It is therefore not old pre-process code that merely survived the migration.

The conceptual pattern was nevertheless reused: S6 contained an uncooperative synchronous poll adapter in a daemon thread, revoked its publication right after timeout, bounded outstanding calls, and then chose a Host terminal result. The containment mechanics are valid. The terminal classification is not: inability to complete one status query proves only that observation failed, not that the external job is lost.

Final controller decision:

- `tool_execution_timeout_seconds` remains the Engine-to-ToolExecutor handshake budget. Awaiting tools must return `ToolAwaitingOutcome` within it, but the accepted external long-running operation is not bounded by it.
- A `process_backed` ToolDefinition gives physical interruption only to the ordinary tool call executed inside that ToolRuntime capsule. It does not automatically enclose an awaiting external job or its later worker-thread sub-steps; those require an explicit process boundary such as the one tracked by Issue #175. Neither boundary changes the semantic owner of external-job completion.
- Wait observation timeout revokes late publication, records a transient diagnostic, releases the claim, and enters policy backoff. It must not call `resolve_wait` or terminalize the wait / Run.
- A wait becomes `LOST` only when a concrete adapter returns an authoritative typed lost outcome, or another explicit Host policy abandons waiting based on its own durable evidence. A generic status-query timeout is not such evidence.
- Issue #175 remains the owner for Fins Docling process isolation; it is now explicitly linked from the total-control document.

### Design Writeback

- The awaiting handshake-versus-external-operation boundary has been written to `docs/engine/design.md`.
- Wait configuration ownership and observation-timeout retry semantics have been written to `docs/host/design.md`.

## Topic 6 - Fins Storage, Source, Financial And XBRL Contract Expansion

Status: final user adjudication recorded; stable Fins design truth written to `docs/fins/design.md`.

The original merged label combined Codex F-08, F-09, F-10, F-11, F-20, F-21 and F-22. Direct inspection confirms that these are not one design decision and must not receive one blanket keep/delete ruling. They cover seven independent facts:

### 6.1 Batch ownership uses explicit and ambient authority at the same time (F-08)

`begin_batch()` returns a `BatchToken` containing `token_id`, `owner_token` and `owner_scope_id`, but repository mutation methods do not receive that token. Instead, storage also records an ambient `ContextVar` owner and recomputes the current asyncio task or thread identity before every mutation. A caller therefore has an explicit token for commit/rollback while actual write authority is decided by hidden execution context. The journal also persists owner token, task/thread scope, PID and hostname even though crash recovery primarily consumes ticker, phase and paths.

The real requirement is valid: concurrent writers must not accidentally join another transaction. The questionable mechanism is the second hidden authority. It rejects delegation to a helper/child task even when the transaction owner intentionally delegates, and an explicit token cannot by itself express write authority. This item needs redesign around one explicit transaction owner; it is not merely missing documentation.

### 6.2 Source business metadata doubles as a staging acknowledgement state machine (F-09)

`stage_source_document()` publishes or reuses source metadata with `ingest_complete=false`; blob storage refuses writes until that source acknowledgement exists; later final upsert changes the same business record to `ingest_complete=true`. Re-entry compares a closed set of stable fields, and read paths explicitly hide or reject incomplete records.

The real requirement is also valid: blobs must not become ownerless and a failed document mutation must not appear complete. The design concern is that transaction/staging state has become part of the durable source business schema. A simpler owner boundary would keep temporary metadata and blobs inside the storage transaction/staging area and publish one final source fact at commit. If crash-resumable partial ingestion is a product requirement, that state needs its own explicit ingestion-state contract rather than borrowing source metadata.

### 6.3 Provenance, revision, citation and read errors are four different concerns (F-10)

- Provenance/citation: storage persists `SEC_EDGAR`, `CNINFO`, `HKEXNEWS` or `USER_UPLOAD`; read runtime derives LLM-readable citation source from that typed fact. This fixes a real prior bug where `document_id` prefixes were guessed as provider identity. A buy-side financial-report agent needs source provenance, so the primary problem is missing Fins design truth, not the existence of the fields.
- Revision/cache consistency: storage hashes selected source metadata fields into a revision. Read runtime reads revision before and after metadata/processor construction; any change evicts caches and immediately returns `source_changed_during_read` with zero retry. Preventing stale mixed-version reads is necessary, but field-list hashing plus double read plus mandatory user-visible zero-retry failure is one particular policy. A storage-owned snapshot/version returned with the source, or a bounded retry, may be simpler.
- Typed read errors: decode, search-index, XBRL-query and concurrent-source-change failures use stable typed codes. Typed errors are preferable to message parsing and are not overdesign merely because they are public. Their exact value set and LLM projection need Fins design ownership.

### 6.4 Financial and XBRL output contracts mix essential facts with diagnostic detail (F-11)

For a financial statement, `periods`, `rows`, `currency`, `units`, `scale`, source citation and whether data is XBRL/extracted/partial are necessary to prevent the model from comparing values with the wrong period or multiplier. A typed partial reason is also useful because missing scale or fiscal semantics materially changes what the model may conclude.

The current contract goes further: it closes nine financial reason values, requires a `statement_locator`, and exposes every field through the public result. XBRL exposes both producer raw `total` and read-side `deduped_fact_count` even though returned `facts` are already deduplicated. Raw count remains useful for producer validation and diagnostics, but there is no demonstrated need for the LLM to reason over both counts. This item should preserve the minimal business result and separately adjudicate diagnostic-only fields/reasons; deleting the whole schema would remove required financial semantics.

### 6.5 Direct-stream terminal validation has three owners (F-20)

The Fins runtime buffers and verifies exactly one `RESULT`; Service wraps the stream and performs the same missing/duplicate check; CLI scans again and raises another missing-result error as a fallback. The invariant itself is correct: a download/upload command cannot end without one terminal result. The drift is that runtime, Service and CLI can independently decide the same protocol fact. One shared stream validator/typed terminal owner should decide it once; upper layers should only map the resulting typed success/error to their presentation.

### 6.6 HKEX exactly-100 results are treated as a failed completeness proof (F-21)

The provider requests one page of 100 rows. If HKEX returns `total > rows`, code fails. If no total is returned and exactly 100 rows arrive, code also fails because it cannot prove there is no 101st row. This avoids silently omitting a filing, which is a real correctness concern, but it turns `completeness unknown` into a task-level failure without pagination or continuation. The product decision is whether to implement provider pagination/date-window splitting, expose an explicit partial result, or retain fail-closed behavior. The number 100 itself predates the reviewed range; the new finding concerns the inference and failure policy.

#### Official Protocol Verification And Recommended Decision

The user confirmed that report discovery must not silently omit filings and asked whether HKEX can return the next 100 records. Direct verification against the official HKEX title-search frontend and live endpoint answered yes, with an important protocol detail:

- HKEX does not use an offset/page-number request for this UI. The official `loadMore()` increments the cumulative `rowRange` by 100 and repeats the same query. A request with `rowRange=200` asks for the first 200 records, not only records 101-200.
- The response provides top-level `rowRange`, `loadedRecord`, `recordCnt` and `hasNextRow`. Live checks with the same query and `rowRange=5`, `10` and `20` returned `(loadedRecord, recordCnt, hasNextRow)` of `(5,19,true)`, `(10,19,true)` and `(19,19,false)` respectively. A separate live request with `rowRange=1200` returned all 1,146 matching records and `hasNextRow=false`, so the official endpoint is not limited to one 100-record page.
- Current Dayu code sends exactly one `rowRange=100` request and has no continuation loop. Its generic total parser checks names such as `recordCount` but misses the actual official top-level name `recordCnt`; therefore an otherwise valid full-page response is classified as having no total and fails solely because its row count is 100.

Recommended owner contract for the fix:

1. Parse the official top-level pagination fields exactly; do not infer completeness from per-row `TOTAL_COUNT` or a loose family of guessed field names.
2. Start with cumulative `rowRange=100`. When `hasNextRow=true`, request at least the server-declared `recordCnt` (or the next cumulative range) using identical search/sort criteria.
3. Treat every response as a complete cumulative snapshot and consume only the final response; do not append overlapping 100-row prefixes, which would create duplicates and shift races.
4. Accept completeness only when `hasNextRow=false`, `loadedRecord == recordCnt`, and `loadedRecord == len(result rows)`. If the count changes while loading, repeat using the latest response facts.
5. If the server reports inconsistent fields, makes no progress, or continues claiming a next row while refusing a larger range, return a typed provider-protocol failure. Never silently return the first 100 as a complete candidate set.
6. Do not add date-range recursive splitting without evidence that the official cumulative protocol has a hard cap. The live endpoint accepted more than 1,000 rows; adding a second pagination mechanism now would be speculative. If a real provider cap is later observed, that evidence can justify date-window splitting while preserving the same completeness invariant.

This changes the preliminary product choice: retain fail-closed only for an invalid/stalled provider pagination contract, not for an ordinary full first page. Normal `hasNextRow=true` is a continuation signal and must be followed until complete.

### 6.7 Path containment is necessary, while raw-ID grammar coupling is optional (F-22)

Filesystem storage now rejects `.`, `..`, separators, absolute paths and drive expressions in ticker/document/file components; object keys are resolved and checked under the portfolio root. Removing containment would allow repository identifiers to escape the owned storage root, so the safety/correctness goal is necessary even without a repository-wide tool-security framework.

The narrower design question is whether an opaque external `document_id` must itself obey filesystem single-component grammar. The current code uses the raw ID as a directory component, so it rejects any future legitimate hierarchical/platform-specific ID. A cleaner design can keep containment while mapping/encoding opaque IDs to internal storage keys. This item is security-related and must be called out separately during final adjudication; the valid correction is not to delete traversal protection.

### Controller Classification

- Retain under Fins design truth: core provenance/citation, essential financial/XBRL fields and typed read failures.
- Redesign/fix: dual batch authority, source-meta staging leakage and three-layer direct-stream terminal validation.
- User-adjudicated HKEX direction: follow the official cumulative continuation until authoritative completion; fail closed only for inconsistent or stalled provider pagination.
- Security-related boundary: preserve path containment and decouple opaque IDs from filesystem grammar through a storage-owned mapping.

Because Host and Engine explicitly do not own financial-report domain semantics, putting these contracts into either existing design document would invert ownership. If retained, the appropriate stable truth is a dedicated Fins design document rather than `docs/host/design.md` or `docs/engine/design.md`.

### Final User Adjudication

The user accepted the controller recommendations and confirmed that HKEX discovery must continue until no filing is omitted. This merged finding is closed at the decision gate with the following implementation boundary:

1. Replace explicit-token plus ambient task/thread batch authority with one explicit transaction owner; keep cross-process lock and crash recovery as separate mechanics, and reduce journal facts to recovery inputs.
2. Remove source business meta as a public incomplete-ingestion acknowledgement state. Keep temporary meta/blob/processed writes in transaction staging and publish one complete source fact at commit. A future crash-resumable ingestion state requires a separate design/issue.
3. Retain typed source provenance, shared citation projection and typed business read errors. Move revision/snapshot ownership fully into storage; read consumers must not hash selected fields or own a second before/after version protocol.
4. Retain the minimum financial/XBRL business fields needed by the model. Keep implementation diagnostics such as processor-method absence, mandatory `statement_locator`, producer raw XBRL total and read-side dedupe diagnostics out of the required LLM-facing contract unless a concrete business consumer is established. Expose one XBRL count that equals the returned deduplicated facts.
5. Make exactly-one direct-stream terminal a single Fins-owned validator contract; Service and CLI mechanically consume it.
6. Replace HKEX full-first-page failure with official cumulative `rowRange` continuation and accept completeness only from consistent `hasNextRow` / `loadedRecord` / `recordCnt` / result-length facts.
7. Preserve filesystem containment. Decouple opaque domain IDs from raw path-component grammar through a storage-owned mapping/encoding boundary. Record this path-containment work separately as security-related in final closeout.

There is no remaining product-level open question for this merged finding. Exact class/helper names, transaction API shape and migration slices belong to the later implementation plan and must satisfy `docs/fins/design.md`.

## Topic 7 - CLI / Web / WeChat / Render Public Entrypoints

Status: final user adjudication recorded; stable UI/CLI design truth written to `docs/ui/design.md`.

The original merged label combined three materially different findings: the implemented-but-divergent
`upload_filings_from` workflow (Codex F-17), placeholder Web/WeChat/render package entrypoints
(Codex F-18), and `dayu-cli init` filesystem mutation policy (Codex F-19). They are adjudicated
separately below.

### 7.1 `upload_filings_from` must be fully implemented and aligned with OLD

Direct comparison with `/Users/leo/workspace/dayu-agent` confirms the intended product workflow:
scan a directory, classify filing/material files, and generate a platform-executable batch upload
script. The command does not directly upload. OLD generates `.sh` on macOS/Linux and `.cmd` on
Windows, supports explicit/default output paths, and returns a readable summary of recognized,
material and skipped files.

Current code implements directory classification through `dayu.fins.upload_batch`, but then emits
`{schema_version: 1, commands: [argv...]}` from `dayu/cli/commands/fins.py`. The README instructs a
caller to parse the file and invoke every argv. Repository search found no production consumer for
that schema. This is not faithful completion of the OLD workflow: it replaces the executable script
with a newly versioned CLI-grammar protocol and makes executable name, flag spelling/order and argv
shape a second public contract.

Final decision:

- `upload_filings_from` is required and must be completed in this WU; it must not be removed or
  downgraded to a human-only preview.
- Keep Fins-owned typed scanning/classification and use OLD as the product-behavior reference.
- Remove the unrequested JSON argv v1 public schema and its README/tests.
- Implement platform-correct executable script output, default/explicit output path behavior, safe
  argv quoting and a user-readable generation summary.
- Do not port OLD architecture or compatibility code. Fins owns the batch plan; CLI owns script
  rendering and current public command projection.

### 7.2 Tracked but unimplemented Web/WeChat/render entrypoints do not publish placeholder grammar

Current package metadata publishes `dayu-web`, `dayu-wechat` and `dayu-render`. Their modules do not
provide the advertised capability: they parse help or speculative subcommands/positionals, print an
unavailable diagnostic and return non-zero. In particular, WeChat predefines login/run/service and
service-management grammar, while render predefines input/output positionals before either capability
exists.

The user confirmed that Web, WeChat and render already have ISSUE tracking. Web is directly verified
as GitHub Issue #84 and WeChat as #147; both explicitly say they are tracking destinations rather
than code-generation-ready plans. The user confirmed an existing independent render tracker as well.

Final decision:

- Remove current placeholder package scripts, parser grammar, unavailable-state README claims and
  tests that freeze these non-capabilities.
- Keep the existing ISSUE trackers as the product backlog owners; do not create duplicate issues.
- When each ISSUE is implemented, publish its entrypoint, complete grammar, dependencies, README and
  smoke tests in the same WU as the real capability and correct Service boundary.
- An ISSUE proves that a future capability is desired; it does not authorize today's placeholder
  grammar.

### 7.3 Keep `init` atomicity and path safety under explicit UI/CLI design ownership

Current `dayu-cli init` copies existing config into a private staging tree, overlays package config
and prompts, swaps the complete config tree through a backup, restores the old tree on failed
replacement/interruption, and rejects containment escape or any symlink in the destination tree.
These mechanics solve real problems: multi-file config should not be left half-updated, and recursive
writes/deletes must not follow a workspace path outside the workspace.

Final decision:

- Align the user-visible init workflow with OLD `/Users/leo/workspace/dayu-agent`. Current code/README
  explicitly redefine init as a non-interactive config copier that never selects a model, asks for or
  persists an API Key, or performs first-run setup; that divergence is not accepted.
- Restore provider/model selection, required API-key setup, workspace manifest default-model update,
  optional Web/FMP/HuggingFace setup and first-run prewarm using the current repository schema and
  architecture. Do not copy OLD parser/service internals or write secrets into workspace JSON.
- When config already exists without `--overwrite`, preserve it and only add missing package prompt
  assets before continuing setup. With `--overwrite`, rebuild config from current package defaults.
- Retain whole-config staging, same-filesystem swap, backup rollback and cleanup for install/overwrite.
  Their stable promise is all-or-nothing config installation; temporary directory names remain
  implementation details.
- Put reset/bootstrap under one workspace-level exclusive lock. Workspace migration framework remains
  tracked by existing Issue #142 and is not duplicated in this WU.
- Retain lexical/resolved containment and symlink rejection for init mutation/reset. This is
  security-related and must be disclosed separately in final closeout.
- Align `--reset` with OLD: show `.dayu`, `config`, and product-present `assets` targets and require
  explicit confirmation, then delete those Dayu-owned/reconstructable roots and run first-time init.
  Do not delete `portfolio` or other user business files.
- Keep Web storage-state deletion. It lives under the Dayu-owned `.dayu` root, so explicit reset
  deletes it along with other runtime state. This does not implement the storage-state naming, TTL,
  refresh, concurrent publish or ordinary cleanup lifecycle deferred to Issue #178.
- The current repository has no `dayu/assets`; do not import unimplemented write/template product
  surface only to mimic an OLD directory. Issue #151 owns write and its required assets.

### Design Writeback And Closure

- Public entrypoint lifecycle, OLD-aligned `upload_filings_from`, and init mutation semantics are now
  recorded in `docs/ui/design.md`.
- Fins batch-plan ownership and its exclusion of CLI argv/schema facts are now recorded in
  `docs/fins/design.md`.
- There is no remaining product-level open question for this merged finding. Exact implementation
  slices and test migration belong to the later fix plan.

## Topic 8 - Engine Exception Message 240-Character Truncation

Status: final user adjudication recorded. Keep the current 240-character hard-coded error-message
projection; no production-code fix is required. This item predates the reviewed `b1a0631f^..HEAD`
range and is not added to the current-WU fix scope.

### Verified Current Behavior

`dayu/engine/agent.py` catches an ordinary Python exception escaping a Runner call. The catch point
logs the full traceback through `exc_info=True`, then creates a typed terminal failure with
`error_code=runner_exception`. Its public/durable `RunFailedData.message` is built as follows:

1. Read `str(exception)` and retain the Python exception type name.
2. If the text appears to contain an assigned API key, Authorization value, password, secret or
   token, replace the whole text with `exception message redacted`.
3. Otherwise truncate the raw exception text to at most 240 characters, including the
   `... [truncated]` suffix.
4. Prefix the result with the exception type, for example `RuntimeError: ...`. Therefore 240 is the
   raw-message projection limit, not a strict total length limit for the final typed message.

This helper is used for generic escaped Runner exceptions, not every Engine/provider failure. Typed
HTTP, provider-protocol, context-overflow, tool and policy failures follow their own contracts. The
same 240-character constant is also used for selected one-line Engine log previews, but it does not
mutate the original exception or traceback.

The resulting truncated message is ingested by Host into the canonical `RUN_FAILED` terminal fact,
projection/read model and Outbox, then exposed as `HostEvent.error_message` / terminal result and
printed by CLI on stderr. The full traceback remains in process logs; it is not preserved in this
durable terminal field.

### Correction To The Original Finding

AgentDS described this as a `run_failed` message visible to “LLM and callers”. Direct propagation
audit verifies caller/UI visibility but does not show ordinary failed-terminal text being inserted
into the next conversation prompt or Conversation Memory as LLM evidence. The LLM-facing part of the
original severity claim is therefore unsupported for this path. A compactor failure may include the
safe Engine outcome message in an operator-facing failure description, but that is not conversation
business evidence supplied to the model.

### Practical Effect

For `RuntimeError("x" * 500)`, Host and CLI receive an exception type plus the first part of the text
and `... [truncated]`. This prevents an unbounded raw exception from expanding terminal state and
reduces accidental secret exposure, while the full traceback remains available in logs. The cost is
that useful detail near the end of a long provider/library message can disappear from durable/public
diagnostics.

### Final User Adjudication

The user confirmed that this field is only an error message and accepted the current 240-character
hard-coded bound. Final decision:

- Keep sensitive-value redaction before projection.
- Keep the 240-character raw exception-message bound and explicit truncation suffix.
- Keep full traceback in operator logs; do not add a durable full-detail artifact/ref without a real
  requirement.
- Do not make the bound configurable and do not treat the hard-coded value as overdesign.
- Correct the prior review scope: this behavior predates the current WU range and needs no code fix.

The stable boundary is now recorded in `docs/engine/design.md`. Topic 8 is closed with no remaining
product or implementation question.

## Topic 9 - Correct The Tool Security Characterization

Status: final user adjudication recorded; Host authorization intent and Tool defensive-safety
boundary written to `docs/host/design.md` and `docs/tool/design.md`.

### Corrected Repository State

The prior statement “this WU contains no tool security code” was too broad. Direct inspection shows
three different categories:

- There is no repository-wide tool authorization framework that decides per principal/Run/Attempt
  which tools may read, write, execute or access which resource scopes.
- There are current local permission/config mechanisms, notably Doc `allowed_paths` and configurable
  Web network access policy.
- There are defense-in-depth mechanisms at actual I/O boundaries, including path containment,
  symlink rejection, Web egress/DNS/peer/resource checks, atomic filesystem mutation, storage-key
  containment and process late-publication fencing.

Host already records generic `authorization_claims` on mutating call context, but current code does
not map those claims into an effective tool resource authority. The existing field is therefore not
evidence that unified tool authorization has been implemented.

### Final User Adjudication

The user's design intent is:

- Unified tool security primarily means permissions: which locations/resources a tool may read or
  write and which side-effecting capabilities it may use.
- The final authorization owner should be Host ToolRuntime or an equivalent Host-owned tool
  governance boundary.
- The concrete framework has not been designed. This WU must not invent a role model, permission
  schema, policy DSL, capability-token system or sandbox implementation.
- Existing defensive security/safety implementations remain as they are. They are not removed merely
  because future authorization will be centralized.

Controller boundary clarification:

- Future Host authority owns the semantic decision and maximum allowed scope.
- Actual filesystem/network/process/storage boundaries must continue enforcement against symlink,
  resolve/redirect/DNS changes, TOCTOU, resource exhaustion and protocol abuse. A Host-only precheck
  cannot replace those controls.
- Until the unified model is designed, current `allowed_paths` and Web policy config remain effective.
  A later dedicated WU should migrate them to one Host authority source and delete duplicate
  permission truth rather than preserve compatibility branches.
- Existing local safety/security-related code must be disclosed accurately in final closeout, but it
  is not a current finding requiring deletion or redesign.

Topic 9 is closed at the design/adjudication gate. There is no production-code fix in this WU for a
future unified permission framework.
