# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S1 Code Review Fix

## Artifact Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-C`
- Slice: `S1 Storage Identity, Commit Point, And Local Durability`
- Gate: `code review fix`
- Fix owner: `AgentCodex`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-code-review-controller-adjudication.md`
- Status: `pass`
- Commit authorization: none；本轮未创建commit。

## Scope

本fix只处理controller accepted的`R3-C-S1-CR-F01`和`R3-C-S1-CR-F02`：

- 修改`dayu/fins/storage/_fs_storage_infra.py`的directory replace owner guard；
- 修改`tests/fins/test_fins_storage_atomicity.py`补齐两个owner-level测试簇；
- 写入本fix artifact。

未修改S2/S3、upload/download workflow、Host/Service wait adapter、README、design/control docs或其它production module。

## Finding Status

### R3-C-S1-CR-F01 — 已修复

- `_replace_directory(source, target)`在`os.replace()`前检查`target.exists() or target.is_symlink()`。
- 普通已存在target和broken symlink target都以`OSError` fail closed；不依赖不同平台对existing directory replace的行为。
- 新增参数化owner-level测试，分别构造existing directory与broken symlink，断言：
  - 抛出`OSError`；
  - source目录及内容保持不变；
  - existing target目录内容保持不变；
  - broken symlink仍存在且link target未改变。

### R3-C-S1-CR-F02 — 已修复

- 测试显式导入`_normalize_object_key`。
- 新增合法参数化测试，直接断言多组件key逐组件trim并保持dot/hyphen合法内容。
- 新增非法参数化测试，直接覆盖empty/whitespace、leading slash、empty segment、`.`/`..` segment、backslash和Windows drive表达。
- 既有`LocalFileStore`间接测试继续保留，owner helper与consumer两层contract均有覆盖。

## Validation

### Focused tests

```bash
source .venv/bin/activate
pytest tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py -q
```

结果：`130 passed, 3 warnings`。warnings均来自既有`edgar` deprecated modules，与本fix无关。

### Type check

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

### Whitespace check

```bash
git diff --check
```

结果：pass，无输出。

## README Decision

不更新README。本fix没有新增测试层级、运行方式、用户可见行为或跨层装配事实；R3-C accepted plan的PF-09仍要求README/current-fact同步等待S1 -> S2 -> S3全部production slices落地后统一执行。

## Tool-Security Exclusion

本fix未实现或扩展以下任何工具安全项：

- upload allowlist / explicit file authority / symlink-safe upload source policy；
- URL / TLS / redirect / SSRF provenance policy；
- remote download byte-budget policy；
- LLM-facing security prompt、tool schema或result schema变化。

broken symlink target guard只保护storage owner内部directory replace前置条件；既有`local://` containment仍只表达storage identity，不投影为upload source authority或远端egress policy。

## Residual Risks

| Risk | Classification | Owner / destination |
| --- | --- | --- |
| directory target check与`os.replace()`之间理论TOCTOU | covered by current S1 owner/lock contract | `_replace_directory`只在持有ticker batch/recovery lock的storage owner内部调用；不把该guard解释为外部安全授权边界 |
| upload/download caller mutation atomicity | covered by later approved slice | mandatory R3-C S2 |
| Fins -> Host import relocation | covered by later approved slice | mandatory R3-C S3 |
| 四类tool-security findings | assigned to later work unit | dedicated tool-security / remote-egress WU |

无未分类residual risk。

## Fix Gate Decision

- status: `pass`
- `R3-C-S1-CR-F01`: `已修复`
- `R3-C-S1-CR-F02`: `已修复`
- remaining accepted findings: `0`
- blocking questions: `0`
- next entry point: R3-C S1 code review re-review
- artifact path: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-code-review-fix-codex.md`
- 本artifact不授权commit；按用户要求停在fix报告。
