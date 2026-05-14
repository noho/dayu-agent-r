# Gateflow Implementation Artifact: Host P2 S3 Payload / Artifact / Liveness

## Gate

- **work gate name**: implementation
- **work-unit**: Host Phase 2 Durable Store / EventLog / Payload Foundation
- **slice id**: Phase 2 Slice 3 - Payload Descriptor / Local Artifact Ref Helper / Host Instance Liveness / Diagnostics Foundation
- **approved plan path**: `docs/host/phase2-durable-store-eventlog-plan.md`
- **accepted plan commit**: `83c6ad6`
- **accepted Slice 1 commit**: `be5dbdc`
- **accepted Slice 2 commit**: `50ba2d7`
- **current branch**: `feat/host-phase2-durable-store-eventlog`

## Assigned Scope

实现 Slice 3 durable foundation：

- payload descriptor dataclasses / enums 与 SQLite payload insert / descriptor insert / read helpers。
- local artifact helper，在注入的 artifact root 下写入、fsync、digest verify、atomic rename，并只返回最终 `LocalArtifactRef`。
- host instance liveness dataclasses / enum 与 current-instance register / heartbeat / stopping / stopped / read helpers。
- structured errors 与测试覆盖 digest mismatch、payload / artifact reference failure、artifact orphan window、host instance identity conflict / missing registration。

## Explicit Non-Goals

本 slice 未实现、也未修改：

- Session / Run / Attempt state machine、command path、admission、projection、audit、outbox、ToolRuntime、Engine dispatch、Fins storage。
- recovery classifier、lease、fencing、takeover、dispatch record join、artifact cleanup scheduler、diagnostics table。
- `dayu.runtime`。
- `docs/host/design.md`、`docs/host/implementation-control.md`。

## Changed Files

- `dayu/host/durable/payload.py`
- `dayu/host/durable/artifact.py`
- `dayu/host/durable/liveness.py`
- `dayu/host/durable/event_log.py`
- `tests/host/test_payload_store.py`
- `tests/host/test_artifact_store.py`
- `tests/host/test_host_instance_liveness.py`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/gateflow-implementation-host-p2-s3-payload-artifact-liveness-20260514.md`

## Implementation Decisions

- `PayloadKind` 当前只包含 `sqlite_payload` 与 `artifact_ref`，直接对应已接受 schema 的 descriptor kind。
- `SQLitePayloadFormat` 当前只包含 `canonical_json` 与 `bytes`，JSON digest 基于 canonical JSON UTF-8 bytes，bytes digest 基于原始 bytes。
- `write_sqlite_payload` 在同一个 `HostTransaction` 中先写 `host_sqlite_payloads`，再写 `payload_descriptors`，并返回读回的 typed `PayloadDescriptor`。
- `write_payload_descriptor_for_artifact` 只接受已发布且已 digest verified 的 `LocalArtifactRef`；descriptor 写入仍在 SQLite transaction 中完成。
- `LocalArtifactStore` 不读取 cwd / env；artifact root 必须由调用方注入。temp 文件固定在 `artifact_root/.tmp/`，最终路径由 digest 派生为 contained relative path。
- artifact helper 在返回前完成 temp write + file fsync、digest verify、atomic rename、final directory fsync、final digest verify。
- EventLog append 对已存在 descriptor 做 digest 一致性校验；缺失 descriptor 仍由 SQLite FK 分类为 `HostForeignKeyError`，保持 schema 作为缺失引用真源。
- EventLog 对 artifact descriptor 做最终 artifact ref 校验，拒绝 `.tmp` 路径进入 accepted EventLog 引用链。
- host instance liveness 只表达当前 Host instance lifecycle diagnostic。heartbeat / mark 只能作用于同一 `host_instance_id + process_start_token + pid + boot_id` 身份；不解释 heartbeat stale，也不产生 orphan proof。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_payload_store.py tests/host/test_artifact_store.py tests/host/test_host_instance_liveness.py -q`
  - result: pass, `25 passed`
- `source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_durable_transaction.py -q`
  - result: pass, `15 passed`
- `source .venv/bin/activate && pytest tests/host/test_event_log_store.py tests/host/test_idempotency_store.py tests/host/test_event_log_multiprocess.py -q`
  - result: pass, `20 passed`
- `source .venv/bin/activate && pytest tests/host -q`
  - result: pass, `92 passed`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - result: pass, `0 errors, 0 warnings, 0 informations`

## README Decision

- Updated `dayu/host/README.md`.
  - Reason: `dayu/host/` changed and README still stated payload descriptor, artifact helper and host instance liveness were not implemented.
  - Scope: durable foundation current facts and non-goals only.
- Updated `tests/README.md`.
  - Reason: `tests/host/` gained payload, artifact and liveness durable foundation tests.
  - Scope: current host test command and durable foundation coverage list only.
- Did not update root `README.md`, `dayu/README.md`, `docs/host/design.md` or `docs/host/implementation-control.md`.
  - Reason: no user CLI / config / project workflow change, no terminology or layering change, and design / implementation-control docs are forbidden in this handoff.

## Open Questions

None blocking.

Non-blocking deferred items remain as accepted in the plan:

- Artifact orphan cleanup mechanism is deferred to a later cleanup / diagnostics work unit.
- Future command path may wrap `dayu.host.durable` types rather than exposing them directly.
- Recovery classifier and positive orphan proof remain Phase 9 / later recovery work, not Phase 2 liveness primitive.

## Residual Risks And Uncovered Areas

- SQLite and filesystem artifact publish are not atomic together. This is accepted by design; tests verify published-but-unreferenced artifact files are not accepted facts when SQLite transaction rolls back.
- Artifact helper writes content-addressed final paths and overwrites the same digest path with identical content. This is acceptable for the current immutable digest-derived artifact contract.
- Phase 2 liveness does not prove orphan status. Later recovery must combine liveness with dispatch records and process proof before marking Attempt `LOST`.
- This slice does not implement descriptor cleanup, projection, diagnostics table, command path consumption or state-machine admission.

## Phase 3 Readiness

Phase 2 durable foundation is complete for Phase 3 state machine / admission consumption within the accepted Phase 2 scope:

- SQLite durable store bootstrap / transaction runner are available.
- EventLog append / read and idempotency primitives are available.
- Payload descriptor and local artifact refs are available.
- Host instance liveness primitive is available.
- Required Slice 3 and Host regression validations pass.

No material schema or contract decision blocked implementation.

## Stop Condition Status

- Payload descriptor required ToolRuntime, Fins storage or trace projection: no.
- Artifact helper required cleanup scheduler or diagnostics projection: no.
- Liveness helper required dispatch record, recovery classifier or Attempt / Run state update: no.
- Implementation required forbidden docs or `dayu.runtime` changes: no.

## Artifact Path

`docs/reviews/gateflow-implementation-host-p2-s3-payload-artifact-liveness-20260514.md`
