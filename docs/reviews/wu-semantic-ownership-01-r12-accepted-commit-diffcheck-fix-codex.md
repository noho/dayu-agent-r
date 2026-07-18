# WU-SEMANTIC-OWNERSHIP-01 R12 accepted commit diff-check evidence hygiene fix

## Gate 与范围

- 这是 `WU-SEMANTIC-OWNERSHIP-01` umbrella 内部 R12 accepted implementation local commit gate 的证据卫生修正，不是新 WU。
- 修正范围仅包含 6 个既有 R12 review artifacts；除此之外只新增本证据 artifact。
- 未修改 product、test、README、workflow、plan、control 或其他 artifact，未执行 stage、commit、push。

## Root cause

问题根因是待检查的 review artifacts 在最初检查时尚未被 Git 跟踪，而普通 `git diff --check` 不会把 untracked files 纳入 diff，因此空白错误没有进入该检查的输入集合。到本 gate 核验时，这 6 个文件已经是 staged additions；普通 `git diff --check` 仍只比较 working tree 与 index，修正前无输出，但限定这 6 个文件执行 `git diff --cached --check` 可直接复现 7 个空白错误：5 个 EOF 空白行和 2 个行尾空格。

因此，问题不属于正文语义、review 结论或产品实现错误，而是检查输入范围遗漏。accepted commit gate 必须检查 `HEAD` 到 working tree 的 staged+working 合成内容，不能只依赖普通 working-tree diff-check。

## 精确修正

1. `docs/reviews/wu-semantic-ownership-01-r12-s2-code-final-rereview-controller-adjudication.md`：删除 1 个 EOF 多余空行。
2. `docs/reviews/wu-semantic-ownership-01-r12-s2-code-rereview-controller-adjudication.md`：删除 1 个 EOF 多余空行。
3. `docs/reviews/wu-semantic-ownership-01-r12-s2-code-review-ds.md`：仅删除第 197、205 行各 1 个行尾空格，正文字符不变。
4. `docs/reviews/wu-semantic-ownership-01-r12-s2-implementation-codex.md`：删除 1 个 EOF 多余空行。
5. `docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-plan-review-controller-adjudication.md`：删除 1 个 EOF 多余空行。
6. `docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-plan-review-fix-controller-validation.md`：删除 1 个 EOF 多余空行。

修正指标：6 个既有 artifacts、7 个机械空白错误；相对 index 的 working-tree delta 为 2 insertions、7 deletions，其中两处行尾空格删除各表现为一行替换。

## 验证

- `git diff --check`：PASS，无输出。
- 对上述 6 个路径执行 `git diff --check HEAD -- <paths>`：PASS，无输出；该口径验证 `HEAD` 到 working tree 的 staged+working 合成结果。
- 对上述 6 个路径执行 `git diff --numstat -- <paths>`：5 个 EOF 修正文件各为 `0 1`，行尾空格修正文件为 `2 2`，合计 `2 7`。
- 工作区范围核对：相对修正前基线，tracked working-tree 变化只包含上述 6 个既有 artifacts；新增 untracked file 只包含本证据 artifact。既有 staged R12 tree 保持暂存状态，未被重新 stage。
- 因本 gate 明确禁止 stage，index-only 的 `git diff --cached --check -- <paths>` 仍会报告 index 内原有的 7 个空白错误；这是预期状态。后续获授权的 commit 操作者必须先将这 6 个 working-tree 修正和本证据 artifact 纳入 index，再复验 cached diff，不能直接提交当前旧 index。
- 受影响测试：不适用；本次只修正文档空白，不触及 Python、测试、schema 或运行时行为。`source .venv/bin/activate` 后运行 `pyright`：PASS（0 errors、0 warnings、0 informations）。

## 结论

6 个既有 R12 review artifacts 的 staged+working 合成内容已无 Git 空白错误；本修正没有改变任何 review 正文语义，也没有扩大 accepted local commit gate 的授权范围。
