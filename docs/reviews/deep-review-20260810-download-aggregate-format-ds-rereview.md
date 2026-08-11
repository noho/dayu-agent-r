# Deep Review Format Rereview — `dayu-cli download` Aggregate (WU-CLI-DOWNLOAD-01)

## Gate 状态

- **Reviewer**: AgentDS（独立 format rereview）。
- **基线**: `f0381f6aa366623590937e5667ddf7f535f7dd01`（当前 HEAD，aggregate fix closeout）。
- **范围**: 基线上未提交的五文件 Ruff formatter diff。
- **日期**: 2026-08-10。
- **参照**: format closeout artifact（`docs/gateflow/wu-cli-download-01-aggregate-format-closeout-20260810.md`）。
- **结论**: **PASS** — 0 findings。

---

## 1. 范围确认

`git diff HEAD --stat`：

```
dayu/cli/arg_parsing.py                     | 32 ++++-----------
dayu/fins/pipelines/cn_form_utils.py        | 16 ++------
dayu/fins/pipelines/sec_rebuild_workflow.py | 25 ++++++------
tests/fins/test_fins_ingestion_tools.py     | 60 +++++++----------------------
tests/service/test_fins_direct.py           | 26 +++----------
5 files changed, 43 insertions(+), 116 deletions(-)
```

与 format closeout 声明的五文件范围一致。无其它产品或测试文件进入工作树。未修改既有 artifact、Oracle、scenario registry；未运行真实 CLI/provider。

---

## 2. 独立 AST 等价性验证

对五个文件分别读取 `git show HEAD:<path>` 与当前 working-tree bytes，使用 `ast.parse(type_comments=True)` → `ast.dump(include_attributes=False)` 进行严格相等比较：

```
dayu/cli/arg_parsing.py:                     AST_EQUIVALENT=true
dayu/fins/pipelines/cn_form_utils.py:        AST_EQUIVALENT=true
dayu/fins/pipelines/sec_rebuild_workflow.py: AST_EQUIVALENT=true
tests/fins/test_fins_ingestion_tools.py:     AST_EQUIVALENT=true
tests/service/test_fins_direct.py:           AST_EQUIVALENT=true
```

五文件 `f0381f6a` 与当前 working tree 的 Python AST 完全相同。

### 2.1 逐 hunk 人工分类

完整 `git diff HEAD` 人工逐 hunk 核验。变化严格属于 Ruff formatter 括号/换行/缩进布局调整，不涉及：

- identifier 重命名
- literal value 变更
- operator 变更
- 调用顺序或参数名变更
- 控制流重构
- docstring 或注释语义变更
- import 新增/删除/重排（同 import 的括号 wrapping 保持不变）

分类明细：

| 文件 | 变化类型 | 示例 |
|---|---|---|
| `arg_parsing.py` | 相邻字符串合并为单行、函数调用参数压缩 | `"cmd-line args must be valid UTF-8 text; " "re-enter..."` → `"cmd-line...re-enter..."` |
| `cn_form_utils.py` | generator expression 压缩、conditional expression 压缩、函数调用压缩 | `tuple(period for period in canonical_order if period in seen)` 从多行改单行 |
| `sec_rebuild_workflow.py` | `cast()` mapping dict 格式化、`add_note()` 调用参数压缩、常量字符串合并 | `cast(JsonValue, {\n...\n})` → `cast(\nJsonValue,\n{\n...\n},\n)`（Ruff 对 nested dict 的标准换行） |
| `test_fins_ingestion_tools.py` | 测试 fixture 路径常量合并、assert 表达式压缩、函数调用压缩、return 表达式压缩 | `_REPO_ROOT / "dayu" / ...` 从多行改单行 |
| `test_fins_direct.py` | 测试 helper 调用参数压缩、`asyncio.create_task` 调用压缩 | `_FakeIngestionRuntime((_result_event(...),))` 从多行改单行 |

所有变化均可逆（逆操作生成相同的 Ruff formatter diff），无单向语义变更。

---

## 3. Contract / LLM-facing / Owner / Testing Drift 独立性检查

### 3.1 Contract drift

| 检查项 | 判定 | 证据 |
|---|---|---|
| 函数签名变更 | 无 | AST 等价，参数名/默认值/返回类型不变 |
| 类/dataclass 字段变更 | 无 | 五文件无类定义变更 |
| module `__all__` 变更 | 无 | 五文件无 `__all__` 变更 |
| 异常类型/消息变更 | 无 | 异常消息字符串内容不变，仅相邻字符串合并 |

### 3.2 LLM-facing drift

| 检查项 | 判定 | 证据 |
|---|---|---|
| prompt/scene prompt 变更 | 无 | 五文件不在 `dayu/config/prompts/` 下 |
| tool schema name/description/参数说明变更 | 无 | 五文件不定义 tool schema |
| LLM-readable message 变更 | 无 | `arg_parsing.py` 的 `help=` 文本字符精确不变（仅换行移除） |

### 3.3 Semantic ownership drift

| 检查项 | 判定 | 证据 |
|---|---|---|
| import 路径变更 | 无 | AST 等价，import 完全相同 |
| 模块依赖方向变更 | 无 | 无新增/删除 import |
| 真源迁移 | 无 | 不涉及 typed contract、enum、schema、协议 |

### 3.4 Testing drift

| 检查项 | 判定 | 证据 |
|---|---|---|
| 测试断言语义变更 | 无 | 断言表达式 AST 等价 |
| 测试 fixture 语义变更 | 无 | fixture 内常量值不变 |
| 测试参数化变更 | 无 | `@pytest.mark.parametrize` 参数不变 |
| 新测试新增/删除 | 无 | 五文件不包含测试函数新增/删除 |

---

## 4. 验证证据

| 检查项 | 结果 |
|---|---|
| 独立 AST 等价（`ast.parse` + `ast.dump` 严格相等） | 5/5 PASS |
| owner tests（`test_arg_parsing.py` + form resolution + rebuild owners + `test_fins_ingestion_tools.py` + `test_fins_direct.py`） | 566 passed, 0 failed |
| pyright（五文件） | 0 errors, 0 warnings |
| ruff check（五文件） | All checks passed |
| ruff format --check（五文件） | 5 files already formatted |
| compileall（五文件） | OK |
| git diff --check | OK |
| 全仓 pyright（only-if-needed 验证无回归） | 0 errors, 0 warnings（全仓基线已通过） |

---

## 5. 结论

**PASS** — 0 findings。

五文件 Python AST 与 `f0381f6a` 完全相同，属于 Ruff formatter-only layout closeout。无 contract、LLM-facing、semantic ownership 或 testing drift。所有要求验证（独立 AST、owner tests、pyright、ruff、compileall）通过。

format closeout artifact 的裁决（"formatter-only，无语义变更"）经独立验证确认可信。
