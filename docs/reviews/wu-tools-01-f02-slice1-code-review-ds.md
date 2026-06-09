# WU-TOOLS-01-F02 Slice 1 Code Review

## 元数据

- Work unit：`WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- Gate：`code review`
- Slice：`Slice 1 Static OLD Pipeline Assets`
- Reviewer：DeepSeek
- Date：2026-06-09
- Artifact path：`docs/reviews/wu-tools-01-f02-slice1-code-review-ds.md`
- Plan reference：`docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`
- Implementation artifact：`docs/reviews/wu-tools-01-f02-slice1-implementation-codex.md`
- Reviewed files：
  - `utils/diag_web.sh`
  - `utils/diag_web_batch.sh`
  - `utils/web_ci_urls.jsonl`

## Verdict

**pass-with-findings**（2 findings，其中 1 个需在 Slice 2 启动前裁决）

非 blocking：findings 均属 Slice 2 handoff 接口对齐问题，不阻塞 Slice 1 完成状态。

---

## Findings

### Finding 1 — Wrapper flags 与 accepted plan 的 Slice 2 CLI specification 不一致

**Severity**：Medium
**Classification**：需要 Controller 在 Slice 2 启动前裁决
**Files**：`utils/diag_web.sh:15-22`、`utils/diag_web_batch.sh:16-22`

**Evidence**：

两个 wrapper 向 `python -m utils.diagnose_web_access` 传递了以下默认 flag：

| Wrapper 使用的 flag | Accepted plan 对应 CLI flag | 匹配？ |
|---|---|---|
| `--channel chrome` | `--playwright-channel <channel>` | 不匹配 |
| `--headed` | 未在 plan CLI flag table 中定义 | 不匹配 |
| `--manual-wait-seconds 30` | 未在 plan CLI flag table 中定义 | 不匹配 |
| `--storage-state-dir` | `--storage-state-dir <path>` | 匹配 |

Accepted plan 的 `实现决策 1` 中明确将 CLI flag 定义为 `--playwright-channel`，且未定义 `--headed` 或 `--manual-wait-seconds`。Plan 仅在决策 3 中定性描述 "Shell wrapper 可以默认 headed browser"，但未将其映射为具体的 CLI flag。

**Impact**：若 Slice 2 严格按 accepted plan 实现 argparse interface，则当前 wrapper 传递的 `--channel`、`--headed`、`--manual-wait-seconds` 将被 Python 模块当作无法识别的参数而报错，导致 wrapper 不可用。

**裁决选项**（任选其一）：
- **Option A**：Slice 2 实现时同时接受 plan-specified flag 和 wrapper 传递的 flag（alias），并在 Slice 2 implementation artifact 中记录该偏差。
- **Option B**：Slice 2 启动时先将 wrapper 的默认 flag 修正为 plan-specified flag（`--channel` → `--playwright-channel`；移除或重命名 `--headed`、`--manual-wait-seconds`）。
- **Option C**：Controller 裁定更新 accepted plan 的 CLI flag table，使 plan 与 wrapper 一致。

**Why not blocking Slice 1**：Slice 1 的正确性验证为 `bash -n` 通过即可；wrapper 在 Python 模块不存在时尚无法端到端运行，该 gap 已在 implementation artifact 中明确记录为 "expected slice gap"。Finding 实质是 Slice 1 到 Slice 2 的接口契约未对齐，应在 Slice 2 启动前裁决。

---

### Finding 2 — 相对输出路径依赖 CWD

**Severity**：Low
**Classification**：accepted 或 informational
**Files**：`utils/diag_web.sh:7`、`utils/diag_web_batch.sh:7`

**Evidence**：两个 wrapper 均使用 `OUTPUT_ROOT="workspace/output/web_diagnostics"` 相对路径。脚本行为依赖调用者从 repo 根目录执行。若从 `utils/` 或其他目录执行，输出将写入错误位置。

**Mitigation**：`utils/` 脚本按约定从 repo 根目录执行，这是项目中 `utils/` 目录的惯例。Plan 中 Slice 1 allowed changes 明确要求 "默认输出根目录使用 `workspace/output/web_diagnostics`"，当前实现符合此要求。

**建议**：可接受。如需加固，可在 wrapper 中增加 `cd "$(dirname "$0")/.."` 或使用 `$SCRIPT_DIR/../workspace/...` 解析，但这属于增强而非 Slice 1 必需。

---

## Validation Evidence

### Shell syntax check

```bash
bash -n utils/diag_web.sh utils/diag_web_batch.sh
```
**Result**：passed，无输出，exit code 0。

### JSONL corpus validation

```bash
python3 -c '
import json, pathlib
p = pathlib.Path("utils/web_ci_urls.jsonl")
rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
'
```
**Result**：
- 60 rows，全部为合法 JSON
- 所有 row 字段集一致：`{"url", "label", "region", "category", "notes"}`
- 60 unique URLs
- Regions：`foreign`、`china`
- Categories：`news`、`finance`、`government`
- 文件末尾有换行符
- 覆盖 foreign/china 的 news、finance、government、regulator、exchange 代表性站点，符合 plan 中描述的 OLD corpus 覆盖范围

### Executable bits

```
-rwxr-xr-x utils/diag_web.sh
-rwxr-xr-x utils/diag_web_batch.sh
```
两个 wrapper 均有可执行权限。

### Whitespace check

```bash
git diff --check
```
**Result**：passed，无输出。

### Scope discipline

- Modified files 仅限 Slice 1 allowed files：`utils/diag_web.sh`、`utils/diag_web_batch.sh`、`utils/web_ci_urls.jsonl`
- `docs/host/issues-implementation-control.md` 的 `M` 状态为 pre-existing，非本 Slice 引入
- 未新增 CI workflow
- 未修改 tests/、README、production Web tools、Host、Engine、Service、UI 或 controller artifacts
- 未运行 live diagnostics

### Shell wrapper safety review

| 检查项 | `diag_web.sh` | `diag_web_batch.sh` |
|---|---|---|
| Shebang (`#!/usr/bin/env bash`) | 通过 | 通过 |
| `set -euo pipefail` | 通过 | 通过 |
| 必需参数校验 (`"${1:?...}"`) | 通过 | 通过 |
| `"$@"` extra args override | 通过（置于默认 flag 之后） | 通过 |
| 变量引号保护 | 通过 | 通过 |
| `mkdir -p` 预创建输出目录 | 通过 | 通过 |
| Timestamp 防碰撞输出路径 | 通过 | 通过 |
| 无 `eval`/`source` 不可信输入 | 通过 | 通过 |
| 手工 opt-in 注释 | 通过 | 通过 |
| 不会进入默认 CI/test | 通过 | 通过 |

