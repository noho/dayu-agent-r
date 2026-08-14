# WU upload-filing ticker alias contract — S1 re-review controller adjudication

## Gate

- Gate: S1 re-review
- Accepted plan base: `5508d0445bd1d649fee54f4ec3d65f99e2484493`
- Review artifacts:
  - `docs/reviews/code-review-20260815-002510.md`
  - `docs/reviews/code-review-20260815-002952.md`
- Decision: **PASS / accept S1**

## Controller adjudication

两路独立 reviewer 均基于当前生产 diff、owner contract 测试和独立验证给出 PASS，未报告 blocker。Controller 复核后接受以下结论：

1. F1 已关闭：`sec_6k_primary_document_repair.py` 的单文件 branch coverage 为 91%，高于 80% 门槛；新增测试覆盖 public discovery、输入 fail-closed、过滤器稳定归一化和 batch rollback，未修改生产逻辑以规避覆盖率要求。
2. F2 已关闭：`UploadCompanyNameRequiredError` 只由缺公司名 owner 抛出，`ingestion_runtime.py` 仅捕获该类型；identity mismatch 与 alias builder 的 `ValueError` 不再被错误投影为 `COMPANY_NAME_REQUIRED`。
3. F3 维持 accepted-with-note：`read_runtime.py` 仅做 `CompanyMeta.ticker_identity.market` 的机械 consumer 迁移；read route、typed corruption 与最终查询投影仍由 S2 收口。
4. F4 维持 rejected-with-reason：现有 upload ticker help 已自足表达 CSV 第一项 canonical、后续项为用户声明 alias、系统信任且不联网核验；不加入内部 producer 术语。
5. Scope containment 通过：未提前实现 S2 commit intent、workspace identity lock、unique alias route 或 typed corruption；未触碰 UF-PF05、oracle/scenario registry、冻结 evidence 或其它 finding。

## Verification evidence

- Focused regression: `1674 passed, 2 skipped, 1 deselected`；被 deselect 项属于已隔离基线失败。
- `tests/fins`: `1538 passed, 1 skipped`。
- Full coverage regression: `3547 passed, 9 skipped, 6 failed`；6 项均与 controller 在 accepted-plan 基线隔离复现的清单一致，未出现新增失败。
- 18 个实际修改生产文件逐文件 branch coverage 均 `>=80%`，最低为 `_fs_storage_utils.py: 81%`。
- `python -m pyright dayu/ tests/ utils/`: `0 errors, 0 warnings, 0 informations`。
- `git diff --check`: 通过。

## Residual risk routing

- S1 的 snapshot/lost-update 窗口、late alias conflict、`resolve_existing_ticker` 半契约和 read fallback 均为 accepted plan 明确列出的 S2 强制工作，不允许在 S1 状态部署或完成 work unit。
- S2 引入 typed corruption 后，必须复核 upload tool 边界既有 `except ValueError`，避免把 identity corruption 投影成普通 `invalid_argument`。
- 6 个基线失败不属于本 work unit，不在本次修复。

## Next gate

创建 accepted S1 local commit，然后进入 S2 implementation。S2 未通过 implementation review 前不得进入 aggregate deep review。
