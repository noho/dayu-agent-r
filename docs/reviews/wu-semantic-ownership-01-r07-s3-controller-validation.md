# WU-SEMANTIC-OWNERSHIP-01 R07-S3 Controller validation

## 1. Gate 与结论

- 本文验证既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R07-S3 累计实现，不创建新 WU，也不关闭 umbrella。
- implementation artifact：`docs/reviews/wu-semantic-ownership-01-r07-s3-implementation-codex.md`。
- 工作树 HEAD：`386fef8d7a7ecbd977c455ca86bb8bab875d1a98`。
- accepted plan：`docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`，Controller 独立复核 SHA-256 为 `ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`。
- staged paths 为空；R07-S1/S2/S3 仍是 accepted plan §10.2 要求的累计未提交 final tree。

结论：**PASS / READY FOR DUAL COMPLETE CUMULATIVE S1+S2+S3 CODE REVIEW**。

## 2. Controller validation findings 与关闭状态

Controller 在首次独立验证后接受四组 implementation validation gap，并在同一 S3 task 内交回 AgentCodex 修复：

1. `R07-S3-CV-F01`：invalid UTF-8 / processor build failure 后不仅要验证 typed error 和空 cache，还必须证明 storage full-snapshot 临时树真实删除。
2. `R07-S3-CV-F02`：full snapshot 已取得、processor 已构建但尚未 publish 时触发既有 cancellation token，必须保留 typed cancellation 优先级、空 cache，并删除未发布 snapshot；不得增加 production seam、sleep 或 fallback。
3. `R07-S3-CV-F03`：process target 必须分别证明 completed、typed/business failed、unexpected execution failed 三路各自关闭 runtime；既有 target 不产出 cancelled envelope，read-runtime cancellation cleanup 由 F02 的 owner test 覆盖。
4. `R07-S3-CV-F04`：收敛 `_retire_entries` docstring、`read_section` 重复注释、coverage 重复结论，并在 `DefaultFinsRuntime.get_read_runtime` 记录 close 后 `RuntimeError`。

最终代码和 owner tests 已关闭 `R07-S3-CV-F01..04`：

- invalid UTF-8 保持 `SOURCE_DECODE_FAILED` typed owner/cause；processor build failure 保持原异常实例；两者均证明 cache 为空且 probe 记录的唯一 full-snapshot root 已不存在。
- cancellation 在 publish 前传播 `FinsReadCancelledError`，processor 未进入 cache，唯一 full-snapshot root 已删除。
- process target 三个执行终态分别创建并关闭不同的 `DefaultFinsRuntime`，同时保持 completed、`invalid_argument`、`execution_error` envelope。
- 没有增加 compatibility、下游补偿、测试驱动 production seam、统一 authorization 或 deferred Issue 能力。

最终 ledger：`4 closed / 0 open / 0 blocker`。

## 3. 累计实现复核

Controller 复核累计 R07 final tree 的关键 owner 行为：

- storage 是 opaque identity、persisted publication revision 与 stable full/light snapshot 的唯一 owner；consumer 不再用 raw identity path、字段 hash 或 before/after reread重建一致性。
- generic LRU 只返回 displaced values；snapshot entry/borrow lifecycle 由 read runtime 统一拥有 processor、meta、provenance、citation 与 result。
- replacement、eviction、clear、runtime close、losing/build/decode/cancellation 路径都 retire/close snapshot；active borrow 延迟到最后一次 release 才关闭。
- exact document ID 的 source-kind resolution 由 storage 0/1/2 typed lookup 决定；alias fallback 枚举 typed namespaces 并拒绝跨 kind 多文档歧义，不再 filing-first 猜测。
- composition root 和 process target 接通 runtime close；没有把 Host cancellation 或 process isolation 扩张到 R07。
- containment、symlink 防护、atomic publication/recovery、path-free public error、typed source-changed failure 均保留。

未发现与 controller discussion、`docs/fins/design.md` 或 accepted plan 直接矛盾的代码证据。

## 4. 验证证据

AgentCodex 最终验证：

- follow-up 精确节点：`4 passed, 3 warnings`；
- 累计八测试文件：`489 passed, 3 warnings`；
- 20 个累计 changed production 文件 line coverage 全部 `>=80%`，最低 `_fs_identity.py=80.00%`，`read_runtime.py=81.09%`；
- full pyright：`0 errors, 0 warnings, 0 informations`；
- cumulative scoped Ruff：`0`；full inherited Ruff ledger 保持 `150`，分布为 `F401=70`、`E402=66`、`F841=10`、`F541=3`、`F821=1`；
- 正式目录 full suite：`4878 passed, 3 failed, 3 skipped, 5 deselected, 3 warnings`；三项 failure 与 accepted plan §1.1 inherited ledger 的 node/type/location/text fingerprint 精确一致；
- `git diff --check`、allowlist、identity/source/AST/LLM-facing scans 通过。

Controller 在最终 follow-up tree 上独立执行：

```text
pytest -q \
  tests/fins/test_processor_read_consistency.py::test_read_runtime_maps_invalid_utf8_to_source_decode_failure \
  tests/fins/test_processor_read_consistency.py::test_processor_build_failure_closes_unpublished_full_snapshot \
  tests/fins/test_processor_read_consistency.py::test_processor_build_cancellation_closes_unpublished_full_snapshot \
  tests/fins/test_fins_storage_provider.py::test_fins_read_process_target_closes_runtime_on_success_and_failure
```

结果：`4 passed, 3 warnings in 0.98s`。

Controller 还独立得到：

- `pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`；
- 对全部当前 Python diff 执行 Ruff：`All checks passed!`；
- `git diff --check`：通过；staged paths：空；
- HEAD 与 plan SHA-256 精确匹配；
- `get_source_revision`、`_build_source_revision`、`revision_before`、`revision_after`、production `_resolve_source_kind`：无残留；唯一 `_resolve_source_kind` 命中是 owner guard test 的禁止字符串。

此前 Controller 已独立重跑累计八文件并逐文件从 coverage JSON 复算 20 个 production owner，得到 `487 passed` 且全部 line coverage `>=80%`；最终新增的两个 owner tests 只把累计通过数提高到 `489`，未降低任何 production coverage，AgentCodex 的最终逐文件复算再次确认门禁成立。

## 5. Inherited failure 与 scope 裁决

正式目录 full suite 的三项失败保持既有 ledger：

1. runtime logging order 节点在全量顺序中失败、隔离通过；
2. Service host-admin fixture 缺少 `wait_poller_policy`；
3. Service import boundary 仍有既有两项 `_ingestion_tool_helpers` 导入。

它们的 owner、位置和文本未因 R07 扩散，不属于 R07 allowlist，因此不接受为本 gate finding。裸 `pytest -q` 的 `workspace/tmp/r06-base-9c07b88d` `ImportPathMismatchError` 同样是已记录的外部临时树 collection 条件，未删除该树制造绿色结果。

R08 financial/XBRL contract、R09-R12、Issues 142/151/175/177/178、统一 tool authorization、push 与 PR 均未授权，也未实施。

## 6. Handoff

下一 gate 是 AgentMiMo 与 AgentDS 对完整累计 R07-S1+S2+S3 final tree 做并发 code deepreview。审查必须覆盖 semantic ownership、snapshot/resource lifecycle、concurrency、cleanup/error priority、opaque identity/non-leak、组合行为、overdesign 与 accepted plan 一致性。所有 accepted findings 必须由 AgentCodex 修复并经双路完整 re-review；在此之前不得创建 R07 accepted implementation commit。
