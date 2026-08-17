# UF-FIX11 aggregate deepreview acceptance

## Gate metadata

- work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- gate：`aggregate deepreview acceptance`
- base：`94182a0c`
- reviewed HEAD：`91dbf843`
- 日期：2026-08-17
- controller verdict：`ACCEPTED AFTER FIX / RE-REVIEW`
- next entry point：accepted deepreview commit

## Review coverage

- 标准 `$deepreview` artifact：`docs/reviews/code-review-20260817-172506.md`
- MiMo state/owner 专项：`docs/reviews/uf-fix11-deepreview-state-owner-mimo-20260817.md`
- DS projection/data-stability 专项：`docs/reviews/uf-fix11-deepreview-projection-ds-20260817.md`
- Controller 复核了两路证据、关键 production diff、真实 SEC/CN → publication/storage → runtime →
  direct/CLI/wait 数据链，并负责最终 severity 与修复裁决。

覆盖范围包含 authoritative company metadata decision、publication-lock final reread、alias union/collision、fresh/stale
metadata、metadata-only skip、atomic commit/rollback、concurrency/cancellation/kill recovery、typed warning parser/codec、
durable summary、direct result、CLI stdout/stderr/exit、wait/LLM-facing projection、README/测试/类型与耦合。

## Finding adjudication

### Finding 01 — fixed and closed

原问题：canonical SKIP executor 只特判 `keep`；若未来 arbitration 与 executor 闭集漂移，非法
`skip/no-intent` 可能越过 stage seam，在 durable commit 后才报错。

修复：`filing_upload_publication.py` 新增唯一私有纯 predicate，完整表达
`keep/no-intent | stage/preserve_published intent`；arbitration 与 executor 共同消费。executor 在任何
repository stage/commit 前拒绝闭集外组合，outer lifecycle 恰好 rollback 一次。

### Finding 02 — fixed and closed

初次 fix test 用 `object.__setattr__` 修改 frozen fresh request。DS re-review 指出该 decision 可由 typed
`dataclasses.replace` 合法构造，强制 setattr 会绕过未来 owner invariant。

修复：测试 validator wrapper 先调用真实 `validate_fins_upload_filing_request`，再用 `replace` 构造带合法
`skip/no-intent` decision 的新 frozen request；arbitration helper 只返回 SKIP，不再 mutation request。生产 diff
保持逐字不变。

## Re-review decisions

- MiMo 初次 fix re-review：`PASS`；
- DS 初次 fix re-review：finding 01 `PASS`，提出 finding 02（低）；
- MiMo finding 02 final re-review：`PASS`；
- DS finding 02 final re-review：`PASS`；
- 最终状态：finding 01/02 全部关闭，无新 finding、无 blocking open question。

Artifacts：

- `docs/gateflow/uf-fix11-deepreview-fix-20260817.md`
- `docs/reviews/uf-fix11-deepreview-fix-rereview-mimo-20260817.md`
- `docs/reviews/uf-fix11-deepreview-fix-rereview-ds-20260817.md`
- `docs/reviews/uf-fix11-deepreview-fix-rereview-final-mimo-20260817.md`
- `docs/reviews/uf-fix11-deepreview-fix-rereview-final-ds-20260817.md`

## Validation accepted

- finding 01 修复前红测：`1 failed`，证明旧 executor 未在 mutation 前拒绝非法组合；
- 最小合法/非法状态组：`5 passed`；
- publication owner file：`41 passed`；
- combined regression：`2158 passed, 1 skipped, 3 warnings`；
- modified production file branch coverage：84%；
- full pyright：`0 errors, 0 warnings, 0 informations`；
- Ruff：通过；
- `git diff --check`：通过；
- warning owner/projection、SEC/CN、storage、runtime、README、Host/Engine 与 frozen docs：除 accepted work-unit
  commits 外，本 fix 无额外 diff；
- 未执行真实 CLI/network/calibration/frozen evidence，符合明确非目标。

## README decision

已读取 `dayu/fins/README.md` 与 `tests/README.md` 更新约束。deepreview fix 只把已有 canonical skip invariant
前移到 executor mutation boundary，并清理测试注入 seam；不改变公共行为、架构、命令、schema 或测试层级，故无需
追加 README 修改。

## Residual risk classification

- fixed in current slice：canonical SKIP 远端不变量依赖；测试 frozen-owner 绕过；
- assigned to later work unit：mutable `UploadOperationResult.file_events`、resolver version 人工同步 bump、material
  upload 同类名称行为、name-only metadata-only physical swap 成本、post-commit cleanup 可见性、真实
  CLI/network/scenario evidence；
- blocking 或未分类 residual risk：无。

## Gate decision

Aggregate deepreview loop 已通过。所有 accepted findings 均已修复并经 MiMo/DS 双路 re-review 关闭，可以创建
accepted deepreview commit。
