# UF-FIX02 action-and-update-identity — S1 Code Re-review (AgentMiMo)

## Gate context

- Gate：`S1 re-review`
- Base：`56d159cb4bf13baf82858bb237b2f73075eaf717`
- Branch：`codex/upload-filing-oracle`
- Fix artifact：`docs/gateflow/uf-fix02-action-and-update-identity-s1-code-review-fix-20260813.md`
- First-round reviews：`docs/reviews/code-review-20260813-175624.md`（AgentMiMo）、`docs/reviews/code-review-20260813-180034.md`（AgentDS）
- Adjudication：`docs/gateflow/uf-fix02-action-and-update-identity-s1-code-review-adjudication-20260813.md`
- Re-review policy：独立核验 fix artifact 的 RED/GREEN 证据、finding 修复状态、S1 原始需求、UF-FIX01 零回归、coverage、pyright、README/no-touch、语义所有权收敛。禁止修改生产代码、测试或已有 artifacts。

## Independent verification results

### DS-02 strict is_deleted reader — PASS

**验证点**：canonical `is_deleted` 严格读取是否真正收敛到 `dayu.fins.storage` 公共唯一 owner，且两个消费者复用。

- 唯一实现：`dayu/fins/storage/source_meta_contract.py:13` — `require_source_meta_is_deleted(source_meta: Mapping[str, JsonValue]) -> bool`
- 公共导出：`dayu/fins/storage/__init__.py:35`（import）、`:66`（`__all__`）
- 消费者 1：`dayu/fins/storage/_fs_source_snapshot.py:54`（import）、`:765`（acquisition）、`:1089`（post-copy marker）— 两处均调用公共 helper
- 消费者 2：`dayu/fins/pipelines/docling_upload_service.py:43`（import）、`:1003`（`_can_skip_upload`）— 调用公共 helper
- 旧 private readers：`_require_deleted_flag`（snapshot）与 `_require_source_deleted_flag`（Docling）均已删除 — `grep -rn` 确认全仓不存在
- 实现质量：字段缺失抛 `KeyError`、非精确 bool 抛 `ValueError`、无 `get`/默认值/fallback/loose truthiness

**结论**：PASS。唯一 owner、两消费者复用、旧 duplicate 已删除。

### DS-03 CLI existing filing update projection — PASS

**验证点**：existing filing 的 update 与 update+overwrite 是否只投影 typed request、不依赖 missing target。

- `tests/cli/test_fins_commands.py:1309` — `test_upload_filing_existing_update_projects_typed_request_to_service`
  - 参数化 `overwrite=False/True`
  - 使用 `_seed_cli_filing_source(workspace_root)` 通过真实 storage owner 发布 existing filing
  - 断言 `exit_code == EXIT_SUCCESS`、`factory_calls == [workspace_root]`
  - 断言 `service.upload_filing_requests` 精确匹配 `_UploadFilingCall(ticker="AAPL", action="update", overwrite=overwrite, ...)`
- 冲突矩阵（`:1229`）仍覆盖 `update-missing` 与 `update-missing-overwrite` 两个 rejection 路径
- 旧 `test_upload_commands_map_args_and_validate_files`（`:1713`）已从 `action="update"` 迁移为 `action="create"`，不影响 update projection 覆盖

**结论**：PASS。update ± overwrite 成功 handoff 有真实 storage seeded 测试覆盖，冲突矩阵无回归。

### DS-04 prepare_upload Raises completeness — PASS

**验证点**：`prepare_upload` Raises docstring 是否完整登记 corruption `KeyError/ValueError`。

- `dayu/fins/pipelines/docling_upload_service.py:261-262`：
  ```
  KeyError: 既有 source meta 缺少 canonical ``is_deleted`` 时抛出。
  ValueError: 参数非法，或既有 source meta 的 ``is_deleted`` 非布尔值时抛出。
  ```
- `_can_skip_upload`（`:997-998`）也登记了对应异常

**结论**：PASS。公共函数异常契约已完整。

### S1 原始需求 — PASS

**update missing 无论 overwrite 均失败**：
- `evaluate_upload_overwrite_precondition`（`:186`）：`if action == "update" and previous_meta is None:` — 无 overwrite 条件
- `prepare_upload`（`:299-300`）：`UPDATE_TARGET_MISSING` → `raise FileNotFoundError`
- 测试覆盖：runtime 层 `test_validate_fins_upload_filing_request_rejects_missing_explicit_update`（参数化 overwrite=False/True）、Service 层 `test_prepare_upload_rejects_missing_update_before_shared_conversion`（参数化 overwrite=False/True × source_kind）、CLI 层 `test_upload_filing_state_conflict_exits_before_service_factory_without_mutation`（含 update-missing-overwrite case）

**deleted auto 不 skip**：
- `_can_skip_upload`（`:1003-1004`）：`if require_source_meta_is_deleted(previous_meta): return False`
- 测试覆盖：`test_execute_upload_deleted_equal_fingerprint_enters_conversion`（create→delete→update 恢复路径，converter 被调用两次）

**结论**：PASS。两个原始需求均有生产实现与测试覆盖。

### UF-FIX01 零回归 — PASS

