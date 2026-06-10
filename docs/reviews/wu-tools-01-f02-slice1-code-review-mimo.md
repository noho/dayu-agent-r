# WU-TOOLS-01-F02 Slice 1 Code Review

## 元数据

- Work unit：`WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- Gate：`code review`
- Slice：`Slice 1 Static OLD Pipeline Assets`
- Reviewer：MiMo
- 日期：2026-06-09
- Artifact path：`docs/reviews/wu-tools-01-f02-slice1-code-review-mimo.md`

## 审查文件

| 文件 | 类型 | 状态 |
|---|---|---|
| `utils/diag_web.sh` | shell wrapper (single URL) | 新增 |
| `utils/diag_web_batch.sh` | shell wrapper (batch) | 新增 |
| `utils/web_ci_urls.jsonl` | URL corpus (JSONL) | 新增 |
| `docs/reviews/wu-tools-01-f02-slice1-implementation-codex.md` | implementation artifact | 新增 |

## Verdict

**pass-with-findings**

1 finding，non-blocking，不阻塞 next gate。

## Findings

### F-1 [minor] Shell wrapper 使用 OLD CLI flag 名称

**位置**：`utils/diag_web.sh:19`，`utils/diag_web_batch.sh:19`

**描述**：两个 wrapper 使用 `--channel chrome`，但 accepted plan 的 config table 定义的 CLI flag 名称为 `--playwright-channel`。同理，`--headed` 与 `--manual-wait-seconds` 未出现在 plan 的 config table 中。

**证据**：

- Plan config table 将 `playwright_channel` 映射为 `--playwright-channel`。
- Shell wrappers 使用 OLD flag name `--channel`。
- Implementation artifact residual risks 已记录该 gap："Wrapper option compatibility depends on Slice 2 preserving or mapping OLD CLI flags such as `--channel`, `--headed`, `--manual-wait-seconds` and `--storage-state-dir`。"

**评估**：Shell wrappers 是 opt-in developer utility，不是 CI contract。OLD flag names 来自 OLD pipeline 迁移，implementation artifact 已如实记录该 handoff risk。Slice 2 implementation 负责决定是否保留 OLD flag names 作为 aliases 或迁移到 plan 定义的新 names。当前 slice 不阻塞。

**裁决建议**：`deferred-with-owner` → WU-TOOLS-01-F02 Slice 2。Slice 2 CLI parser 设计时必须决定 OLD flag compatibility 策略。

## Validation Evidence

### 1. Shell 语法验证

```bash
bash -n utils/diag_web.sh utils/diag_web_batch.sh
```

结果：通过，无输出。

### 2. JSONL 格式与结构验证

```bash
python -c 'import json, pathlib; ...'
```

结果：
- 60 rows，全部有效 JSON
- 所有记录字段一致：`{url, label, region, category, notes}`
- Region 分布：foreign 30, china 30
- Category 分布：news 20, finance 20, government 20
- 无非法 JSONL 行

### 3. OLD vs NEW corpus diff

```bash
diff -u /Users/leo/workspace/dayu-agent/utils/web_ci_urls.jsonl utils/web_ci_urls.jsonl
```

结果：仅末尾换行符差异（OLD 无 trailing newline，NEW 有）。JSONL record 内容完全一致。

### 4. 文件权限

```
-rwxr-xr-x utils/diag_web.sh
-rwxr-xr-x utils/diag_web_batch.sh
-rw-r--r-- utils/web_ci_urls.jsonl
```

Shell wrappers 具有 executable bit（正确）。JSONL 数据文件无 executable bit（正确）。

### 5. Scope 合规性

| 检查项 | 结果 |
|---|---|
| 仅修改 Slice 1 allowed files | 通过 |
| 未跨入 Slice 2（未新增 `diagnose_web_access.py`） | 通过 |
| 未新增 CI workflow | 通过 |
| 未修改 Host / Engine / Service / UI / production Web tools | 通过 |
| 未修改 controller artifacts | 通过 |
| 未运行 live diagnostics | 通过 |

### 6. Shell wrapper 行为审查

| 检查项 | `diag_web.sh` | `diag_web_batch.sh` |
|---|---|---|
| shebang | `#!/usr/bin/env bash` | `#!/usr/bin/env bash` |
| `set -euo pipefail` | 是 | 是 |
| 位置参数校验 | `${1:?用法: ...}` | `${1:?用法: ...}` |
| `$shift` after positional | 是 | 是 |
| 输出目录 `mkdir -p` | 是 | 是 |
| 默认输出根目录 | `workspace/output/web_diagnostics` | `workspace/output/web_diagnostics` |
| `"$@"` 传递 extra args | 是 | 是 |
| 不进入默认 CI | 是（手工 opt-in 脚本） | 是（手工 opt-in 脚本） |
| 不意外触发 live/browser | 否（需 `python -m` 存在才执行） | 否（需 `python -m` 存在才执行） |

### 7. `python -m utils.diagnose_web_access` 调用正确性

- Single wrapper：`--url "${URL}"` → 正确调用单 URL 模式
- Batch wrapper：`--url-file "${URL_FILE}"` → 正确调用批量模式，不误把 URL file 当单 URL

### 8. Implementation artifact 诚实性

| 检查项 | 结果 |
|---|---|
| 如实记录 validation 命令与结果 | 通过 |
| 如实记录 residual risks（OLD flag gap、python module 不存在、未 live test） | 通过 |
| 如实记录 docs decision（未更新 README） | 通过 |
| 如实记录 scope boundary（Slice 1 only） | 通过 |

### 9. AGENTS.md / Plan 合规性

| 检查项 | 结果 |
|---|---|
| 不违反 AGENTS.md 架构硬约束 | 通过（`utils/` 脚本，非分层代码） |
| 不违反 AGENTS.md 编码硬约束 | 通过（shell 脚本，不适用 Python docstring/类型约束） |
| 不违反 F02 非目标 | 通过 |
| 不违反 accepted plan scope | 通过 |
| `utils/` 脚本无需测试/覆盖率（AGENTS.md） | 通过 |

## Residual Risks

| 风险 | 分类 | Owner / Destination |
|---|---|---|
| `python -m utils.diagnose_web_access` 尚不存在，wrapper 运行时会失败 | expected slice gap | WU-TOOLS-01-F02 Slice 2 |
| OLD CLI flags (`--channel`, `--headed`, `--manual-wait-seconds`) 与 plan config table 不完全一致 | deferred finding | WU-TOOLS-01-F02 Slice 2 |
| URL corpus 未经过 live network/browser 验证 | non-goal | Slice 2/F03 manual opt-in |

## Recommendation for Next Gate

Slice 1 通过 code review gate。建议进入 **Slice 2 implementation**，重点：

1. CLI parser 设计需决定 OLD flag compatibility 策略（保留 aliases 或迁移到 plan config table names）。
2. `utils/diagnose_web_access.py` 必须实现 `--url` / `--url-file` / `--headed` / `--channel` / `--manual-wait-seconds` / `--storage-state-dir` / `--output` / `--batch-output-dir` 参数，至少保留 wrapper 使用的全部 flags。
3. 注意 `utils/` 目录缺少 `__init__.py`；`python -m utils.diagnose_web_access` 需要 `utils/__init__.py` 或等价 package setup 才能运行。
