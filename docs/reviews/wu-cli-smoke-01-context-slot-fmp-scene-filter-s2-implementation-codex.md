# WU-CLI-SMOKE-01 Context Slot / FMP / Scene Filter S2 Implementation

## Metadata

- Gate: implementation slice S2
- Work unit: WU-CLI-SMOKE-01 context slot / FMP / scene tool filtering follow-up
- Agent: AgentCodex
- Accepted plan: `docs/host/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan.md`
- Controller adjudication: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-controller-adjudication.md`
- Accepted plan commit: `645c7473`
- Accepted S1 commit: `2824ee59`
- Current state commit at start: `a124e0a8`

## Changed Files

- `dayu/fins/resolver/__init__.py`
- `dayu/fins/resolver/fmp_company_info.py`
- `dayu/service/scene_context.py`
- `dayu/cli/commands/prompt.py`
- `dayu/cli/commands/interactive.py`
- `dayu/cli/commands/session.py`
- `tests/fins/test_fmp_company_info_resolver.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `tests/service/test_import_boundary.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_session_command.py`
- `dayu/fins/README.md`
- `tests/README.md`

## Behavior Implemented

- Added `dayu.fins.resolver` as a public subpackage without re-exporting symbols from `dayu.fins`.
- Added `FmpCompanyInfo(canonical_ticker, company_name, ticker_aliases)` with immutable `tuple[str, ...]` aliases. Tuple is intentional public-contract immutability: callers cannot mutate resolver-returned business facts after resolution.
- Added `FmpCompanyInfoResolver` with explicit `api_key`, injectable `FmpHttpClientProtocol`, and configurable positive finite timeout. The resolver does not read env.
- Ported OLD two-hop FMP algorithm:
  - `search-symbol` resolves the company name.
  - `search-name` finds strictly same-name securities.
  - aliases are normalized through existing ticker normalization helper where possible, deduped, and canonical ticker is always first.
- Added `dayu.service.scene_context` as the Service-facing slot text source:
  - `fins_default_subject(None) == ""`.
  - ticker-only subject: `# 当前分析对象\n你正在分析的是 V。`
  - FMP-enhanced subject: `# 当前分析对象\n你正在分析的是 V（Visa Inc.）。`
  - `current_time(...)` returns Chinese 24-hour `Asia/Shanghai` text such as `# 当前时间\n现在是 2026年7月7日 15:08（Asia/Shanghai，星期二）。`
  - `EntrypointContextSlotRequest` carries `ticker`, `now`, `fmp_api_key`, and `fmp_timeout_seconds`.
  - `build_entrypoint_context_slot_values(...)` returns typed JSON slot values and falls back to ticker-only subject on missing key or FMP resolver failure.
- Updated `dayu-cli prompt` to read `FMP_API_KEY` at the CLI/Service boundary and call the Service scene context builder. CLI no longer writes raw ticker or `"未指定具体公司"` into `fins_default_subject`.
- Updated `dayu-cli interactive` to stop providing `fins_default_subject`; it only provides the `base_user` slot still required by the current manifest until S3 removes it.
- Updated `dayu-cli session` carrier runtime slot values so list/purge no longer use `"未指定具体公司"`; current prompt manifest still requires `base_user`, so it remains as a temporary manifest-required slot.
- Updated Service import boundary tests to allow the new designed Service dependency on `dayu.fins.resolver` and `dayu.fins.ticker_normalization`; this does not allow Service access to Fins storage or pipelines.
- Updated README facts for the new Fins resolver and related test coverage.

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/fins/test_fmp_company_info_resolver.py
# 7 passed

source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py
# 90 passed, 3 warnings

source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py
# 48 passed, 3 warnings

source .venv/bin/activate && pytest tests/service/test_import_boundary.py tests/service/test_weak_typing_guard.py -q
# 2 passed

source .venv/bin/activate && pyright
# 0 errors, 0 warnings

git diff --check
# passed
```

Warnings were existing `edgar` deprecation warnings and unrelated to this slice.

## Deviations From Plan

- `tests/service/test_import_boundary.py` was updated even though it was not listed in the user’s narrow allowed test files. This was necessary because the S2-approved architecture adds `dayu.service.scene_context -> dayu.fins.resolver` / ticker normalization as a legitimate Service-to-Fins public business dependency. Without this update, the existing import-boundary test fails while production code follows the accepted plan.
- S2 did not remove `base_user` globally or edit prompt manifests. Current prompt/interactive/wechat manifests still require `base_user`; S3 owns global manifest and prompt asset cleanup.

## Residual Risks

- Real FMP network/API-key behavior was not manually validated. Classified as covered by later approved slice / optional smoke; automated tests use fake HTTP and monkeypatch resolver coverage.
- Prompt scene still has manifest-required `base_user` and therefore prompt/session still pass that slot for compatibility with current assets. Classified as covered by later approved slice S3.
- `current_time` is generated by the Service builder even when the current prompt manifest does not consume the slot. Classified as covered by later approved slice S3, which will align prompt assets/manifests and final slot usage.

## Completion Status

S2 implementation is complete locally. No commit, push, issue, or PR was created per user instruction.
