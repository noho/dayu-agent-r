# WU-SEMANTIC-OWNERSHIP-01 P3-I S1 re-review (AgentMiMo)

## Scope

- Gate: S1 re-review
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Verdict: **pass**
- Input artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s1-code-review-mimo.md` (original MiMo review)
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s1-code-review-ds.md` (original DS review)
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s1-code-review-controller-adjudication.md` (controller adjudication)
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s1-fix-codex.md` (Codex fix report)
- Re-review scope: 验证 accepted finding DS F1 是否被 fix 关闭；检查 fix 是否引入新 material issue。
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-i-s1-rereview-mimo.md`

## DS F1 Fix Verification

### Finding recap

DS F1（低）：`_normalize_system_exit_code` 在 `dayu/web/__main__.py`、`dayu/wechat/main.py`、`dayu/render/render.py` 中重复定义。Controller adjudication 要求提取到 `dayu.runtime` 层中立 helper。

### Fix 方案

Codex 新增 `dayu/runtime/argparse_exit.py`，提供 `normalize_argparse_system_exit_code(exc: SystemExit) -> int`，并替换三个入口模块的重复实现。

### Fix 验证

**1. `dayu/runtime/argparse_exit.py` 代码质量 ✅**

- 层中立：不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`，只依赖标准库 `typing.Final`。
- 类型完整：函数签名 `normalize_argparse_system_exit_code(exc: SystemExit) -> int`，参数和返回值均有类型标注。
- 中文 docstring 完整：包含参数、返回值、异常说明。
- 常量提取：`ARGPARSE_USAGE_ERROR_EXIT_CODE: Final[int] = 2` 消除了魔法数字。
- 行为不变：`isinstance(exc.code, int)` → 返回 code，否则返回 2。与原三处实现逻辑一致。

**2. 三个入口模块替换 ✅**

- `dayu/web/__main__.py`：已删除本地 `_normalize_system_exit_code` 和重复常量，改用 `from dayu.runtime.argparse_exit import normalize_argparse_system_exit_code`。
- `dayu/wechat/main.py`：同上。
- `dayu/render/render.py`：同上。
- 三处调用点行为不变：`except SystemExit as exc: return normalize_argparse_system_exit_code(exc)`。

**3. `dayu/runtime/__init__.py` 更新 ✅**

- 包 docstring 已登记 `dayu.runtime.argparse_exit`。
- 包根仍不 re-export（`__all__: list[str] = []`），符合架构约束。

**4. 无重复残留 ✅**

- `rg "_normalize_system_exit_code" --type py` 仅在 `dayu/cli/main.py` 中出现。
- `rg "normalize_argparse_system_exit_code" --type py` 在三个入口模块和 `dayu/runtime/argparse_exit.py` 中出现，分布正确。

**5. `dayu/cli/main.py` 保留独立实现 — 语义不同，不属于 DS F1 范围 ✅**

`dayu/cli/main.py` 仍保留自己的 `_normalize_system_exit_code`，但其语义与 runtime helper 不同：

| 行为 | `dayu.runtime.argparse_exit` | `dayu/cli/main.py` |
|---|---|---|
| `code is None` | 不处理（argparse 不会抛 `None` code） | 返回 `EXIT_SUCCESS (0)` |
| `isinstance(code, int)` | 返回 code | 返回 code |
| 其他 | 返回 `2`（argparse usage error） | 返回 `EXIT_FAILURE (1)` |

差异原因：`dayu/cli/main.py` 的 `_normalize_system_exit_code` 是整个 CLI 进程的最外层 `SystemExit` catch，需要处理来自所有 command runner 的 `SystemExit`（包括 `None` code 和非 argparse 来源的非整数 code）。而 `dayu.runtime.argparse_exit` 专门处理 argparse 抛出的 `SystemExit`，其非整数 code 按 argparse 约定映射为 usage error `2`。两者语义不同，`dayu/cli/main.py` 不属于 DS F1 的修复范围。

**6. 测试验证 ✅**

- `pytest tests/cli/test_public_package_entrypoints.py -q` → `12 passed in 0.12s`
- `python -m pyright dayu/runtime/argparse_exit.py dayu/web/__main__.py dayu/wechat/main.py dayu/render/render.py dayu/runtime/__init__.py` → `0 errors, 0 warnings, 0 informations`
- help smoke: `python -m dayu.web --help` / `python -m dayu.wechat.main --help` / `python -m dayu.render.render --help` → 均 exit 0，输出正确
- 诊断 smoke: `python -m dayu.web` (no args) → exit 1, 诊断文本正确；`python -m dayu.render.render input.md output.pdf` → exit 1, 诊断文本正确

**7. 行为不变确认 ✅**

所有 S1 测试断言未被修改，现有测试覆盖了三个入口的 help 路径（触发 argparse `SystemExit(0)` 经过共享 helper）和非 help 诊断路径。fix 不改变任何公开行为。

## DS F1 Status

**CLOSED (fixed)**

## New Findings

未发现新 material issue。

fix 实现干净：新增层中立 runtime helper，替换三处消费者，无行为变化，无新增依赖，类型完整，中文 docstring 完整。`dayu/cli/main.py` 保留独立实现有明确语义理由，不属于此 finding 范围。

## Open Questions

无。

## Residual Risk

- 与原始 DS review 残留风险一致：`dayu.render` package-data 资源文件仍未创建、完整 Web UI / WeChat daemon / render 转换能力仍为后续 slice 范围。
- 无新增残留风险。
