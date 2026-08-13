# UF-FIX01 validation-atomic-boundary final closeout

## Outcome

`UF-FIX01` 已闭环：所有可在业务启动前判定的 filing upload 用户输入错误共享同一 typed validation 真源，并在 workspace/service bootstrap 前以具体、有限、可行动 reason 返回 exit 2；进入业务后的内容/仓储/运行期失败保持 exit 1。company meta 与 source publication 由 `dayu.fins.storage` 同一 batch owner 原子提交，fresh create 与 existing update 的 handled failure 均不留下部分 durable state。

## Local commits

- `5031ec6b` — accepted owner-based implementation plan
- `69bc9d2a` — plan correction
- `3caca6fa` — validation/atomic boundary initial implementation
- `54c867f8` — initial implementation review adjudication
- `5a6d80c2` — atomicity review fixes
- `0391b589` — fix re-review adjudication
- `ef4e4324` — typed prevalidation repository construction fix
- `452258eb` — implementation delta acceptance
- `7ea01244` — focused-real stderr finding
- `b3304eb4` — isolate inherited Docling child stderr
- `2f5ec121` — F1 dual review adjudication
- `8c94312d` — bounded stderr follow-up fixes
- `184c0819` — bounded follow-up dual review acceptance
- `b1064bd9` — UF-PF01 focused-real evidence record
- final review/closeout commit — contains both final `/deepreview` artifacts and this adjudication/closeout

## Verification

- Initial affected suite after core fix：`591 passed`。
- F1 affected suite：`630 passed, 3 warnings`。
- Bounded follow-up affected files：`120 passed, 3 warnings`。
- Final MiMo affected selection：`524 passed, 0 failed`。
- Modified converter owner file coverage：`95%`（目标 ≥80%）。
- Full pyright：`0 errors, 0 warnings, 0 informations`。
- Ruff / `git diff --check` / scope audit：通过。
- README trigger checks：根 README、`dayu/fins/README.md`、`dayu/service/README.md`、`tests/README.md` 已按职责更新；Host/Engine design boundary 未改变。

## Focused-real evidence

- Accepted root：`/Users/leo/workspace/.dayu-cli-ci/uf-pf01-focused-real-20260813-Cxy3YR/final-r3`
- Evidence HEAD：`184c0819c2f14c843f008e99df78ba1e71ecf594`
- Bundle digest：`5e311272dce426a79e841f5963a050d3491cd7f48f9e67c928d30bf76360b350`
- `manifest.json`：`66e3d769b51d2dd4685a448f7e35c52092e06be9ba46835525ad356fe7988058`
- `report.md`：`6d1fd4e5d56a99ff02387d6a491f9fcc73b73a8f94d3a3afd2c588803d53414a`
- Result：30/30 PASS，integrity failures 0；25 usage cases exit 2 + fresh workspace zero mutation；3 content cases、fresh atomic、existing atomic exit 1 且无部分 durable update。
- Rejected harness roots：`final`（SHA input path detection bug）与 `final-r2`（typed reason output-channel assertion bug）均保留但不采纳；没有删除或复用。

## Explicitly not covered

- 未执行或登记 `UF-PF12` 137 条 full-real matrix。
- 未刷新 conformance registry，未修改 frozen evidence、accepted oracle 或 scenario finding/rerun 状态。
- 未处理 UF-FIX02–UF-FIX08、UF-FIX10、UF-FIX11 的明确非目标。
- 未运行仓库全量 pytest；验证为受影响 suite、owner coverage、完整 pyright 与 focused-real CLI evidence。

## Residual risks

- FD2 `dup/dup2/close` 在 macOS Python 3.11 实跑；Windows descriptor 差异留给现有跨平台 CI owner。
- 无主体异常时 exit flush failure 的传播控制流没有单独 owner test；主体异常保护、FD restore/close 与真实 CLI 泄漏路径已有直接覆盖。
- Docling child 的第三方 raw stderr 在 public CLI boundary 被有意丢弃；用户获得 typed actionable reason，父进程 operator cause/closed descriptor 仍保留，但第三方原始 stderr 不作为 durable debug artifact。
- 3 条 edgar dependency deprecation warning 属上游维护范围。

## Local-only compliance

未创建 PR，未 push，未切分支，未更新 main，未创建兼容 shim。
