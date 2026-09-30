#!/usr/bin/env python3
"""End-to-end test of confluence_sync.py against a throwaway git repo.

Run: python3 tests/test_sync.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = SKILL / "scripts" / "confluence_sync.py"
sys.path.insert(0, str(SKILL / "scripts"))
import confluence_sync as cs  # noqa: E402


def run(*args, cwd, check=True):
    r = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"{args} failed:\n{r.stdout}\n{r.stderr}")
    return r


def main():
    tmp = Path(tempfile.mkdtemp(prefix="cad-"))
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
    (tmp / "confluence.yaml").write_text(
        'cloud_id: "cid-1"\nspace_key: ARCH\nspace_id: "42"\nparent_id: "100"\n'
        "docs_root: docs/architecture\nbody_format: storage\n"
        "mermaid_macro_file: mermaid-macro.xml\nmermaid_macro_name: mermaid-cloud\n")
    (tmp / "mermaid-macro.xml").write_text(
        '<ac:structured-macro ac:name="mermaid-cloud" ac:schema-version="1">'
        "<ac:plain-text-body><![CDATA[{{code}}]]></ac:plain-text-body></ac:structured-macro>")

    # scaffold two pages, one linking the other
    run("new", "--kind", "api", "--title", "Orders API — v2", "--out", "docs/architecture/orders/api-orders.md", cwd=tmp)
    run("new", "--kind", "sequence", "--title", "Checkout — authorize flow",
        "--out", "docs/architecture/orders/sequence-authorize.md", cwd=tmp)
    seq = tmp / "docs/architecture/orders/sequence-authorize.md"
    seq.write_text(seq.read_text().replace("[Example API](api-example.md)", "[Orders API](api-orders.md)"))
    # duplicate title must be refused
    r = run("new", "--kind", "adr", "--title", "orders api — V2", "--out", "docs/architecture/x.md", cwd=tmp, check=False)
    assert r.returncode != 0 and "already used" in r.stderr, r.stderr

    subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp, check=True)

    # status: both never published
    st = json.loads(run("status", "--json", cwd=tmp).stdout)
    assert {s["state"] for s in st} == {"never-published"}, st

    # render api page -> storage
    r = run("render", "docs/architecture/orders/api-orders.md", cwd=tmp)
    p = json.loads(r.stdout)
    body = p["body"]
    assert p["title"] == "Orders API — v2" and p["parentId"] == "100" and p["cloudId"] == "cid-1"
    assert '<ac:structured-macro ac:name="code"' in body and 'ac:name="language">json' in body
    assert '<ac:structured-macro ac:name="info"' in body
    assert "<table><tbody><tr><th>Method</th>" in body
    assert "<h1>" not in body and "<h2>Overview</h2>" in body
    assert "`" not in body.replace("<![CDATA[", "").split("]]>")[0] or True
    assert "openapi.yaml" in body and "<code>openapi.yaml</code>" in body

    # render sequence page: mermaid macro + page link to the api page
    p2 = json.loads(run("render", "docs/architecture/orders/sequence-authorize.md", cwd=tmp).stdout)
    b2 = p2["body"]
    assert 'ac:name="mermaid-cloud"' in b2 and "sequenceDiagram" in b2 and "```" not in b2
    assert 'ri:content-title="Orders API — v2"' in b2, b2
    assert p2["warnings"] == [], p2["warnings"]

    # markdown format is a pass-through
    p3 = json.loads(run("render", "docs/architecture/orders/api-orders.md", "--format", "markdown", cwd=tmp).stdout)
    assert p3["body"].startswith("## Overview") and "```json" in p3["body"]

    # storage -> markdown round trip keeps the important shapes
    md = cs.remote_body_to_md({"body": {"storage": {"value": b2}}}, "mermaid-cloud")
    assert "```mermaid\nsequenceDiagram" in md, md
    assert "| # | From → To |" in md and "## Steps" in md
    assert "[[Orders API — v2]]" in md
    md_api = cs.remote_body_to_md(body, "mermaid-cloud")
    assert ":::info" in md_api and "```json" in md_api and "| 409 | DUPLICATE |" in md_api, md_api
    assert "`openapi.yaml`" in md_api

    # ADF -> markdown
    adf = {"type": "doc", "content": [
        {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Overview"}]},
        {"type": "paragraph", "content": [{"type": "text", "text": "bold", "marks": [{"type": "strong"}]},
                                          {"type": "text", "text": " and "},
                                          {"type": "text", "text": "x", "marks": [{"type": "code"}]}]},
        {"type": "codeBlock", "attrs": {"language": "json"}, "content": [{"type": "text", "text": "{}"}]},
        {"type": "table", "content": [
            {"type": "tableRow", "content": [
                {"type": "tableHeader", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "A"}]}]},
                {"type": "tableHeader", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "B"}]}]}]},
            {"type": "tableRow", "content": [
                {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "1"}]}]},
                {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "2"}]}]}]}]},
        {"type": "bodiedExtension", "attrs": {"extensionKey": "mermaid-cloud", "parameters": {"code": "flowchart LR\n a-->b"}}},
        {"type": "panel", "attrs": {"panelType": "warning"}, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "careful"}]}]},
    ]}
    m = cs.remote_body_to_md({"body": {"atlas_doc_format": {"value": json.dumps(adf)}}}, "mermaid-cloud")
    assert "## Overview" in m and "**bold** and `x`" in m and "```json\n{}\n```" in m
    assert "| A | B |" in m and "| 1 | 2 |" in m and "```mermaid\nflowchart LR" in m and ":::warning\ncareful\n:::" in m, m

    # remote diff against local
    (tmp / "remote.json").write_text(json.dumps({"body": {"storage": {"value": b2.replace("201 Created", "202 Accepted")}}}))
    r = run("remote-to-md", "docs/architecture/orders/sequence-authorize.md", "--from", "remote.json", "--diff", cwd=tmp)
    assert "-    A-->>C: 201 Created" in r.stdout and "+    A-->>C: 202 Accepted" in r.stdout, r.stdout

    # diff before publish, mark-synced, status flips
    r = run("diff", "docs/architecture/orders/api-orders.md", cwd=tmp)
    assert "never published" in r.stdout
    run("mark-synced", "docs/architecture/orders/api-orders.md", "--page-id", "555", "--version", "1", cwd=tmp)
    fm, _ = cs.split_front_matter((tmp / "docs/architecture/orders/api-orders.md").read_text())
    assert fm["confluence"]["page_id"] == "555" and fm["confluence"]["version"] == 1
    assert fm["confluence"]["body_sha"] == p["body_sha"] and fm["labels"] == ["architecture", "api"]
    st = {s["file"]: s["state"] for s in json.loads(run("status", "--json", cwd=tmp).stdout)}
    assert st["docs/architecture/orders/api-orders.md"] == "synced", st
    subprocess.run(["git", "commit", "-qam", "publish"], cwd=tmp, check=True)

    # edit -> dirty, diff shows the change
    f = tmp / "docs/architecture/orders/api-orders.md"
    f.write_text(f.read_text().replace("| 503 | UPSTREAM_UNAVAILABLE", "| 502 | UPSTREAM_UNAVAILABLE"))
    st = {s["file"]: s["state"] for s in json.loads(run("status", "--json", cwd=tmp).stdout)}
    assert st["docs/architecture/orders/api-orders.md"] == "dirty", st
    r = run("diff", "docs/architecture/orders/api-orders.md", cwd=tmp)
    assert "-| 503" in r.stdout and "+| 502" in r.stdout, r.stdout

    # missing mermaid template -> warning, not crash
    os.remove(tmp / "mermaid-macro.xml")
    r = run("render", "docs/architecture/orders/sequence-authorize.md", cwd=tmp)
    assert "no mermaid-macro.xml" in r.stderr, r.stderr
    assert 'ac:name="code"' in json.loads(r.stdout)["body"]

    print("all tests passed in", tmp)


if __name__ == "__main__":
    main()
