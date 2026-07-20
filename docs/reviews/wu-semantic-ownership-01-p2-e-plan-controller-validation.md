# WU-SEMANTIC-OWNERSHIP-01 P2-E plan controller validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-E`
- Gate: plan
- Plan artifact: `docs/reviews/wu-semantic-ownership-01-p2-e-plan-codex.md`

## Controller Validation

The plan correctly treats the seven remaining broad-suite failures as a
validation fallout alignment problem, not as one semantic defect. It also
preserves owner-boundary discipline: if direct evidence contradicts the stale
test hypothesis during implementation, the slice must stop instead of updating
tests mechanically.

The proposed two-slice grouping is reviewable:

- Slice E1: Engine stream diagnostic level, Engine event contract and Engine
  public export snapshot alignment.
- Slice E2: Host public export snapshots, wait-resume integration assertion and
  purge-session fixture alignment.

## Review Focus

Reviewers should challenge:

1. Whether any of the seven failures require production code fixes rather than
   test/fixture alignment.
2. Whether `stream_idle.heartbeat` at `STREAM_DEBUG_LOG_LEVEL` is truly intended
   and whether tests should retain ordinary DEBUG gating.
3. Whether `input_projection` and the two Engine projection exports have design
   and artifact support as public contract.
4. Whether `HostThinkingView` belongs in both `dayu.host.__all__` and
   `dayu.host.api.__all__`.
5. Whether wait-resume integration should assert protocol replay messages or
   fallback guidance for this path, based on actual durable request atom/evidence
   presence.
6. Whether the purge fixture fix should add a semantically valid cancel request
   event rather than reusing arbitrary terminal events.
7. Whether one sub WU with two slices is too broad for the review/fix loop.

## Decision

Proceed to plan review. No implementation should start until accepted plan
findings are fixed and re-reviewed.
