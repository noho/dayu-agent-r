# Phase 13 Schema Version Controller Clarification

## Context

The accepted Phase 13 plan was written before Slice 1 implementation and stated that the Host durable schema should bump from version 10 to 11.

Slice 1 has now been accepted and committed as `7432f02`, adding `host_audit_sink_markers` and bumping the schema to version 11.

## Clarification

For the remaining Phase 13 schema-changing slices, implementation must treat the current committed schema version as truth and apply fresh-schema bumps incrementally:

- Slice 2 Tool Trace Hot JSON / Cold JSONL must bump from 11 to 12 when adding `host_tool_trace_hot`.
- Slice 3 Outbox durable projection must bump from the then-current schema version to the next version when adding outbox tables.

This does not introduce compatibility migration behavior. The project still follows fresh schema semantics: schema bootstrap accepts only empty stores or the current version.

## Reason

Keeping schema version 11 while adding new tables would hide a schema change behind an unchanged version. That would violate the project schema discipline and make tests unable to detect stale store shape.

## Stop Condition

If an implementation slice finds an unexpected committed schema version or needs compatibility migration logic, it must stop and return to controller.
