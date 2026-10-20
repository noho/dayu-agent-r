"""开发树公开原文 API 验收；只复制获准原件与仓储导航，保留每次完整返回。"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from datetime import datetime, UTC
import hashlib
import importlib.metadata
import json
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time
import traceback
from typing import cast

import dayu
from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.original_read_contract import (
    ExpandedName,
    OriginalSpan,
    SourceAssetIdentity,
    DocumentAssetsResult,
    OriginalStructureResult,
)
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.tools.read_runtime import FinsReadRuntime


def mapping(value: JsonValue) -> Mapping[str, JsonValue]:
    """参数：JSON 值。返回：严格 mapping。异常：非 mapping 拒绝。"""
    if not isinstance(value, Mapping):
        raise TypeError("需要 JSON mapping")
    return value


def items(value: JsonValue) -> list[JsonValue]:
    """参数：JSON 值。返回：严格数组。异常：非数组拒绝。"""
    if not isinstance(value, list):
        raise TypeError("需要 JSON 数组")
    return value


def string(value: JsonValue) -> str:
    """参数：JSON 值。返回：严格字符串。异常：类型不符。"""
    if not isinstance(value, str):
        raise TypeError("需要字符串")
    return value


def integer(value: JsonValue) -> int:
    """参数：JSON 值。返回：严格整数。异常：类型不符。"""
    if type(value) is not int:
        raise TypeError("需要整数")
    return value


def load(path: Path) -> JsonValue:
    """参数：JSON 文件。返回：JSON。异常：读取或解码错误。"""
    return cast(JsonValue, json.loads(path.read_text()))


def save(path: Path, value: JsonValue) -> None:
    """参数：本次证据路径和值。返回：无。异常：写入错误。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def fingerprint(path: Path) -> dict[str, JsonValue]:
    """参数：允许只读的原件/副本。返回：实际 SHA/size。异常：读取错误。"""
    payload = path.read_bytes()
    return {"sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload)}


class Recorder:
    """仅负责本次调用的完整返回、时间、错误与证据索引。"""

    def __init__(self, output: Path) -> None:
        """参数：本次独占输出目录。返回：无。异常：目录创建失败。"""
        self.output = output
        self.calls: list[JsonValue] = []
        output.mkdir(parents=True, exist_ok=False)

    def call(
        self, label: str, method: str, kwargs: Mapping[str, JsonValue], invoke: Callable[[], JsonValue]
    ) -> JsonValue:
        """参数：标签、公开方法、实参、调用。返回：完整返回。异常：保存完整 traceback 后透传原错误。"""
        started = time.perf_counter()
        target = self.output / f"{len(self.calls):05d}-{label}.json"
        receipt: dict[str, JsonValue] = {
            "method": method,
            "kwargs": kwargs,
            "started_at": datetime.now(UTC).isoformat(),
            "response": target.name,
        }
        try:
            result = invoke()
            save(target, result)
            receipt["success"] = True
            receipt["response_fingerprint"] = fingerprint(target)
            return result
        except BaseException as exc:
            receipt.update(success=False, error_type=type(exc).__name__, error=str(exc))
            target.with_suffix(".error.txt").write_text(traceback.format_exc())
            raise
        finally:
            receipt["elapsed_seconds"] = time.perf_counter() - started
            receipt["maxrss_bytes_macos"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            self.calls.append(receipt)
            save(self.output / "calls.json", self.calls)
            print(
                json.dumps(
                    {
                        "call": len(self.calls),
                        "label": label,
                        "success": receipt["success"],
                        "seconds": receipt["elapsed_seconds"],
                    }
                ),
                flush=True,
            )


def copy_inputs(source: Path, destination: Path, plans: list[Mapping[str, JsonValue]]) -> list[JsonValue]:
    """参数：只读调用方根、隔离副本、六批计划。返回：每个允许文件的双份指纹。异常：越界、symlink、字节不符。"""
    selected: set[Path] = set()
    tickers: set[str] = set()
    for plan in plans:
        for call in items(plan["calls"]):
            tickers.add(string(mapping(mapping(call)["kwargs"])["ticker"]))
        for raw in items(plan["sources"]):
            declaration = mapping(raw)
            path = Path(string(declaration["path"]))
            relative = path.relative_to(source)
            assert relative.parts[0] == "portfolio"
            actual = fingerprint(path)
            assert actual["sha256"] == declaration["sha256"] and actual["size_bytes"] == declaration["size"]
            selected.add(path.parent)
    allowed: set[Path] = set()
    for company in tickers:
        root = source / "portfolio" / company
        allowed.update(root / filename for filename in (".identity.json", "meta.json"))
        for kind, manifest in (("filings", "filing_manifest.json"), ("materials", "material_manifest.json")):
            directory = root / kind
            if (directory / manifest).is_file():
                allowed.add(directory / manifest)
            # 完整 manifest 的双向导航校验需要同公司 source identity/meta，不读取其它业务产物。
            for child in directory.glob("id-*"):
                if child.is_dir():
                    allowed.update(child / name for name in (".identity.json", "meta.json") if (child / name).is_file())
    for directory in selected:
        allowed.update(path for path in directory.iterdir() if path.is_file())
    receipts: list[JsonValue] = []
    for path in sorted(allowed):
        assert not path.is_symlink()
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        before = fingerprint(path)
        if target.exists():
            assert fingerprint(target) == before, f"已有副本与原件不符：{relative}"
        else:
            shutil.copyfile(path, target)
        assert fingerprint(target) == before
        receipts.append({"relative_path": str(relative), "before": before, "copy_before": fingerprint(target)})
    return receipts


def replay(reader: FinsReadRuntime, call: Mapping[str, JsonValue]) -> JsonValue:
    """参数：公开 reader 与历史请求。返回：新版本公开返回。异常：真实 API 错误。"""
    method = string(call["method"])
    kwargs = mapping(call["kwargs"])
    ticker = string(kwargs["ticker"])
    if method == "list_documents":
        return cast(JsonValue, reader.list_documents(ticker=ticker))
    document = string(kwargs["document_id"])
    if method == "get_document_sections":
        return cast(JsonValue, reader.get_document_sections(ticker=ticker, document_id=document))
    if method == "read_section":
        return cast(JsonValue, reader.read_section(ticker=ticker, document_id=document, ref=string(kwargs["ref"])))
    if method == "get_table":
        return cast(
            JsonValue, reader.get_table(ticker=ticker, document_id=document, table_ref=string(kwargs["table_ref"]))
        )
    if method == "list_tables":
        return cast(JsonValue, reader.list_tables(ticker=ticker, document_id=document))
    if method == "get_page_content":
        return cast(
            JsonValue, reader.get_page_content(ticker=ticker, document_id=document, page_no=integer(kwargs["page_no"]))
        )
    if method == "search_document":
        queries = [string(v) for v in items(kwargs["queries"])] if "queries" in kwargs else None
        return cast(
            JsonValue,
            reader.search_document(
                ticker=ticker,
                document_id=document,
                query=string(kwargs["query"]) if "query" in kwargs else None,
                queries=queries,
                mode=string(kwargs["mode"]),
            ),
        )
    raise ValueError("计划含未授权的方法")


def text_call(
    reader: FinsReadRuntime, recorder: Recorder, asset: SourceAssetIdentity, start: int, end: int | None, label: str
) -> Mapping[str, JsonValue]:
    """参数：reader/证据器、已枚举身份、范围、标签。返回：实际公开文本页。异常：API 或断言失败。"""
    kwargs: dict[str, JsonValue] = {
        "ticker": asset["ticker"],
        "document_id": asset["document_id"],
        "source_kind": asset["source_kind"],
        "filename": asset["filename"],
        "expected_sha256": asset["sha256"],
        "start": start,
        "end": end,
        "max_chars": 65536,
    }
    return mapping(
        recorder.call(
            label,
            "read_original_text",
            kwargs,
            lambda: cast(
                JsonValue,
                reader.read_original_text(
                    ticker=asset["ticker"],
                    document_id=asset["document_id"],
                    source_kind=SourceKind(asset["source_kind"]),
                    filename=asset["filename"],
                    expected_sha256=asset["sha256"],
                    start=start,
                    end=end,
                    max_chars=65536,
                ),
            ),
        )
    )


def asset_arguments(asset: SourceAssetIdentity) -> dict[str, JsonValue]:
    """参数：已枚举身份。返回：实际公开方法选择参数。异常：无。"""
    return {
        "ticker": asset["ticker"],
        "document_id": asset["document_id"],
        "source_kind": asset["source_kind"],
        "filename": asset["filename"],
        "expected_sha256": asset["sha256"],
    }


def read_span(reader: FinsReadRuntime, recorder: Recorder, span: OriginalSpan, label: str) -> str:
    """参数：公开定位、reader、证据器及标签。返回：通过公开分页回读的完整原文。异常：页不连续或 API 失败。"""
    parts: list[str] = []
    start = span["start"]
    while True:
        page = text_call(reader, recorder, span["asset"], start, span["end"], label)
        assert page["asset"] == span["asset"]
        piece = string(page["text"])
        assert integer(mapping(page["returned_range"])["start"]) == start
        parts.append(piece)
        if page["next_start"] is None:
            assert not page["truncated"]
            break
        assert page["next_start"] == start + len(piece)
        start += len(piece)
    return "".join(parts)


def verify_original(
    reader: FinsReadRuntime,
    recorder: Recorder,
    source_root: Path,
    copy_root: Path,
    evidence: Path,
    targets: Mapping[str, str],
) -> list[JsonValue]:
    """参数：公开 reader、回执、原件/副本根、锚证据和文档路由。返回：真实原文验收结果。异常：真实输入失败即阻塞。"""
    checks: list[JsonValue] = []
    anchors = items(load(evidence / "targeted-original-anchors.json"))
    for raw_group in anchors:
        group = mapping(raw_group)
        source = mapping(group["source"])
        relative = Path(string(source["path"])).relative_to("workspace")
        ticker, filename = relative.parts[1], relative.name
        document = targets[ticker]
        listing = mapping(
            recorder.call(
                ticker + "-assets",
                "list_document_assets",
                {"ticker": ticker, "document_id": document, "source_kind": "filing"},
                lambda: cast(
                    JsonValue,
                    reader.list_document_assets(ticker=ticker, document_id=document, source_kind=SourceKind.FILING),
                ),
            )
        )
        selected = [
            mapping(a) for a in items(listing["assets"]) if mapping(mapping(a)["asset"])["filename"] == filename
        ]
        assert len(selected) == 1
        asset = cast(SourceAssetIdentity, dict(mapping(selected[0]["asset"])))
        actual = fingerprint(source_root / relative)
        assert asset["sha256"] == actual["sha256"] and asset["size_bytes"] == actual["size_bytes"]
        assert fingerprint(copy_root / relative) == actual
        for temperature in ("cold", "warm"):
            chunks: list[str] = []
            start = 0
            while True:
                page = text_call(reader, recorder, asset, start, None, ticker + "-" + temperature)
                piece = string(page["text"])
                assert page["asset"] == asset
                assert mapping(page["returned_range"])["start"] == start
                chunks.append(piece)
                if page["next_start"] is None:
                    assert not page["truncated"]
                    break
                assert page["next_start"] == start + len(piece)
                start += len(piece)
            text = "".join(chunks)
            # 外部指纹只验真 API 身份；生产内容与定位全部经公开 API 取得。
            payload = (source_root / relative).read_bytes()
            assert text == payload.decode("utf-8-sig")
            assert len(text) == page["total_chars"]
        discovery = mapping(
            recorder.call(
                ticker + "-namespace",
                "read_original_structure",
                {**asset_arguments(asset), "start": 0, "end": None, "max_nodes": 200},
                lambda: cast(
                    JsonValue,
                    reader.read_original_structure(
                        ticker=ticker,
                        document_id=document,
                        source_kind=SourceKind.FILING,
                        filename=filename,
                        expected_sha256=asset["sha256"],
                        max_nodes=200,
                    ),
                ),
            )
        )
        declarations: dict[str, str] = {}
        for raw_node in items(discovery["nodes"]):
            node = mapping(raw_node)
            for raw_attribute in items(node["attributes"]):
                attribute = mapping(raw_attribute)
                name = string(attribute["name"])
                if name.startswith("xmlns:") and attribute["value"] is not None:
                    preview = mapping(attribute["value"])
                    assert preview["preview_complete"] is True
                    declarations[name.partition(":")[2]] = string(preview["preview"])
        concepts: list[ExpandedName] = []
        expected_occurrences: dict[str, list[Mapping[str, JsonValue]]] = {}
        for raw_anchor in items(group["anchors"]):
            anchor = mapping(raw_anchor)
            prefix, separator, local = string(anchor["concept_search"]).partition(":")
            if not separator or not items(anchor["matches"]):
                continue
            assert prefix in declarations, f"公开结构未发现 {ticker}/{prefix} URI"
            concepts.append({"namespace_uri": declarations[prefix], "local_name": local})
            expected_occurrences[local] = [mapping(m) for m in items(anchor["matches"])]
            for match in expected_occurrences[local]:
                back = read_span(
                    reader,
                    recorder,
                    {"asset": asset, "start": integer(match["start"]), "end": integer(match["end"])},
                    ticker + "-anchor",
                )
                assert back == match["raw"]
        if concepts:
            facts = mapping(
                recorder.call(
                    ticker + "-facts",
                    "query_original_facts",
                    {**asset_arguments(asset), "concepts": cast(JsonValue, concepts), "offset": 0, "limit": 500},
                    lambda: cast(
                        JsonValue,
                        reader.query_original_facts(
                            ticker=ticker,
                            document_id=document,
                            source_kind=SourceKind.FILING,
                            filename=filename,
                            expected_sha256=asset["sha256"],
                            concepts=concepts,
                            limit=500,
                        ),
                    ),
                )
            )
            assert not facts["truncated"]
            occurrences = [mapping(f) for f in items(facts["facts"])]
            for concept, expected in expected_occurrences.items():
                found = [
                    f for f in occurrences if f["name"] is not None and mapping(f["name"])["local_name"] == concept
                ]
                assert len(found) >= len(expected), f"原生事实缺失：{ticker}/{concept}"
                for match in expected:
                    assert any(mapping(mapping(f["node"])["opening"])["start"] == match["start"] for f in found)
            for fact in occurrences:
                node = mapping(fact["node"])
                span = cast(OriginalSpan, dict(mapping(mapping(node["preview"])["span"])))
                raw = read_span(reader, recorder, span, ticker + "-fact-node")
                assert raw.startswith(string(mapping(node["preview"])["preview"]))
                context = mapping(fact["context"])
                assert context["status"] == "resolved", f"真实 fact context 未解析：{ticker}"
                context_preview = mapping(context["target"])
                context_span = cast(OriginalSpan, dict(mapping(context_preview["span"])))
                assert read_span(reader, recorder, context_span, ticker + "-context").startswith(
                    string(context_preview["preview"])
                )
            if ticker == "MSFT":
                assert len([f for f in occurrences if mapping(f["name"])["local_name"] == "TradingSymbol"]) == 3
        checks.append(
            {
                "ticker": ticker,
                "asset": cast(JsonValue, asset),
                "full_text_chars": len(text),
                "namespace_declarations": declarations,
                "discovery_parse_status": discovery["parse_status"],
                "verified": True,
            }
        )
    # 主件的关系原文与附件分别选择；保留 reading primary。
    ticker, document = "TSM", targets["TSM"]
    listing = cast(
        DocumentAssetsResult,
        recorder.call(
            "tsm-assets-both",
            "list_document_assets",
            {"ticker": ticker, "document_id": document, "source_kind": "filing"},
            lambda: cast(
                JsonValue,
                reader.list_document_assets(ticker=ticker, document_id=document, source_kind=SourceKind.FILING),
            ),
        ),
    )
    assert listing["reading_primary_filename"] == "tsm-ex991_18.htm"
    main = next(a["asset"] for a in listing["assets"] if a["asset"]["filename"] == "tsm-6k_20220812.htm")
    attachment = next(a["asset"] for a in listing["assets"] if a["asset"]["filename"] == "tsm-ex991_18.htm")
    main_text = string(text_call(reader, recorder, main, 0, None, "tsm-main-relationship")["text"])
    assert 'href="tsm-ex991_18.htm"' in main_text
    main_structure = cast(
        OriginalStructureResult,
        recorder.call(
            "tsm-main-structure",
            "read_original_structure",
            {**asset_arguments(main), "max_nodes": 1000},
            lambda: cast(
                JsonValue,
                reader.read_original_structure(
                    ticker=ticker,
                    document_id=document,
                    source_kind=SourceKind.FILING,
                    filename=main["filename"],
                    expected_sha256=main["sha256"],
                    max_nodes=1000,
                ),
            ),
        ),
    )
    link = next(
        node
        for node in main_structure["nodes"]
        if any(
            attr["name"] == "href" and attr["value"] is not None and attr["value"]["preview"] == attachment["filename"]
            for attr in node["attributes"]
        )
    )
    assert 'href="tsm-ex991_18.htm"' in read_span(reader, recorder, link["opening"], "tsm-href-opening")
    assert link["content"] is not None and read_span(reader, recorder, link["content"], "tsm-link-text").strip()
    assert main_structure["parse_status"] == "partial"  # 原件保留 SEC SGML 外层，不能冒充完整 HTML 树。
    assert any(n["parent_status"] == "unknown" for n in main_structure["nodes"])
    assert link["parent_status"] == "resolved" and not link["ancestors_complete"]
    assert (
        main["sha256"] == "4e93053855798383ab0c98b5e03f1f5183bf1eed7707c9639738c7192b34d6b1"
        and main["size_bytes"] == 34492
    )
    assert (
        attachment["sha256"] == "63942e99dfe4e4417ba356e434f84b2c50c3d4b5bbae1a3f8d86f8b9557525dc"
        and attachment["size_bytes"] == 10997629
    )
    first = text_call(reader, recorder, attachment, 0, 1000, "tsm-attachment-opening")
    assert "English Translation" in string(first["text"])
    full_attachment = read_span(
        reader, recorder, {"asset": attachment, "start": 0, "end": integer(first["total_chars"])}, "tsm-attachment-full"
    )
    attachment_paths = list((copy_root / "portfolio" / "TSM" / "filings").glob("*/tsm-ex991_18.htm"))
    assert len(attachment_paths) == 1 and full_attachment == attachment_paths[0].read_bytes().decode("utf-8-sig")
    checks.append(
        {"main": cast(JsonValue, main), "attachment": cast(JsonValue, attachment), "relationship_verified": True}
    )
    return checks


def main() -> int:
    """参数：命令行隔离目录及证据根。返回：真实退出码。异常：失败留 traceback/回执且返回 1。"""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source-workspace", "workspace-root", "evidence-root", "output-dir"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    source, workspace, evidence, output = (
        Path(args.source_workspace).resolve(),
        Path(args.workspace_root).resolve(),
        Path(args.evidence_root).resolve(),
        Path(args.output_dir).resolve(),
    )
    assert workspace != source and source not in workspace.parents
    recorder = Recorder(output)
    receipt: dict[str, JsonValue] = {
        "argv": cast(JsonValue, sys.argv),
        "python": sys.executable,
        "dayu_module": dayu.__file__,
        "started_at": datetime.now(UTC).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "dependencies": {
            n: importlib.metadata.version(n)
            for n in ("dayu-agent", "beautifulsoup4", "lxml", "edgartools", "docling-core")
        },
        "notes": [
            "cold 仅指本次新 runtime 未有 entry，不清 OS cache",
            "不运行 live、下载、上传、预处理",
            "指纹为外部验真；内容仅由公开 API 产生",
        ],
    }
    runtime: DefaultFinsRuntime | None = None
    before: list[JsonValue] = []
    exit_code = 1
    try:
        diff = subprocess.check_output(["git", "diff", "--binary"])
        (output / "development.diff").write_bytes(diff)
        receipt["diff_sha256"] = hashlib.sha256(diff).hexdigest()
        modules = [p for p in Path("dayu/fins").rglob("*.py") if p.is_file()]
        receipt["module_fingerprints"] = {str(p): fingerprint(p) for p in modules}
        for path in [*modules, Path(__file__), Path("dayu/config/prompts/base/tools.md")]:
            target = (
                output / "source-snapshot" / path.relative_to(Path.cwd())
                if path.is_absolute()
                else output / "source-snapshot" / path
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        plans = [mapping(load(evidence / f"api-probe-{i:02}-plan.json")) for i in range(1, 7)]
        before = copy_inputs(source, workspace, plans)
        save(output / "input-fingerprints-before.json", before)
        replay_results: list[JsonValue] = []
        targets: dict[str, str] = {}
        for batch, plan in enumerate(plans, 1):
            runtime = DefaultFinsRuntime.create(workspace_root=workspace)
            try:
                reader = runtime.get_read_runtime()
                for raw in items(plan["calls"]):
                    call = mapping(raw)
                    kwargs = mapping(call["kwargs"])
                    if "document_id" in kwargs:
                        targets[string(kwargs["ticker"])] = string(kwargs["document_id"])
                    result = mapping(
                        recorder.call(
                            f"replay-{batch}-" + string(call["id"]),
                            string(call["method"]),
                            kwargs,
                            lambda: replay(reader, call),
                        )
                    )
                    historical = mapping(load(evidence / f"api-probe-{batch:02}" / (string(call["id"]) + ".json")))
                    assert result.get("supported") == historical.get("supported")
                    if "content" in historical:
                        assert len(string(result["content"])) >= len(string(historical["content"]))
                    for field in ("records", "markdown"):
                        if field in historical:
                            assert result[field] == historical[field]
                    for field in ("sections", "tables", "records"):
                        if field in historical and isinstance(historical[field], list):
                            assert len(items(result[field])) == len(items(historical[field]))
                    replay_results.append(
                        {"batch": batch, "id": call["id"], "supported": result.get("supported"), "verified": True}
                    )
            finally:
                runtime.close()
                runtime = None
        assert len(replay_results) == 53
        receipt["replay"] = replay_results
        runtime = DefaultFinsRuntime.create(workspace_root=workspace)
        receipt["original_checks"] = verify_original(
            runtime.get_read_runtime(), recorder, source, workspace, evidence, targets
        )
        runtime.close()
        runtime = DefaultFinsRuntime.create(workspace_root=workspace)
        reader = runtime.get_read_runtime()
        reopened = cast(
            DocumentAssetsResult,
            recorder.call(
                "reopened-assets",
                "list_document_assets",
                {"ticker": "TSM", "document_id": targets["TSM"], "source_kind": "filing"},
                lambda: cast(
                    JsonValue,
                    reader.list_document_assets(
                        ticker="TSM", document_id=targets["TSM"], source_kind=SourceKind.FILING
                    ),
                ),
            ),
        )
        asset = next(a["asset"] for a in reopened["assets"] if a["asset"]["filename"] == "tsm-6k_20220812.htm")
        assert "FORM" in string(text_call(reader, recorder, asset, 0, 10000, "reopened-main")["text"])
        exit_code = 0
    except BaseException:
        (output / "failure.txt").write_text(traceback.format_exc())
        print(traceback.format_exc(), file=sys.stderr)
    finally:
        if runtime is not None:
            runtime.close()
        after: list[JsonValue] = []
        for raw in before:
            record = mapping(raw)
            relative = Path(string(record["relative_path"]))
            original, copied = fingerprint(source / relative), fingerprint(workspace / relative)
            assert original == copied == record["before"]
            after.append({"relative_path": str(relative), "after": original, "copy_after": copied})
        save(output / "input-fingerprints-after.json", after)
        receipt.update(
            exit_code=exit_code,
            finished_at=datetime.now(UTC).isoformat(),
            calls=len(recorder.calls),
            source_and_copy_unchanged=True,
        )
        save(output / "receipt.json", receipt)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
