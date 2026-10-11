"""显式 opt-in 的两例真实 SEC CLI fresh/旧版升级/故障/重试验收。"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path
from typing import cast
from urllib.parse import quote, urljoin

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.enums import SourceKind
from dayu.fins.downloaders.sec_downloader import RemoteFileDescriptor, SecDownloader, build_source_fingerprint
from dayu.fins.pipelines.sec_filing_collection import FilingRecord, collect_filings_from_table
from dayu.fins.pipelines.sec_pipeline import SEC_PIPELINE_DOWNLOAD_VERSION
from dayu.fins.storage import FsSourceDocumentRepository, SourceIntegrityStatus
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.storage.local_file_store import LocalFileStore

_REPO = Path(__file__).resolve().parents[2]
_BASELINE_COMMIT = "297bfbbc67b7d7468e3dfb6669a3385c4dd10d18"
_OLD_VERSION = "sec_pipeline_download_v1.2.0"
_DIAGNOSTICS_PREFIX = "Fins download diagnostics: "
_SAMPLES = (
    ("2019", "0001193125-19-110066", "d733154d6k.htm", 17, 15),
    ("2025", "0001046179-25-000082", "a2q25presentatione_6kxwm.htm", 12, 12),
)
_FILING_UNIQUE_IMAGES = {"d733154d6k.htm": 15, "a2q25presentatione_6kxwm.htm": 13}
_PRODUCER_PATHS = (
    "dayu/fins/downloaders/sec_downloader.py",
    "dayu/fins/pipelines/sec_download_filing_workflow.py",
    "dayu/fins/pipelines/sec_pipeline.py",
    "dayu/fins/pipelines/sec_rebuild_workflow.py",
)
# 只观察 transport 与原指纹函数；fault 仅改变 exact 图片 GET 的远端响应。
_OBSERVER_SCRIPT = '''"""临时真实验证 transport/descriptor 观测器，不改变生产结果。"""
from __future__ import annotations
import importlib.metadata
import hashlib
import json
import os
from pathlib import Path
import httpx
from dayu.contracts.json_value import JsonValue
from dayu.fins.downloaders import sec_downloader

def record(value: dict[str, JsonValue]) -> None:
    """参数为非敏感事实；返回无；证据写入异常透传。"""
    with Path(os.environ["DAYU_SEC_IMAGE_OBSERVER"]).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=True) + "\\n")

original_fingerprint = sec_downloader.build_source_fingerprint

def observed_fingerprint(descriptors: list[sec_downloader.RemoteFileDescriptor]) -> str:
    """参数为真实描述符；返回原函数结果；原函数异常透传。"""
    result = original_fingerprint(descriptors)
    rows: list[JsonValue] = [{"name": item.name, "source_url": item.source_url,
        "http_etag": item.http_etag, "http_last_modified": item.http_last_modified,
        "remote_size": item.remote_size, "http_status": item.http_status,
        "sec_document_type": item.sec_document_type, "sec_description": item.sec_description}
        for item in descriptors]
    record({"kind": "fingerprint", "descriptors": rows, "fingerprint": result})
    return result

sec_downloader.build_source_fingerprint = observed_fingerprint
original_transport = httpx.AsyncHTTPTransport.handle_async_request

async def observed_transport(self: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
    """参数为真实 transport/request；返回原响应或 exact GET 404；网络异常透传。"""
    url = str(request.url).split("?", 1)[0].split("#", 1)[0]
    fault = request.method == "GET" and url == os.environ.get("DAYU_SEC_IMAGE_FAULT", "")
    if fault:
        response = httpx.Response(404, request=request, content=b"isolated required-image fault")
    else:
        response = await original_transport(self, request)
    if url.startswith(os.environ["DAYU_SEC_IMAGE_ARCHIVE"]):
        record({"kind": "transport", "method": request.method, "url": url,
                "status": response.status_code, "fault": fault})
    return response

httpx.AsyncHTTPTransport.handle_async_request = observed_transport
import dayu
from dayu.fins.pipelines import sec_pipeline
record({"kind": "origin", "dayu": dayu.__file__, "sec_pipeline": sec_pipeline.__file__,
        "sec_downloader_sha256": hashlib.sha256(Path(sec_downloader.__file__).read_bytes()).hexdigest(),
        "package_version": importlib.metadata.version("dayu-agent"),
        "download_version": sec_pipeline.SEC_PIPELINE_DOWNLOAD_VERSION})
'''


@dataclass
class _Context:
    """独立验证 roots 与只在内存存在的子进程配置。"""

    root: Path
    baseline: Path
    cli: Path
    environment: dict[str, str] = field(repr=False)
    filings: dict[str, FilingRecord] = field(default_factory=dict)


def _write_json(path: Path, value: JsonValue) -> None:
    """参数为证据路径与非敏感 JSON；返回无；写入异常透传。"""
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, JsonValue]:
    """参数为证据路径；返回有明确 JSON 边界的字典；格式不符时断言失败。"""
    value = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(value, dict)
    return value


def _mapping(value: JsonValue) -> dict[str, JsonValue]:
    """参数为 JSON 值；返回明确字典；错误 schema 时断言失败。"""
    assert isinstance(value, dict)
    return value


def _rows(value: JsonValue) -> list[dict[str, JsonValue]]:
    """参数为 JSON 数组；返回每行字典；错误 schema 时断言失败。"""
    assert isinstance(value, list)
    return [_mapping(row) for row in value]


def _load_user_agent() -> str:
    """无参数；在内存提取既有 zshrc literal 身份；缺席或非法配置时抛出安全错误。"""
    contents = (Path.home() / ".zshrc").read_text(encoding="utf-8")
    pattern = r'''(?m)^[ \t]*(?:export[ \t]+)?SEC_USER_AGENT[ \t]*=[ \t]*("[^"\n]*"|'[^'\n]*')[ \t]*(?:\#.*)?$'''
    literals = re.findall(pattern, contents)
    if not literals:
        raise RuntimeError("既有 SEC_USER_AGENT literal 未配置，真实验证失败")
    tokens = shlex.split(literals[-1])
    if len(tokens) != 1 or not tokens[0] or "$" in tokens[0] or "`" in tokens[0]:
        raise RuntimeError("SEC_USER_AGENT 不是可直接复用的 literal，真实验证失败")
    return tokens[0]


def _producer_hashes() -> dict[str, JsonValue]:
    """无参数；返回四个生产 owner 的源码 hash；源码读取异常透传。"""
    return {name: hashlib.sha256((_REPO / name).read_bytes()).hexdigest() for name in _PRODUCER_PATHS}


async def _official_filings(context: _Context) -> dict[str, FilingRecord]:
    """参数为验证配置；经生产 SEC downloader/收集 owner 返回正式披露元数据；网络异常透传。"""
    downloader = SecDownloader(context.root / "metadata", user_agent=context.environment["SEC_USER_AGENT"])
    try:
        cik, _, cik10 = await downloader.resolve_company("TSM")
        assert int(cik) == 1046179
        submissions = await downloader.fetch_submissions(cik10)
        filings = _mapping(submissions["filings"])
        records: dict[str, FilingRecord] = {}
        collect_filings_from_table(records=records, table=_mapping(filings["recent"]),
                                   form_windows={"6-K": dt.date(2019, 1, 1)}, end_date=dt.date(2025, 12, 31))
        for file in _rows(filings["files"]):
            if all(accession in records for _, accession, _, _, _ in _SAMPLES):
                break
            filename = file["name"]
            assert isinstance(filename, str)
            table = await downloader.fetch_json("https://data.sec.gov/submissions/" + filename)
            collect_filings_from_table(records=records, table=table,
                                       form_windows={"6-K": dt.date(2019, 1, 1)}, end_date=dt.date(2025, 12, 31))
        selected = {accession: records[accession] for _, accession, _, _, _ in _SAMPLES}
        for _, accession, _, _, _ in _SAMPLES:
            assert selected[accession].form_type == "6-K"
        return selected
    finally:
        await downloader.close()


@pytest.fixture(scope="module")
def real_context() -> Iterator[_Context]:
    """无参数；返回 opt-in 配置与正式日期；未启用时 skip，启用后任何配置/网络失败均 fail。"""
    if os.environ.get("DAYU_SEC_IMAGE_REAL_VALIDATION") != "1":
        pytest.skip("未启用 DAYU_SEC_IMAGE_REAL_VALIDATION=1；这不是实际网络验收通过")
    root = Path(os.environ["DAYU_SEC_IMAGE_RUN_ROOT"]).resolve()
    baseline = Path(os.environ["DAYU_SEC_IMAGE_BASELINE_ROOT"]).resolve()
    cli = Path(os.environ["DAYU_SEC_IMAGE_CLI"]).absolute()
    assert root.is_relative_to(_REPO / "workspace/tmp")
    assert baseline.is_relative_to(root) and (baseline / "dayu/cli/__main__.py").is_file()
    assert cli == _REPO / ".venv/bin/dayu-cli" and cli.is_file()
    hooks = root / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "sitecustomize.py").write_text(_OBSERVER_SCRIPT, encoding="utf-8")
    environment = dict(os.environ)
    environment["SEC_USER_AGENT"] = _load_user_agent()
    context = _Context(root, baseline, cli, environment)
    context.filings = asyncio.run(_official_filings(context))
    producer_hashes = _producer_hashes()
    _write_json(root / "evidence/context.json", {
        "run_root": str(root), "baseline_root": str(baseline), "baseline_commit": _BASELINE_COMMIT,
        "cli": str(cli), "cli_resolved": str(cli.resolve()), "ua_configured": True,
        "producer_hashes": producer_hashes,
        "samples": [{"accession": filing.accession_number, "filing_date": filing.filing_date,
                     "form": filing.form_type, "primary_document": filing.primary_document}
                    for filing in context.filings.values()],
    })
    try:
        yield context
    finally:
        assert _producer_hashes() == producer_hashes
        credential = environment["SEC_USER_AGENT"].encode()
        leak_free = all(credential not in path.read_bytes() for path in (root / "evidence").rglob("*") if path.is_file())
        _write_json(root / "evidence/credential-check.json", {"ua_configured": True, "credential_leak_check_passed": leak_free})
        assert leak_free, "真实验证证据包含身份值"


class _RealFlatImages(HTMLParser):
    """独立验收 parser：真实样例限平铺 img/src，遇到新形态明确失败。"""

    def __init__(self) -> None:
        """无参数；初始化引用列表；无异常。"""
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """参数为真实标签属性；收集 src；base/srcset/picture 输入变化时断言失败。"""
        values: dict[str, str | None] = {}
        for name, value in attrs:
            values.setdefault(name, value)
        assert tag not in {"base", "picture"}
        assert not (tag in {"img", "source"} and values.get("srcset"))
        if tag == "img" and values.get("src"):
            source = values["src"]
            assert source is not None and "/" not in source and "?" not in source and "#" not in source
            self.references.append(source)


def _snapshot(context: _Context, base: Path, accession: str) -> dict[str, JsonValue]:
    """参数为配置、独立 base 与文档；仓储同版读回 metadata/URI/hash/manifest；不一致时失败。"""
    document_id = "fil_" + accession
    source = FsSourceDocumentRepository(base)
    assert source.classify_source_integrity("TSM", document_id, SourceKind.FILING).status is SourceIntegrityStatus.COMPLETE
    with source.read_source_snapshot("TSM", document_id, SourceKind.FILING, materialize_files=True) as snapshot:
        metadata = dict(snapshot.source_meta)
        entries = {str(row["name"]): row for row in _rows(metadata["files"])}
        observed: list[JsonValue] = []
        for descriptor in snapshot.files:
            with snapshot.get_source(descriptor.name).open() as stream:
                payload = stream.read()
            published_source = source.get_source("TSM", document_id, SourceKind.FILING, descriptor.name)
            with published_source.open() as stream:
                assert stream.read() == payload
            digest = hashlib.sha256(payload).hexdigest()
            assert descriptor.sha256 == entries[descriptor.name]["sha256"] == digest
            assert descriptor.size == entries[descriptor.name]["size"] == len(payload)
            assert published_source.uri == entries[descriptor.name]["uri"]
            observed.append({"name": descriptor.name, "uri": published_source.uri, "size": len(payload), "sha256": digest})
        assert set(entries) == {descriptor.name for descriptor in snapshot.files}
        core = build_fs_repository_set(workspace_root=base).core
        meta_path = core._source_meta_path_for_read("TSM", document_id, SourceKind.FILING)
        manifest_path = core._filing_manifest_path_for_read("TSM")
        store = LocalFileStore(base)
        meta_bytes = store.get_object(str(meta_path.relative_to(base))).read()
        manifest_bytes = store.get_object(str(manifest_path.relative_to(base))).read()
        manifest = cast(JsonValue, json.loads(manifest_bytes))
        manifest_rows = _rows(_mapping(manifest)["documents"])
        target_row = next(row for row in manifest_rows if row["document_id"] == document_id)
        return {"meta": metadata, "revision": snapshot.revision.token, "files": observed,
                "primary": snapshot.primary_filename, "manifest_row": target_row,
                "meta_sha256": hashlib.sha256(meta_bytes).hexdigest(),
                "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()}


def _observations(path: Path) -> list[dict[str, JsonValue]]:
    """参数为临时 observer 路径；返回所有非敏感事实；缺席或 JSON 错误时失败。"""
    assert path.is_file(), "子进程 observer 未启动"
    return [_mapping(cast(JsonValue, json.loads(line))) for line in path.read_text().splitlines()]


def _run_cli(context: _Context, year: str, accession: str, mode: str, base: Path, *,
             baseline: bool = False, fault: str | None = None) -> dict[str, JsonValue]:
    """参数为 CLI 模式、base 与 exact transport fault；保存 argv/两通道/log/exit/观测；入口失败透传。"""
    evidence = context.root / "evidence" / (year + "-" + mode)
    evidence.mkdir()
    argv = [str(_REPO / ".venv/bin/python"), "-m", "dayu.cli.__main__"] if baseline else [str(context.cli)]
    day = context.filings[accession].filing_date
    argv += ["download", "--base", str(base), "--ticker", "TSM", "--forms", "6-K", "--start", day,
             "--end", day, "--log-file", str(evidence / "operator.log")]
    env = dict(context.environment)
    env["PYTHONPATH"] = os.pathsep.join((str(context.baseline if baseline else _REPO), str(context.root / "hooks")))
    env["DAYU_SEC_IMAGE_OBSERVER"] = str(evidence / "observer.jsonl")
    env["DAYU_SEC_IMAGE_ARCHIVE"] = "https://www.sec.gov/Archives/edgar/data/1046179/" + accession.replace("-", "") + "/"
    env["DAYU_SEC_IMAGE_FAULT"] = fault or ""
    cwd = context.baseline if baseline else _REPO
    completed = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=900)
    (evidence / "stdout.txt").write_text(completed.stdout)
    (evidence / "stderr.txt").write_text(completed.stderr)
    result: dict[str, JsonValue] = {"argv": cast(JsonValue, argv), "cwd": str(cwd), "base": str(base),
                                 "exit_code": completed.returncode, "evidence": str(evidence), "fault": fault}
    _write_json(evidence / "command.json", result)
    lines = [line.removeprefix(_DIAGNOSTICS_PREFIX) for line in (completed.stdout + "\n" + completed.stderr).splitlines()
             if line.startswith(_DIAGNOSTICS_PREFIX)]
    assert len(lines) == 1, f"真实 CLI 诊断缺席；证据：{evidence}"
    diagnostics = _mapping(cast(JsonValue, json.loads(lines[0])))
    result["diagnostics"] = diagnostics
    observations = _observations(evidence / "observer.jsonl")
    origins = [row for row in observations if row["kind"] == "origin"]
    assert len(origins) == 1
    origin = origins[0]
    assert origin["download_version"] == (_OLD_VERSION if baseline else SEC_PIPELINE_DOWNLOAD_VERSION)
    assert origin["package_version"] == "0.1.4"
    expected_root = context.baseline if baseline else _REPO
    for name in ("dayu", "sec_pipeline"):
        value = origin[name]
        assert isinstance(value, str) and Path(value).is_relative_to(expected_root)
    assert origin["sec_downloader_sha256"] == hashlib.sha256((expected_root / _PRODUCER_PATHS[0]).read_bytes()).hexdigest()
    result["origin"] = origin
    result["observations"] = cast(JsonValue, observations)
    _write_json(evidence / "command.json", result)
    return result


def _assert_target(result: dict[str, JsonValue], accession: str, disposition: str) -> None:
    """参数为真实命令结果与目标终态；返回无；target/计数/退出语义不符时失败。"""
    diagnostics = _mapping(result["diagnostics"])
    summary = _mapping(diagnostics["summary"])
    counts = _mapping(summary["counts"])
    assert counts["discovered"] == sum(cast(int, counts[key]) for key in ("downloaded", "skipped", "rejected", "failed", "uncertain"))
    document_id = "fil_" + accession
    if disposition == "failed":
        failed = [row for row in _rows(diagnostics["failed_documents"]) if row["document_id"] == document_id]
        assert len(failed) == 1 and failed[0]["reason_category"] == "file_download_failed"
        assert result["exit_code"] == (0 if counts["downloaded"] or counts["skipped"] else 1)
    else:
        rows = [row for row in _rows(summary["documents"]) if row["document_id"] == document_id]
        assert len(rows) == 1 and rows[0]["disposition"] == disposition
        assert result["exit_code"] == 0
        assert not any(row["document_id"] == document_id for row in _rows(diagnostics["failed_documents"]))


def _assert_fingerprint(result: dict[str, JsonValue], snapshot: dict[str, JsonValue]) -> None:
    """参数为 descriptor 观测与仓储 snapshot；重算同一次完整指纹；缺图或不一致时失败。"""
    names = {str(row["name"]) for row in _rows(snapshot["files"])}
    matches = []
    for observation in _rows(result["observations"]):
        if observation["kind"] != "fingerprint":
            continue
        rows = _rows(observation["descriptors"])
        if {str(row["name"]) for row in rows} != names:
            continue
        descriptors = [RemoteFileDescriptor(
            name=cast(str, row["name"]), source_url=cast(str, row["source_url"]),
            http_etag=cast(str | None, row["http_etag"]), http_last_modified=cast(str | None, row["http_last_modified"]),
            remote_size=cast(int | None, row["remote_size"]),
        ) for row in rows]
        assert build_source_fingerprint(descriptors) == observation["fingerprint"] == _mapping(snapshot["meta"])["source_fingerprint"]
        matches.append(observation)
    assert matches, "published 指纹没有对应完整真实 descriptor 观测"


def _check_images(context: _Context, base: Path, accession: str, html: str, references: int, unique: int) -> tuple[set[str], dict[str, JsonValue]]:
    """参数为正式目标与样例计数；返回全 filing 图片集及分栏逐图证据；引用/hash/URI 不一致时失败。"""
    source = FsSourceDocumentRepository(base)
    with source.get_source("TSM", "fil_" + accession, SourceKind.FILING, html).open() as stream:
        payload = stream.read()
    parser = _RealFlatImages()
    parser.feed(payload.decode("utf-8"))
    assert len(parser.references) == references and len(set(parser.references)) == unique
    snapshot = _snapshot(context, base, accession)
    names = {str(row["name"]) for row in _rows(snapshot["files"])}
    assert set(parser.references) <= names
    preflight = _read_json(_REPO / "docs/validation/sec-html-image-assets-remote-preflight.json")
    expected = next(row for row in _rows(preflight["samples"]) if row["accession"] == accession)
    observed = {str(row["name"]): row for row in _rows(snapshot["files"])}
    assert observed[html]["sha256"] == expected["local_html_sha256"]
    for remote in _rows(expected["remote"]):
        url = cast(str, remote["url"])
        assert observed[url.rsplit("/", 1)[-1]]["sha256"] == remote["sha256"]
    target_images = set(parser.references)
    filing_images: set[str] = set()
    html_rows: list[JsonValue] = []
    for filename in sorted(names):
        if not filename.lower().endswith((".htm", ".html")):
            continue
        with source.get_source("TSM", "fil_" + accession, SourceKind.FILING, filename).open() as stream:
            selected_payload = stream.read()
        selected = _RealFlatImages()
        selected.feed(selected_payload.decode("utf-8"))
        selected.close()
        selected_names = set(selected.references)
        selected_names_json: list[JsonValue] = [name for name in sorted(selected_names)]
        assert selected_names <= names
        filing_images.update(selected_names)
        html_rows.append({"name": filename, "sha256": observed[filename]["sha256"],
                          "reference_count": len(selected.references), "image_names": selected_names_json})
    assert len(filing_images) == _FILING_UNIQUE_IMAGES[html]
    assert names == {str(row["name"]) for row in _rows(cast(JsonValue, html_rows))} | filing_images
    archive = "https://www.sec.gov/Archives/edgar/data/1046179/" + accession.replace("-", "") + "/"
    entries = {str(row["name"]): row for row in _rows(_mapping(snapshot["meta"])["files"])}
    image_rows: list[JsonValue] = []
    for name in sorted(filing_images):
        canonical = archive + quote(name, safe="")
        assert entries[name]["source_url"] == canonical
        image_rows.append({**observed[name], "source_url": canonical, "in_target_html": name in target_images})
    target_names_json: list[JsonValue] = [name for name in sorted(target_images)]
    additional_names_json: list[JsonValue] = [name for name in sorted(filing_images - target_images)]
    target_check: dict[str, JsonValue] = {
        "name": html, "reference_count": references, "unique_images": len(target_images), "image_names": target_names_json,
    }
    filing_check: dict[str, JsonValue] = {
        "unique_images": len(filing_images), "additional_image_names": additional_names_json,
        "selected_html": html_rows, "images": image_rows,
    }
    return filing_images, {"target_html": target_check, "complete_filing": filing_check}


def _assert_image_gets(result: dict[str, JsonValue], image_check: dict[str, JsonValue]) -> None:
    """参数为真实命令观测及全 filing 证据；返回无；未逐图 exact GET 或重复 GET 时失败。"""
    images = _rows(_mapping(image_check["complete_filing"])["images"])
    expected = {str(row["source_url"]) for row in images}
    observed = [row for row in _rows(result["observations"]) if row["kind"] == "transport" and row["method"] == "GET" and row["url"] in expected]
    assert len(observed) == len(expected) and {str(row["url"]) for row in observed} == expected
    assert all(row["status"] == 200 and row["fault"] is False for row in observed)


@pytest.mark.parametrize("year,accession,html,references,unique", _SAMPLES, ids=["2019", "2025"])
def test_real_cli_matrix(real_context: _Context, year: str, accession: str, html: str, references: int, unique: int) -> None:
    """参数为 opt-in 配置与正式样例；验证 fresh/旧版升级/重复/故障/保留/retry；任一必要断言失败。"""
    context = real_context
    commands: list[JsonValue] = []
    snapshots: dict[str, JsonValue] = {}
    image_checks: dict[str, JsonValue] = {}
    sample: dict[str, JsonValue] = {"year": year, "accession": accession, "html": html,
                                   "filing_date": context.filings[accession].filing_date, "commands": commands,
                                   "snapshots": snapshots, "image_checks": image_checks,
                                   "producer_hashes": _producer_hashes(), "status": "in_progress"}
    outcome = context.root / "evidence" / ("real-" + year + ".json")
    try:
        fresh = context.root / ("fresh-" + year)
        assert not fresh.exists()
        result = _run_cli(context, year, accession, "fresh", fresh)
        commands.append(result)
        _assert_target(result, accession, "downloaded")
        images, image_check = _check_images(context, fresh, accession, html, references, unique)
        image_checks["fresh"] = image_check
        _assert_image_gets(result, image_check)
        snapshot = _snapshot(context, fresh, accession)
        snapshots["fresh"] = snapshot
        assert _mapping(snapshot["meta"])["download_version"] == SEC_PIPELINE_DOWNLOAD_VERSION
        assert _mapping(snapshot["meta"])["document_version"] == "v1"
        _assert_fingerprint(result, snapshot)
        for base_kind in ("upgrade", "failure-upgrade"):
            base = context.root / (base_kind + "-" + year)
            assert not base.exists()
            old_result = _run_cli(context, year, accession, base_kind + "-seed", base, baseline=True)
            commands.append(old_result)
            _assert_target(old_result, accession, "downloaded")
            old = _snapshot(context, base, accession)
            snapshots[base_kind + "-old"] = old
            old_meta = _mapping(old["meta"])
            assert old_meta["download_version"] == _OLD_VERSION and old_meta["source_fingerprint"]
            assert not (images & {str(row["name"]) for row in _rows(old["files"])})
            _assert_fingerprint(old_result, old)
            if base_kind == "failure-upgrade":
                fault = urljoin("https://www.sec.gov/Archives/edgar/data/1046179/" + accession.replace("-", "") + "/", sorted(images)[0])
                failed = _run_cli(context, year, accession, "failure-upgrade", base, fault=fault)
                commands.append(failed)
                _assert_target(failed, accession, "failed")
                assert any(row["kind"] == "transport" and row.get("fault") is True for row in _rows(failed["observations"]))
                assert _snapshot(context, base, accession) == old
                log = Path(cast(str, failed["evidence"])) / "operator.log"
                assert sorted(images)[0] in log.read_text() and "provider_http_status" in log.read_text()
                snapshots["failure-upgrade-preserved"] = _snapshot(context, base, accession)
            result = _run_cli(context, year, accession, base_kind + "-success", base)
            commands.append(result)
            _assert_target(result, accession, "downloaded")
            _, image_check = _check_images(context, base, accession, html, references, unique)
            image_checks[base_kind + "-new"] = image_check
            _assert_image_gets(result, image_check)
            new = _snapshot(context, base, accession)
            snapshots[base_kind + "-new"] = new
            new_meta = _mapping(new["meta"])
            assert new_meta["download_version"] == SEC_PIPELINE_DOWNLOAD_VERSION
            assert new_meta["source_fingerprint"] != old_meta["source_fingerprint"]
            assert new_meta["document_version"] == "v" + str(int(cast(str, old_meta["document_version"])[1:]) + 1)
            for key in ("first_ingested_at", "created_at"):
                assert new_meta[key] == old_meta[key]
            assert new["primary"] == old["primary"]
            _assert_fingerprint(result, new)
        base = context.root / ("failure-fresh-" + year)
        fault = urljoin("https://www.sec.gov/Archives/edgar/data/1046179/" + accession.replace("-", "") + "/", sorted(images)[0])
        assert not base.exists()
        failed = _run_cli(context, year, accession, "failure-fresh", base, fault=fault)
        commands.append(failed)
        _assert_target(failed, accession, "failed")
        assert any(row["kind"] == "transport" and row.get("fault") is True for row in _rows(failed["observations"]))
        log = Path(cast(str, failed["evidence"])) / "operator.log"
        assert sorted(images)[0] in log.read_text() and "provider_http_status" in log.read_text()
        assert FsSourceDocumentRepository(base).classify_source_integrity("TSM", "fil_" + accession, SourceKind.FILING).status is SourceIntegrityStatus.MISSING
        result = _run_cli(context, year, accession, "failure-fresh-retry", base)
        commands.append(result)
        _assert_target(result, accession, "downloaded")
        _, image_check = _check_images(context, base, accession, html, references, unique)
        image_checks["failure-fresh-retry"] = image_check
        _assert_image_gets(result, image_check)
        _assert_fingerprint(result, _snapshot(context, base, accession))
        snapshots["failure-fresh-retry"] = _snapshot(context, base, accession)
        for base_kind in ("fresh", "upgrade", "failure-upgrade", "failure-fresh"):
            base = context.root / (base_kind + "-" + year)
            before = _snapshot(context, base, accession)
            result = _run_cli(context, year, accession, base_kind + "-repeat", base)
            commands.append(result)
            _assert_target(result, accession, "skipped")
            assert not [row for row in _rows(result["observations"]) if row["kind"] == "transport"]
            assert _snapshot(context, base, accession) == before
            snapshots[base_kind + "-repeat"] = before
        sample["status"] = "passed"
        sample["image_references"] = references
        sample["unique_images"] = unique
        sample["complete_filing_unique_images"] = len(images)
        sample["assertions"] = ["fresh", "formal-baseline", "ordinary-upgrade", "descriptor-fingerprint", "uri-size-sha256",
                                "document-version", "idempotence-zero-target-transport", "get404-fresh-missing",
                                "get404-upgrade-publication-preserved", "fault-hit", "diagnostics", "retry"]
    finally:
        _write_json(outcome, sample)
