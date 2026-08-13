# Code Review

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `69bc9d2a`
- Output file: `docs/reviews/code-review-20260813-143000-final-mimo.md`
- Included scope: 69bc9d2a..b1064bd9 共 12 commits，57 文件，+6514/−690 行
- Excluded scope: DS 本轮 artifact（按指令不读取）
- Parallel review coverage: 无（按指令禁止子 agent）

## Checklist Verification

### 1. usage validation 唯一真源与 bootstrap 前零 mutation / exit2 exact actionable reason

**结论：PASS。**

- `validate_fins_upload_filing_request()` 是 filing 上传请求验证的唯一真源 owner。它调用 `_validate_fins_upload_filing_static()` 处理全部静态字段校验（ticker、action、files、fiscal_year/period、amended、date、overwrite），再叠加 published-state 前置条件校验（create 目标已存在、update 目标缺失、company name 要求）。
- CLI `_prevalidate_upload_filing_request()` 在 `FINS_DIRECT_SERVICE_FACTORY(workspace_root)` **之前**调用 `prevalidate_fins_upload_filing_request_for_workspace()`，后者以 `create_directories=False` 构造 `FsFilingUploadStateRepository`，不创建 identity/ticker/lock/job 目录。
- `FinsUploadUsageError` 携带 `FinsUploadUsageFailure`（closed code + bounded actionable message）→ CLI 捕获后输出 `exc.failure.message` 并返回 `EXIT_USAGE_ERROR`（exit 2）。
- `FinsUploadPrevalidationError` 携带 `FinsUploadFailureReason`（kind=STORAGE, code=STORAGE_IO, path-free message）→ CLI 捕获后输出 `exc.failure.message` 并返回 `EXIT_FAILURE`（exit 1）。
- 证据：UF-PF01 bundle 25 个 usage cases 全部 exit 2 且 workspace tree 零 mutation。

### 2. runtime/content exit1 不靠字符串匹配

**结论：PASS。**

- `FinsUploadFailureKind`（CONTENT/STORAGE/RUNTIME）和 `FinsUploadFailureCode`（8 个 closed code）是 str Enum，不是字符串。
- `fins_upload_failure_from_exception()` 使用 `isinstance(error, DoclingConversionError)` → CONTENT，`isinstance(error, OSError)` → STORAGE，其它 → RUNTIME。不依赖 `str(exc)` 或消息文本分类。
- `_DOCLING_FAILURE_CODES` 映射表将 6 种 `DoclingConversionFailureKind` 精确映射到对应 `FinsUploadFailureCode`。
- pipeline/workflow 的 `except` 块按类型分层捕获：`DoclingConversionCancelledError` → cancelled；`DoclingConversionError` → content；`OSError` → storage；`Exception` → runtime。

### 3. company meta + source publication fresh/existing 同一 storage batch 原子提交且无补偿删除

**结论：PASS。**

- SEC/CN workflow 在 `prepare_upload` 返回 prepared mutation（非 `UploadOperationResult`）后，开启 **单一** `publication_batch`。
- `stage_upload_company_meta_decision(repository, decision, batch=publication_batch)` 先 stage company meta。
- `commit_prepared_upload_batch(service, batching_repository, batch=publication_batch, prepared=prepared_upload)` 在**同一个 batch** 中 stage source/blob 并 commit。
- stage 失败时调用 `rollback_prepared_upload_batch()` 回滚该 batch，不进入 commit。rollback 保留主异常证据。
- 转换失败（`DoclingConversionError`）、取消（`DoclingConversionCancelledError`）或 skip 路径不开启 batch，不删除旧文档。
- 代码中无补偿删除逻辑。
- 证据：UF-PF01 UF-ATOMIC-FRESH（fresh_atomic exit 1 不发布）和 UF-ATOMIC-EXISTING（existing_atomic exit 1 SHA 不变）均 PASS。

### 4. authoritative revalidation / identity fail-closed

**结论：PASS。**

- SEC/CN workflow 入口处从注入的 `FilingUploadStateRepositoryProtocol.read_filing_upload_state()` 读取 fresh snapshot。
- 调用同一 `validate_fins_upload_filing_request(raw_request, published_state=fresh_state)` 重新验证。
- `_assert_authoritative_filing_identity(preflight, authoritative)` 断言 canonical ticker、document_id、internal_document_id 三者一致；不一致时 `raise RuntimeError("filing authoritative identity mismatch")`。
- 只有 authoritative request 的 resolved_action、published_state.source_meta、company_meta_decision 驱动后续 prepare/stage/commit，旧派生值被丢弃。

### 5. UF-FIX09 shared interruptible converter 不回退

**结论：PASS。**

- `_isolated_inherited_stderr()` context manager 仍然包裹 `convert_pdf_bytes_with_docling()` 调用。
- 使用 `os.dup` / `os.dup2` 操作底层 FD，不只替换 `sys.stderr`。
- 退出时恢复原 FD，flush 清理失败不改写 conversion 失败分类。
- `DoclingConversionCancelledError` 和 `DoclingConversionError` 仍为独立 typed 异常，继承 `RuntimeError` 而非互相继承。
- DoclingUploadService `prepare_upload` 的 `previous_meta` 参数由 caller 从 authoritative request 传入，不再由 service 自行读取。

### 6. README / 测试 / pyright / coverage

**结论：PASS。**

| 检查项 | 结果 |
|---|---|
| pyright | 0 errors, 0 warnings, 0 informations |
| 测试 | 524 passed, 0 failed |
| README.md | 新增 upload_filing 行为说明段落 |
| dayu/fins/README.md | 新增 typed validator / atomic batch / failure contract / stderr 隔离说明 |
| dayu/service/README.md | 更新 fins_direct filing upload handoff 描述 |
| tests/README.md | 新增 UF-FIX01 owner coverage 段落 |

### 7. UF-PF01 exact argv / streams / tree / durable / SHA integrity 及无 UF-PF12 / registry 越界

**结论：PASS。**

- bundle digest: `5e311272dce426a79e841f5963a050d3491cd7f48f9e67c928d30bf76360b350`
- 30/30 cases passed，0 integrity failures
- usage cases (25): exit 2，workspace tree 零 mutation
- content cases (UF-I11–I13): exit 1，真实 corrupt input，不发布 company/source
- atomic fresh (UF-ATOMIC-FRESH): exit 1，corrupt input 不发布
- atomic existing (UF-ATOMIC-EXISTING): 先 seed 成功，再 corrupt update 失败，company/source 全文件 SHA 不变
- 未使用 mock/fake/monkeypatch/fault injection
- 未运行 UF-PF12

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `upload_failure_reason_from_json` 的 round-trip 测试（serialize → deserialize → equality）在当前测试集中未独立验证，但 UF-PF01 content cases 间接覆盖了 failure reason 在 pipeline result 中的投影。
- coverage 因 numpy import 冲突无法在当前环境生成精确百分比，但 524 个测试全部通过且 pyright 零报错，静态正确性已验证。

## Conclusion

**PASS。** 全部 7 项核销清单通过，无阻塞 finding。implementation 69bc9d2a..b1064bd9 满足 UF-FIX01 final gate 要求。