**zero mutation**：
- CLI conflict tests 断言 `_snapshot_cli_workspace_tree(workspace_root) == before_tree`（`:1307`）
- 断言 `factory_calls == []`（`:1308`）

**atomic batch**：未修改 `commit_prepared_upload_batch` / `rollback_prepared_upload_batch`

**bounded stderr**：
- CLI conflict tests 断言 `len(captured.err) <= _MAX_PUBLIC_CONTENT_FAILURE_STDERR_CHARS`（`:1306`）
- 断言 `captured.err.count("\n") == 1`（`:1305`）

**cancellation**：未修改 cancellation 相关代码

**typed validation**：`_USAGE_MESSAGES` 文案与行为一致（`:753`：移除"或允许覆盖"）

**结论**：PASS。UF-FIX01 全部 contracts 无回归。

### DS-01 material parity — PASS（deferred-with-owner，无恶化）

**验证点**：S1 diff 是否新增或恶化 material create-existing 缺口。

- `prepare_upload`（`:295-296`）的 `source_kind is SourceKind.FILING` 守卫是 baseline 已有代码，S1 diff 未引入
- S1 diff 仅修改了：（1）admission matrix 的 update-missing 分支、（2）skip owner 的 deleted 检查、（3）strict reader 收敛
- material create-existing 的行为（同指纹 skip、不同指纹 conversion 后 `_resolve_upsert_mode` 失败）是 baseline 行为，S1 未改变

**结论**：PASS。DS-01 保持 deferred-with-owner，S1 diff 未引入或恶化。

## Quality checks

### Tests-first evidence

Fix artifact 记录了 RED/GREEN 证据：
- DS-03 CLI projection RED：fresh workspace 下 update 测试 exit 1、stderr 为 conflict → 证明需要 `_seed_cli_filing_source`
- DS-02 shared helper RED：`ImportError: cannot import name 'require_source_meta_is_deleted'` → 证明需要先创建公共模块
- GREEN：278 passed（独立复验确认）

### Coverage（独立复验）

```
Name                                            Stmts   Miss  Cover
-------------------------------------------------------------------
dayu/fins/ingestion_runtime.py                   2134    194    91%
dayu/fins/pipelines/docling_upload_service.py     406     55    86%
dayu/fins/storage/__init__.py                      13      0   100%
dayu/fins/storage/_fs_source_snapshot.py          443     63    86%
dayu/fins/storage/source_meta_contract.py          13      0   100%
-------------------------------------------------------------------
TOTAL                                            3009    312    90%
```

每个修改生产文件均独立达到 `>=80%`。PASS。

### Pyright（独立复验）

`0 errors, 0 warnings, 0 informations`。PASS。

### README 触发

- `dayu/fins/README.md`：diff 增加 `require_source_meta_is_deleted(...)` 到公共契约列表，增加 `is_deleted` 语义归属说明。符合其 Agent 更新约束（"当前代码已实现的公共契约"）。PASS。
- `tests/README.md`：未修改。测试层级、运行方式或维护规则未变化，不触发。PASS。
- 根 README / `dayu/README.md`：无用户入口、命令参数、工作流、分层或装配边界变化，不触发。PASS。

### Forbidden patterns scan

- 无 `hasattr`/`getattr` 滥用
- 无 `object`/`Any` 无类型签名
- 无兼容性 re-export、wrapper、facade
- 无 lazy import
- 无下游 fallback 或 loose truthiness
- 无重复 owner（`source_meta_contract.py` 是 `is_deleted` 严格读取的唯一 owner）

## Finding status

| Finding | Adjudication | Re-review verdict | Evidence |
| --- | --- | --- | --- |
| DS-01 material create-existing | deferred-with-owner | PASS（无恶化） | baseline 已有 FILING guard，S1 未引入或改变 |
| DS-02 duplicated strict reader | accepted | PASS（已修复） | 唯一 `source_meta_contract.py` 实现，两消费者复用，旧 readers 已删 |
| DS-03 CLI update projection gap | accepted | PASS（已修复） | seeded existing update ± overwrite 两个成功 typed handoff tests |
| DS-04 prepare_upload Raises | accepted | PASS（已修复） | docstring 完整登记 corruption KeyError/ValueError |

## Residual risks（与 fix artifact 一致）

| Residual | Classification / owner |
| --- | --- |
| material create-existing 无 typed admission | deferred-with-owner；后续独立 `upload_material action-contract` WU |
| `_resolve_upsert_mode` 旧 upsert 分支残留 | S2 |
| `ingestion_runtime.py:5102` loose deleted reader | UF-FIX08 |
| `cn_download_rebuild.py:151` loose deleted reader | UF-FIX08 |
| prevalidation → fresh recheck 同请求竞争 | UF-FIX10 |

无未分类 residual risk。

## Conclusion

**PASS**

S1 全部 4 个 findings（DS-01 deferred、DS-02/03/04 accepted）已按 adjudication 完成修复或正确 defer。S1 原始需求（update missing 无条件失败、deleted auto 不 skip）均有生产实现与三层测试覆盖。UF-FIX01 全部 contracts 零回归。每个修改生产文件 coverage >= 80%，pyright 零错误，README 更新在触发边界内，无 forbidden patterns。
