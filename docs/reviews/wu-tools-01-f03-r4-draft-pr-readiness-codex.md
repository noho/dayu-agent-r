# WU-TOOLS-01-F03-R4 Draft PR Readiness

## Scope

- Gate: ready-to-open-draft-PR
- Branch: `phase/wu-tools-01-f03-r4`
- Issue: GitHub issue-133, title `评估并调整 Tools Discovery spec 语义`
- Base: `main`

## Local State

- `git status --short`: clean before this readiness artifact.
- `git branch --show-current`: `phase/wu-tools-01-f03-r4`
- `git log --oneline main..HEAD`: branch contains only WU-TOOLS-01-F03-R4 gate commits:
  - `3463ae9d` `gateflow: accept deepreview for WU-TOOLS-01-F03-R4`
  - `21751ec9` `gateflow: accept WU-TOOLS-01-F03-R4 slice 7 validation`
  - `d8db0b49` `gateflow: accept WU-TOOLS-01-F03-R4 slice 6`
  - `ee5f2e19` `gateflow: accept WU-TOOLS-01-F03-R4 slice 5`
  - `4514f550` `gateflow: accept WU-TOOLS-01-F03-R4 slice 4`
  - `3f7fd44a` `gateflow: accept WU-TOOLS-01-F03-R4 slice 3`
  - `c785f218` `gateflow: accept WU-TOOLS-01-F03-R4 slice 1`
  - `fe212365` `gateflow: accept plan for WU-TOOLS-01-F03-R4`

## Gate Checklist

- Approved plan exists: `docs/host/host-issues/wu-tools-01-f03-r4-tools-discovery-spec-plan.md`.
- Plan review, plan fix, and plan re-review artifacts exist and passed.
- All implementation slices are complete:
  - Slice 1 accepted commit: `c785f218`
  - Slice 2: covered by Slice 1 controller judgment
  - Slice 3 accepted commit: `3f7fd44a`
  - Slice 4 accepted commit: `4514f550`
  - Slice 5 accepted commit: `ee5f2e19`
  - Slice 6 accepted commit: `d8db0b49`
  - Slice 7 final validation accepted commit: `21751ec9`
- Aggregate deepreview passed:
  - AgentMiMo artifact: `docs/reviews/wu-tools-01-f03-r4-aggregate-deepreview-mimo.md`, verdict `pass`
  - AgentDS artifact: `docs/reviews/wu-tools-01-f03-r4-aggregate-deepreview-ds.md`, verdict `pass`
  - Accepted deepreview commit: `3463ae9d`
- Accepted findings requiring fix: none.
- Tests and type checks:
  - Focused WU suites passed.
  - `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`.
  - Broad affected suite excluding classified non-WU web smoke residual: `866 passed, 1 skipped`.
- Docs decision complete:
  - `docs/host/design.md`, `dayu/config/README.md`, `dayu/fins/README.md`, `tests/README.md`, review artifacts, and control doc updated.
- Residual risks have owners:
  - `WU-TOOLS-01-F03-R4-POLICY-R1`: Future Host / policy design
  - `WU-TOOLS-01-F03-R4-PATH-R1`: Future provider path-boundary hardening
  - `WU-TOOLS-01-F03-R4-SCENE-R1`: Future scene manifest maintenance
  - `WU-TOOLS-01-F03-R4-WEB-SMOKE-R1`: Web smoke / CI owner

## Issue Association Decision

GitHub issue-133 asks to evaluate and adjust six Tools Discovery spec items:

1. remove provider-level `allow_empty`;
2. remove `include_read_tools`;
3. change `workspace_root` default to `workspace/`;
4. migrate `financial-read-tools` OLD limits;
5. remove `financial-upload-tools.allowed_upload_roots`;
6. migrate `doc-tools` OLD limits.

All six items are implemented, tested, and documented in this branch. Deferred risks are either explicit non-goals or unrelated web smoke ownership. The draft PR body should use `Closes #133` and list remaining deferred owners so merge can close issue-133 without hiding future work.

## Completion Status

Ready to push and create draft PR. No blocking open question remains for draft PR creation.
