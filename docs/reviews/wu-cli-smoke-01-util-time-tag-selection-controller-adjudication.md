# WU-CLI-SMOKE-01 util time + tag-only selection controller adjudication

## Scope

- Work unit: WU-CLI-SMOKE-01 follow-up
- Gate: implementation review / fix / re-review
- Implementation artifact: `docs/reviews/wu-cli-smoke-01-util-time-tag-selection-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/wu-cli-smoke-01-util-time-tag-selection-review-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-util-time-tag-selection-review-ds.md`
- Fix artifact: `docs/reviews/wu-cli-smoke-01-util-time-tag-selection-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-cli-smoke-01-util-time-tag-selection-rereview-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-util-time-tag-selection-rereview-ds.md`
  - `docs/reviews/wu-cli-smoke-01-util-time-tag-selection-controller-followup-rereview-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-util-time-tag-selection-controller-followup-rereview-ds.md`

## Controller decision

Accepted.

The follow-up correctly moves `get_current_time` into a `dayu.tools.utils`
ToolsDiscovery provider, keeps Engine out of tool registration, enables the
provider through `dayu/config/tool_discovery.json`, and changes packaged scene
manifest `tool_selection` to tag-only selection without changing `ScenePrepare`
public semantics.

## Finding adjudication

| Finding | Source | Decision | Final status | Reason |
|---|---|---|---|---|
| `infer.json` lost `start_fins_download` / `start_fins_preprocess` during tag-only migration | AgentDS review | accepted | fixed | Old `infer` manifest exposed read + download + preprocess tools. No design source authorized shrinking that tool surface. Fix restored `fins-read`, `fins-download`, `fins-preprocess`, and `utils`, while excluding `web` and `fins-upload`. |
| Non-string `timezone` produced an empty-value error message | AgentMiMo / AgentDS review | accepted | fixed | LLM-facing error recovery should identify the parameter type problem. Fix returns a clear `invalid_argument` message and keeps a concrete hint. |
| `ZoneInfoNotFoundError` branch appeared defensive / unreachable | AgentMiMo review | rejected-with-reason, then controller follow-up accepted related root cause | fixed | The branch itself is valid for missing IANA timezone data. Controller found the real defect: metadata timestamps loaded `ZoneInfo(DEFAULT_TIMEZONE)` before the protected `try`. Fix uses UTC metadata timestamps and tests the `timezone_load_failed` outcome. |
| Test diff contained formatting noise | AgentMiMo review | rejected-with-reason | not applicable | Review noise is not a correctness or architecture blocker for this gate. No broad reverse-formatting was requested. |

## Validation accepted

- Focused provider / manifest tests: `6 passed`, then provider follow-up `5 passed`.
- Affected file-level pytest group: `158 passed, 3 warnings`; warnings are edgar dependency deprecations.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.
- Real CLI smoke: `dayu-cli --log-level debug ... prompt --base workspace/tmp/wu-cli-smoke-time-workspace --ticker AAPL "等待10秒后输出现在是什么时间"` completed and log evidence recorded `tool_name=get_current_time` / `tool_fact_kind=completed`.

## Residual risk

- `get_current_time` intentionally supports only `Asia/Shanghai`; broader timezone support needs a separate schema and prompt design.
- Workspace custom scene manifests can still use `tool_names` or broad `fins` tags because the user explicitly limited this change to packaged manifest `tool_selection`, not `ScenePrepare` public semantics.
- Real CLI validation is a single environment smoke, not a CI substitute.

## Final status

Pass. No blocking findings remain for this follow-up gate.
