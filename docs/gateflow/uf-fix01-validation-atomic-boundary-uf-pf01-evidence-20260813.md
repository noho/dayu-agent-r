# UF-FIX01 / UF-PF01 focused-real evidence

## Accepted bundle

- Evidence root：`/Users/leo/workspace/.dayu-cli-ci/uf-pf01-focused-real-20260813-Cxy3YR/final-r3`
- Evidence HEAD：`184c0819c2f14c843f008e99df78ba1e71ecf594`
- Python：`3.11.15`
- CLI package：`dayu-agent 0.1.4`
- Bundle digest：`5e311272dce426a79e841f5963a050d3491cd7f48f9e67c928d30bf76360b350`
- `manifest.json` SHA-256：`66e3d769b51d2dd4685a448f7e35c52092e06be9ba46835525ad356fe7988058`
- `report.md` SHA-256：`6d1fd4e5d56a99ff02387d6a491f9fcc73b73a8f94d3a3afd2c588803d53414a`
- Result：`30/30 PASS`，integrity failures `0`

每个 case 均保存 exact argv、stdout、stderr、exit/duration、before/after tree、durable artifact projection 与 SHA-256 清单。所有调用均为本地真实 `.venv/bin/dayu-cli` subprocess；未使用 mock、fake、monkeypatch 或 fault injection。

## Usage validation matrix

覆盖 `UF-003–UF-006`、`UF-015–UF-019`、`UF-021–UF-024`、`UF-026–UF-028`、`UF-030–UF-038`，共 25 个代表性缺失/空值/非法值/缺失文件/目录冒充文件/后缀 owner 已判无效场景。

全部场景满足：

- exit code 精确为 `2`；
- stderr 与 accepted 具体 reason 精确一致；
- stdout 为空；
- workspace 在调用前不存在，before/after tree 完全一致；
- created/deleted/modified 均为空，确认为真正零新增，未忽略 `.dayu` skeleton。

## Runtime/content classification

`UF-I11`、`UF-I12`、`UF-I13` 使用真实不可解析 PDF/DOCX 输入，全部满足：

- exit code 为 `1`，未被重分类为 usage error；
- stderr 保留 `文件无法解析或已损坏，请检查文件后重试` 与 typed `failure_kind="content"`；
- stderr 有界（代表 case 为 372 bytes），无 `Traceback`、repo root、workspace root 或 calibration input root 泄漏；
- fresh workspace before/after 完全一致。

## Atomic publication

- Fresh create：`UF-ATOMIC-FRESH` 的 corrupt source 失败后 exit `1`，before/after tree 完全一致，company/source business facts 为零。
- Existing update：先由真实 CLI 成功 seed `EXAT` company/source，再用 corrupt source 执行 update；handled failure exit `1`，完整 filesystem diff 为空，且 `business_before == business_after`，所有 company/source durable file SHA 保持不变。

因此 source 未成功发布时，不会出现孤立 company meta、半成品 source 或既有 durable state 的部分刷新；成功 seed 时二者共同可见。

## Harness audit

首次 `final` root 因 evidence runner 将 300 字符非法值误作路径而在 SHA 采集阶段触发 `ENAMETOOLONG`；第二次 `final-r2` root 因 runner 错误假设 typed reason 位于 stdout 而报告 25/30。两者均为 rejected harness run，未删除、未复用、未作为产品结论。修正仅涉及临时 evidence runner 的路径识别与输出通道断言；最终 `final-r3` 从空 root 全量重跑并通过。

## Scope statement

- 本 rerun 只证明 `UF-PF01`。
- 未运行或登记 `UF-PF12` 137 条 full-real matrix。
- 未修改 frozen evidence、accepted oracle 或 `docs/cli_ci_scenarios.json` finding/rerun 状态。
- conformance registry refresh 留待后续统一登记。
