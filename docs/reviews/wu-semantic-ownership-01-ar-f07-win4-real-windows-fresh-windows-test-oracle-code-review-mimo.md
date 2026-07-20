# Code Review — AR-F07 WIN4-RW-RF01 第一路 AgentMiMo 完整 Immutable Review

## Review Identity

- **Reviewer**: AgentMiMo
- **Review type**: WU-SEMANTIC-OWNERSHIP-01 最后一个内部 remediation sub-WU AR-F07 WIN4-RW-RF01 第一路完整 immutable code review
- **Mechanical base**: `39926eb85aa25441f5209a128a3c971f451b5b25`
- **Code path**: `tests/cli/test_upload_filings_from_command.py`
- **Exact function**: `test_windows_generated_script_runs_real_cli_into_temp_storage`
- **Agent artifact SHA**: `f9b36d4b58d4a81c845058790f6d99d8b7994b8a35410a79242aed606163f42e` ✓ 已验证
- **Controller validation SHA**: `382fbf2f4a16ee1a3492b5d712212372820e2599b0595ab72b6ab6a38378e672` ✓ 已验证
- **Review timestamp**: 2026-07-20T09:52:29+08:00

## Scope

- **Mode**: Current Changes
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `39926eb85aa25441f5209a128a3c971f451b5b25` (frozen mechanical base)
- **Output file**: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-test-oracle-code-review-mimo.md`
- **Included scope**: 仅 `tests/cli/test_upload_filings_from_command.py` 中 `test_windows_generated_script_runs_real_cli_into_temp_storage` 函数的 snapshot 断言块（行 1003-1017）
- **Excluded scope**: 所有其他文件、函数、import、helper、schema、oracle、README、workflow、product 路径
- **Parallel review coverage**: 无（单一函数块变更，无需 subagent）

## Diff Summary

**文件**: `tests/cli/test_upload_filings_from_command.py`
**变更量**: 14 insertions / 3 deletions，单一 hunk `@@ -1000, +1000,21 @@`

**删除**（base commit 行 1003-1006）:
```python
assert snapshot.primary_filename == source_path.name
assert snapshot.primary_filename in tuple(
    descriptor.name for descriptor in descriptors
)
```

**插入**（working tree 行 1003-1017）:
```python
primary_descriptors = tuple(
    descriptor
    for descriptor in descriptors
    if descriptor.name == snapshot.primary_filename
)
assert len(primary_descriptors) == 1
raw_source_descriptors = tuple(
    descriptor
    for descriptor in descriptors
    if descriptor.name == source_path.name
)
assert len(raw_source_descriptors) == 1
raw_source_descriptor = raw_source_descriptors[0]
assert raw_source_descriptor.sha256 is not None
assert raw_source_descriptor.sha256 == hashlib.sha256(fixture).hexdigest()
```

**代码 diff SHA-256（冻结命令）**: `fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169`

冻结命令: `LC_ALL=C git diff --binary --full-index --no-ext-diff --no-renames 39926eb85aa25441f5209a128a3c971f451b5b25 -- tests/cli/test_upload_filings_from_command.py | shasum -a 256`

> 注: 简单 `git diff | sha256` 输出 `f4dd51eb...`，是不同序列化格式的不同 identity command，非 mismatch。

## Findings

未发现实质性问题。

## Adversarial Analysis（逐条对照）

### 1. primary exact-name 与 raw-source exact name 是否真正独立、exact-one、optional hash fail-closed

**结论: 通过。**

- `primary_descriptors` 按 `descriptor.name == snapshot.primary_filename` 过滤，`raw_source_descriptors` 按 `descriptor.name == source_path.name` 过滤。两个过滤器使用不同 key，完全独立。
- 两个断言均要求 `len(...) == 1`：zero hit → 失败；duplicate → 失败。exact-one 语义正确。
- `sha256` 字段类型为 `Optional[str]`（`repository_protocols.py:65`）。断言先检查 `is not None`，再比较值。若 `sha256` 为 `None`，断言立即失败，fail-closed。
- 两个事实（primary 属于 descriptors、raw-source 属于 descriptors 且 hash 匹配）不要求 primary == raw-source，也不禁止。正确解耦。

### 2. duplicate descriptor names、zero hit、primary!=raw 合法反例

**结论: 通过。**

- **Duplicate descriptor names**: 若 `descriptors` 中有两个同名文件，`len(...) == 1` 断言失败。测试正确拒绝重复描述符。
- **Zero hit**: 若 primary 或 raw-source 不在 descriptors 中，`len(...) == 0` 断言失败。测试正确拒绝缺失描述符。
- **primary != raw 合法反例**: Fins 层可选择 Docling JSON 作为 primary，而 raw-source 是原始 HTML。新断言不要求两者相等，允许这种合法场景。旧断言 `snapshot.primary_filename == source_path.name` 错误禁止了这种场景。修复正确。

### 3. 是否仍有 test 越权选择 Fins primary、hardcoded Docling/private meta/rglob business oracle

**结论: 通过。**

- **越权选择 Fins primary**: 测试从 `snapshot.primary_filename` 读取 primary，不硬编码任何期望值。Fins 层决定 primary 是谁，测试只验证 primary 存在于 descriptors 中。
- **Hardcoded Docling**: 新断言中无任何 Docling 文件名（如 `.json` 后缀、`docling` 字符串）。
- **Private meta**: 断言仅消费 `SourceSnapshotFileDescriptor.name` 和 `sha256`，均为公共协议字段。不读取 `source_meta`、`provenance`、`revision` 或任何 storage 私有字段。
- **Rglob business oracle**: 断言块内无 `rglob`。函数末尾的 `source_artifacts = tuple(path for path in (storage / "portfolio").rglob("*") ...)` 是物理产物检查，不在本次变更范围内，且不涉及业务语义判断。

### 4. exact function-block allowlist、无 import/helper/schema/oracle/README/workflow/product 扩张

**结论: 通过。**

- **Exact function-block**: diff 唯一 hunk 位于 `test_windows_generated_script_runs_real_cli_into_temp_storage` 函数内（行 1003-1017）。无其他函数修改。
- **Import**: `hashlib` 已在文件头部导入（行 6），无新增 import。
- **Helper/schema/oracle/README/workflow/product**: 无任何新增。变更完全自包含于断言块内。

### 5. 测试/pyright/Ruff evidence 是否足够且真实 Windows 仍 pending

**结论: 通过（有 residual risk）。**

- **测试**: Controller validation 报告 target file 20 passed / 2 skipped，full CLI 552 passed / 7 skipped，aggregate 262 passed / 2 skipped。断言逻辑在 macOS 上通过 `@pytest.mark.skipif(os.name != "nt", ...)` 跳过，但代码路径的语法和语义已被 pyright 和其他测试覆盖。
- **Pyright**: 0 errors, 0 warnings, 0 informations。
- **Ruff**: scoped checks passed。
- **真实 Windows**: 仍 pending。macOS 无法执行 `cmd.exe`，Windows exact node 显示 `PLATFORM SKIP`。真实 Windows 验证需在 accepted implementation commit 后通过 fresh R11/R12 workflow 执行。

### 6. 安全边界、trusted-local secret 裁决、Tool Trace/audit 明文禁止、deferred Issue 范围不漂移

**结论: 通过。**

- **安全边界**: 断言仅比较 hash 值（单向摘要），不暴露文件内容。无 secret 泄露风险。
- **Trusted-local secret**: 测试使用本地 fixture 文件，不涉及 secret。
- **Tool Trace/audit 明文**: 断言不写入任何 trace 或 audit 内容。
- **Deferred Issue 范围**: 仅 deferred "真实 Windows 验证"，范围不漂移。

### 7. correctness/stability/maintainability、semantic ownership drift、adversarial failure pass

**结论: 通过。**

- **Correctness**: 新断言正确实现了 "primary 存在于 descriptors 且唯一" 和 "raw-source 存在于 descriptors 且唯一且 hash 匹配" 两个独立事实。旧断言错误地将两个事实强制相等。
- **Stability**: 断言对 duplicate/zero-hit/hash-mismatch 均 fail-closed，不会静默通过。
- **Maintainability**: 代码清晰，意图明确，无隐藏依赖。
- **Semantic ownership drift**: 旧断言是典型的 semantic ownership drift——测试层越权强制 Fins 层的 primary == raw-source。新断言正确收敛回 Fins 层的 contract：primary 由 Fins 决定，raw-source 由 storage 证明。无 fallback、特例、`hasattr`/`getattr`、loose parsing 或兼容 shim。
- **Adversarial failure pass**:
  - `primary_filename` 不在 descriptors 中 → `len == 0` 失败 ✓
  - `source_path.name` 不在 descriptors 中 → `len == 0` 失败 ✓
  - `sha256` 为 `None` → `is not None` 失败 ✓
  - `sha256` 值不匹配 → 等值比较失败 ✓
  - descriptors 为空 → 已被 `assert descriptors` 拦截 ✓
  - primary 和 raw-source 是同一文件 → 两个过滤器各命中同一 descriptor，`len == 1` 通过 ✓
  - primary 和 raw-source 是不同文件 → 两个过滤器各命中不同 descriptor，`len == 1` 通过 ✓

## Open Questions

无。

## Residual Risk

1. **真实 Windows 验证 pending**: macOS 无法执行 `cmd.exe`，Windows exact node 显示 `PLATFORM SKIP`。真实 Windows 验证需在 accepted implementation commit 后通过 fresh R11/R12 workflow 执行。若 R11/R12 在 primary membership 或 raw-source name/hash 上失败，diagnostic-first stop gate 要求返回 Controller 而非回退到旧断言。

## Non-Finding / No-Action

- **POSIX 测试不对称**: 兄弟测试 `test_posix_generated_script_runs_real_cli_into_temp_storage`（行 792）不包含 snapshot/descriptor 断言。这是 pre-existing 且 out-of-scope，非本次变更引入，不构成 finding 或 residual risk。

## Verdict

**PASS**

- **Blocker**: 0
- **Open**: 0
- **Backflow**: 0
- **Finding**: 0

## Correct Next Gate

Controller adjudication → AgentCodex 修复所有 accepted findings（即使 0 也要 zero-change fix record）→ 双路完整 re-review → accepted implementation commit → fresh R11/R12 workflow 执行真实 Windows 验证。
