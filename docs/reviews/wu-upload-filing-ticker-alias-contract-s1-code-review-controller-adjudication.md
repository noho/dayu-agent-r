# upload-filing-ticker-alias-contract S1 code review controller adjudication

## Gate metadata

| 字段 | 值 |
| --- | --- |
| Gate | `S1 code review adjudication` |
| Work unit | `upload-filing-ticker-alias-contract` |
| Accepted plan commit | `5508d0445bd1d649fee54f4ec3d65f99e2484493` |
| Timestamp | `2026-08-15 00:06:18 +0800` |
| Implementation artifact | `docs/reviews/wu-upload-filing-ticker-alias-contract-s1-implementation-codex.md` |
| Review artifacts | `docs/reviews/code-review-20260814-235645.md`; `docs/reviews/code-review-20260815-000420.md` |
| Decision | `fail` |
| Next gate | `S1 fix` |

## Controller conclusion

S1 的 identity、CompanyMeta、filing/material producer、CLI/tool 与 storage consumer 主体迁移成立，但尚不能提交。AgentDS 的两个中严重度 finding均由直接代码/验证证据支持；6-K 单文件覆盖率还违反项目与accepted plan的硬门槛。进入 S1 fix 后必须重新review。

## Findings adjudication

### F1 — `accepted`：6-K 单文件 branch coverage 76%

`dayu/fins/pipelines/sec_6k_primary_document_repair.py` 是本slice实际修改的生产文件，逐文件branch coverage必须达到`>=80%`。不能以本次变更行已覆盖或缺口属于既有分支为由豁免。

Required fix：只补行为有效的 owner/public-path tests，优先覆盖artifact列出的异常、恢复、discovery/CLI边界，使独立命令：

```text
coverage report --include=dayu/fins/pipelines/sec_6k_primary_document_repair.py --fail-under=80
```

通过。禁止改生产逻辑只为抬覆盖率，禁止omit/pragma/降低阈值。

### F2 — `accepted`：identity mismatch 被误投影为 COMPANY_NAME_REQUIRED

`resolve_upload_company_meta_decision` 新增的 identity mismatch `ValueError` 会被 `ingestion_runtime.py` 的 blanket `except ValueError` 捕获并投影为 `COMPANY_NAME_REQUIRED`，与真实原因相反，也违反accepted plan的typed failure owner约束。

Required fix：

1. 在 `upload_company_meta.py` 定义专用 `UploadCompanyNameRequiredError(ValueError)`；只有missing/stale create/update需要company name且缺失时由owner抛出。
2. `ingestion_runtime.py`只捕获该typed exception并投影`COMPANY_NAME_REQUIRED`；builder、identity mismatch及其它`ValueError`不得被捕获。
3. owner test覆盖专用异常；runtime test构造strict-valid但incoming canonical不同的CompanyMeta，断言不成为`FinsUploadUsageCode.COMPANY_NAME_REQUIRED`。
4. 不提前实现S2 storage corruption code/route；其它错误先保持非usage failure，S2再完成最终typed corruption投影。

### F3 — `accepted-with-note`：read_runtime 一行机械 consumer迁移

接受 `company_meta.market -> company_meta.ticker_identity.market`。这是删除compat field后通过pyright/运行期所需的最小consumer迁移，未改变read route、fallback、schema或failure projection。S2仍拥有其余read contract切换。

### F4 — `rejected-with-reason`：upload_material help 必须暴露 material producer

现有upload专用help已自足说明：CSV第一项canonical、后续项为用户声明aliases、系统信任且不联网核验、成功保存CompanyMeta后均查询同一归档；该helper只用于三个upload命令，用户查看`upload_material --help`时语境明确。再写“material CompanyMeta producer”会向用户暴露不必要内部实现术语，违反LLM-facing文本约束。现有测试已分别断言三个命令的关键语义，不要求修改。

## Controller-added decisions

- `CompanyMeta.from_dict` 是否要求raw persisted ticker/aliases已是exact canonical：本S1不新增finding。accepted plan明确要求strict类型、grammar、market一致并调用唯一builder；exact raw equality未被冻结。S2在descriptor/meta identity mismatch实现时必须基于最终accepted plan决定，不在S1临时扩大schema。
- grammar负向对照（`AA.SS`、`V.N`、`SHEL`/`SHOP`）不是当前bug证据；可在不扩大生产scope的前提下补owner tests，但不是S1 acceptance blocker。
- 6个回归失败已由controller在隔离的`5508d044` worktree逐项复现，确认是accepted baseline failure；不在本WU修复。

## Kept closed / allowed residual

- 未发现compat shim、material accept-ignore、duplicate grammar owner、legacy CompanyMeta field consumer或旧Fmp constructor。
- S1 `resolve_existing_ticker`、alias-to-list late conflict、snapshot lost-update窗口与read fallback是accepted S2 residual，不在本fix提前处理。
- README仍留到S2，不在S1 checkpoint写半契约。

## S1 fix exit criteria

1. F1/F2实现并有owner tests。
2. focused tests、`tests/fins`回归、全量pyright、residue scans通过。
3. 6-K单文件coverage`>=80%`，所有其它修改生产文件仍`>=80%`。
4. 两路S1 re-review无blocker后才创建accepted S1 local commit，并立即进入S2。
