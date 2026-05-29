# Phase 15 Slice P15-S4 Implementation Artifact

## Scope

Gate: Phase 15 Slice P15-S4 Audit JSONL Retention And Tombstone Audit Record.

本次实现只覆盖 S4：public `purge_session` 成功返回前必须已经追加 purge tombstone audit JSONL line，并把该 audit record 的 ref/digest 写入 purge tombstone。未做 P15-S5/S6、projection rebuild、recovery multiprocess hardening、README final closeout、aggregate review、commit、push 或 PR。

## Changed Files

- `dayu/host/audit.py`
  - 新增 purge tombstone audit JSONL line builder / append helper。
  - 新增 audit line 识别 helper，用于识别 `source_eventlog_facts_purged=true` 的 tombstone audit line。
  - 抽出默认 audit sink options 派生逻辑，供 public command 与 opener 使用同一默认路径规则。
- `dayu/host/durable/purge.py`
  - 将 `PurgeSessionDeleteRequest` 从直接携带可空 audit ref/digest 改为携带 typed `PurgeTombstoneAuditRecorder`。
  - 在删除矩阵完成、tombstone insert 前构造稳定 tombstone id 和 deleted counts digest，调用 recorder 获取 audit ref/digest。
  - 强制 tombstone validation 要求 `audit_record_ref` 与 `audit_record_digest` 非空。
- `dayu/host/command.py`
  - 必要触及：S3 public `purge_session` 仍传 `audit_record_ref=None`，无法满足 S4 fail-before-success。
  - public command 现在从 durable store 的 artifact root 派生 audit JSONL sink options，并提供 JSONL recorder 给 durable purge helper。
  - audit append 的 `OSError` / file lock failure 映射为现有 `HostApiErrorCode.INTERNAL_ERROR`，`retryable=True`，不新增 public error code 或 API shape。
- `tests/host/test_audit_sink.py`
  - 覆盖 purge tombstone audit line append-only、幂等识别、既有 EventLog-derived JSONL line 保留。
- `tests/host/test_purge_session.py`
  - 覆盖 tombstone 必须带 audit ref/digest。
  - 覆盖 durable audit failure rollback，不留下 tombstone。
  - 覆盖 public `purge_session` 成功路径追加 audit line 并写入 tombstone ref/digest。
  - 覆盖 public audit append failure fail-before-success，不返回 successful result，不留下 successful tombstone。

## Implementation Strategy

根因判断：S3 裁决已明确 public command 层传 `audit_record_ref=None`，而 durable tombstone 允许 ref/digest 为空。这会产生成功 purge tombstone 无 audit evidence 的路径，违反设计中 append-only audit retention 与 purge tombstone audit record 的 release-blocking invariant。

实现采用 typed recorder 端口而不是让 durable 层直接 import JSONL sink：`dayu.host.durable.purge` 只表达“tombstone 写入前必须取得 audit ref/digest”的下层契约；具体 JSONL 路径、文件锁和 append-only 写入由 `dayu.host.command` 注入的 recorder 实现。

purge audit line 使用 tombstone id 作为 source key，字段包含 session id、purge tombstone ref、audit record ref、deleted counts digest、reason、actor/source、operation context refs/digest、request context、precondition/deleted refs digest、deleted counts 和 `source_eventlog_facts_purged=true`。line digest 基于稳定字段计算，不包含当前时间，避免 rollback 后 retry 与既有 source key 产生 digest 冲突。

## Fail-Before-Success Guarantee

`purge_session_durable` 的 normal path 顺序为：

1. replay / precondition 检查；
2. 在同一 SQLite write transaction 中执行删除矩阵；
3. 计算 stable tombstone id、deleted counts digest、deleted refs digest；
4. 调用 audit recorder append purge tombstone audit JSONL line，取得 `audit_record_ref` 与 `audit_record_digest`；
5. 校验 audit ref/digest 非空且 digest 合法；
6. 插入 purge tombstone，并写入 purge idempotency row；
7. transaction commit 后 public command 才构造 `PurgeSessionResult(purged=True)`。

如果 audit append 抛出 `OSError` 或 file lock error，异常发生在 tombstone insert 前且仍处于 write transaction 内，transaction runner 会 rollback 删除矩阵；public command 映射为 retryable `INTERNAL_ERROR`，不会返回 `PurgeSessionResult(purged=True)`。tombstone validation 也拒绝缺失或单边 audit ref/digest，防止 audit-pending successful tombstone 通过 durable helper 写入。

Replay path 读取既有 tombstone 返回结果，不重新追加第二个 tombstone；audit line append helper 以 tombstone ref 作为 source key，重复同一 line digest 时不追加重复行。

## Validation

已运行：

```bash
source .venv/bin/activate && pytest tests/host/test_audit_sink.py tests/host/test_purge_session.py -q
```

结果：

```text
33 passed in 0.49s
```

已运行：

```bash
source .venv/bin/activate && python -m pyright dayu/host/audit.py dayu/host/durable/audit.py dayu/host/durable/purge.py dayu/host/command.py tests/host
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

## README Decision

触发检查：本次修改触及 `dayu/host/` 与 `tests/host/`，已检查 `dayu/host/README.md` 与 `tests/README.md`。

结论：未修改 README。现有 `dayu/host/README.md` 已描述 `purge_session` destructive cleanup、tombstone replay、purge 后 read fail-closed 和 projection/audit 不重建 facts；`tests/README.md` 已覆盖 Host command/public session API 与 purge tombstone/read fail-closed 测试职责。本 slice 未改变 public API shape、命令用法、配置入口或 README 面向读者的稳定操作说明，只补齐内部 fail-before-success invariant 与测试。

## Residual Risks

- audit JSONL 是文件系统 append-only artifact，不与 SQLite 共享原子提交。当前实现选择 audit append before tombstone insert：可避免 successful tombstone without audit，但若 audit append 成功后 SQLite commit 失败，可能留下 audit line 而无 tombstone。该状态不违反 S4 的 fail-before-success 要求，重试时同 tombstone source key/digest 幂等跳过重复 append。
- audit line source key 冲突会导致 durable error 并 rollback purge；这保护 append-only audit 一致性，但需要运维按 JSONL 冲突排查 artifact 损坏或并发外部写入。
- 未修改 `utils/` analyze helper。当前 S4 边界内新增了 `audit_json_line_marks_purged_source_eventlog_facts` 供现有边界识别 tombstone audit line；没有发现必须触及现有 utils helper 的直接证据。