### Semantics check

- `diag_web.sh` 使用 `--url` + `--output`，batch wrapper 使用 `--url-file` + `--batch-output-dir`：正确区分单 URL 与批量模式
- Batch wrapper 接收 `URL_FILE` 参数并传递给 `--url-file`，不误当成单 URL
- 两个 wrapper 的默认参数均在 `"$@"` 之前，允许手工运行者追加参数覆盖
- `--storage-state-dir` 指向 `workspace/output/web_diagnostics/storage_states`，与输出根目录共存，不污染 repo 其他区域

---

## Residual Risks

| Risk | Status | Destination |
|---|---|---|
| Wrapper flags 与 plan Slice 2 CLI 不一致 | Finding 1，需裁决 | Slice 2 启动前 |
| `python -m utils.diagnose_web_access` 尚不可运行 | expected slice gap | Slice 2 |
| URL corpus 未对 live network 验证 | non-goal (Slice 1) | F02 Slice 2/3 manual opt-in |
| 相对路径依赖 CWD | accepted (Finding 2) | 可后续加固 |

无 unclassified residual risk。

---

## Recommendation for Next Gate

Slice 1 **code review gate passed**。Recommendation：

1. **Controller 裁决 Finding 1**：在 Slice 2 implementation 启动前，选择 Option A / B / C 解决 wrapper flags 与 plan CLI specification 的不一致。
2. Slice 2 可开始，但 Slice 2 implementer 必须在实现 CLI parser 时按裁决结果处理 flag 命名。
3. Slice 2 验证命令中应包含 `python -m py_compile utils/diagnose_web_access.py` 和 wrapper 语法复查。
4. Finding 2 为 informational，不强制处理。
