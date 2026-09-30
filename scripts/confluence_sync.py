#!/usr/bin/env python3
"""Sync markdown architecture docs with Confluence via gateway MCP tools.

The script never talks to Confluence itself: it prepares payloads for the
Atlassian MCP tools exposed by the LiteLLM AI gateway and records the result
after the agent has called them. Stdlib only (works on /usr/bin/python3 3.9+).

Commands:
  status                              list docs and their sync state
  new --kind K --title T --out PATH    scaffold a page from templates/
  render FILE [--format F]            JSON payload for create/updateConfluencePage
  diff FILE                           local change since last sync (git)
  remote-to-md FILE --from JSON       convert a getConfluencePage body to markdown
  mark-synced FILE --page-id ID --version N
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_NAME = "confluence.yaml"
PANEL_TYPES = ("info", "note", "warning", "tip", "error")


# ----------------------------------------------------------------------------
# Minimal YAML (front matter + config). Supports scalars, flow lists
# ([a, b]), block lists (- a) and one level of nested mapping.
# ----------------------------------------------------------------------------

def _scalar(v: str) -> Any:
    v = v.strip()
    if v == "" or v == "~" or v == "null":
        return None
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [_scalar(x) for x in inner.split(",")] if inner else []
    if v in ("true", "false"):
        return v == "true"
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    return v


def parse_yaml(text: str) -> Dict[str, Any]:
    root: Dict[str, Any] = {}
    stack: List[Tuple[int, Any]] = [(-1, root)]
    last_key: Optional[str] = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        container = stack[-1][1]
        if line.startswith("- "):
            if not isinstance(container, list):
                if last_key is None:
                    raise ValueError("list item without a key")
                parent = stack[-2][1] if len(stack) > 1 else root
                lst: List[Any] = []
                parent[last_key] = lst
                stack.append((indent, lst))
                container = lst
            container.append(_scalar(line[2:]))
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        if val.strip() == "":
            child: Dict[str, Any] = {}
            container[key] = child
            stack.append((indent, child))
            last_key = key
        else:
            container[key] = _scalar(val)
            last_key = key
    return root


def dump_yaml(d: Dict[str, Any], indent: int = 0) -> str:
    out = []
    pad = " " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            out.append(f"{pad}{k}:")
            out.append(dump_yaml(v, indent + 2))
        elif isinstance(v, list):
            out.append(f"{pad}{k}: [{', '.join(str(x) for x in v)}]")
        elif v is None:
            out.append(f"{pad}{k}:")
        elif isinstance(v, str) and (re.search(r"[:#\[\]{}]", v) or v.isdigit() or v == ""):
            out.append(f'{pad}{k}: "{v}"')
        else:
            out.append(f"{pad}{k}: {v}")
    return "\n".join(x for x in out if x != "")


# ----------------------------------------------------------------------------
# Config + front matter
# ----------------------------------------------------------------------------

def find_repo_root(start: Path) -> Path:
    p = start.resolve()
    for cand in [p] + list(p.parents):
        if (cand / CONFIG_NAME).exists():
            return cand
    sys.exit(f"{CONFIG_NAME} not found above {start}; run setup first")


def load_config(root: Path) -> Dict[str, Any]:
    cfg = parse_yaml((root / CONFIG_NAME).read_text())
    cfg.setdefault("docs_root", "docs/architecture")
    cfg.setdefault("body_format", "storage")
    cfg.setdefault("mermaid_macro_file", "mermaid-macro.xml")
    return cfg


def split_front_matter(text: str) -> Tuple[Dict[str, Any], str]:
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    if not m:
        return {}, text
    return parse_yaml(m.group(1)), text[m.end():]


def join_front_matter(fm: Dict[str, Any], body: str) -> str:
    return "---\n" + dump_yaml(fm) + "\n---\n" + body


def doc_files(root: Path, cfg: Dict[str, Any]) -> List[Path]:
    base = root / cfg["docs_root"]
    return sorted(p for p in base.rglob("*.md"))


# ----------------------------------------------------------------------------
# Markdown -> Confluence storage XML
# ----------------------------------------------------------------------------

class Renderer:
    def __init__(self, root: Path, cfg: Dict[str, Any], src: Path):
        self.root, self.cfg, self.src = root, cfg, src
        self.warnings: List[str] = []
        self.titles = self._title_index()
        mf = root / cfg["mermaid_macro_file"]
        self.mermaid_tpl = mf.read_text() if mf.exists() else None

    def _title_index(self) -> Dict[Path, str]:
        idx = {}
        for f in doc_files(self.root, self.cfg):
            fm, _ = split_front_matter(f.read_text())
            if fm.get("title"):
                idx[f.resolve()] = fm["title"]
        return idx

    # --- inline ---------------------------------------------------------
    def inline(self, s: str) -> str:
        codes: List[str] = []

        def stash(m):
            codes.append(f"<code>{html.escape(m.group(1))}</code>")
            return f"\x00{len(codes) - 1}\x00"

        s = re.sub(r"`([^`]+)`", stash, s)
        s = html.escape(s, quote=False)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
        s = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"<em>\1</em>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", self._link, s)
        s = re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], s)
        return s

    def _link(self, m) -> str:
        text, target = m.group(1), html.unescape(m.group(2))
        if re.match(r"^[a-z]+://|^mailto:|^#", target):
            return f'<a href="{html.escape(target)}">{text}</a>'
        path = (self.src.parent / target.split("#")[0]).resolve()
        title = self.titles.get(path)
        if not title:
            self.warnings.append(f"link target not a known doc: {target}")
            return text
        return (f'<ac:link><ri:page ri:content-title="{html.escape(title)}"/>'
                f"<ac:plain-text-link-body><![CDATA[{html.unescape(text)}]]>"
                f"</ac:plain-text-link-body></ac:link>")

    # --- blocks ---------------------------------------------------------
    def render(self, body: str) -> str:
        lines = body.split("\n")
        out: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            if line.startswith("```"):
                lang = line[3:].strip()
                j = i + 1
                buf = []
                while j < len(lines) and not lines[j].startswith("```"):
                    buf.append(lines[j])
                    j += 1
                out.append(self.code_block(lang, "\n".join(buf)))
                i = j + 1
                continue
            if line.startswith(":::"):
                kind = line[3:].strip() or "info"
                j = i + 1
                buf = []
                while j < len(lines) and not lines[j].startswith(":::"):
                    buf.append(lines[j])
                    j += 1
                if kind not in PANEL_TYPES:
                    self.warnings.append(f"unknown panel type {kind}, using info")
                    kind = "info"
                out.append(f'<ac:structured-macro ac:name="{kind}" ac:schema-version="1">'
                           f"<ac:rich-text-body>{self.render(chr(10).join(buf))}"
                           "</ac:rich-text-body></ac:structured-macro>")
                i = j + 1
                continue
            m = re.match(r"^(#{1,6})\s+(.*)$", line)
            if m:
                lvl = len(m.group(1))
                if lvl == 1:
                    self.warnings.append("h1 in body; title comes from front matter, use ## and below")
                out.append(f"<h{lvl}>{self.inline(m.group(2))}</h{lvl}>")
                i += 1
                continue
            if re.match(r"^(-{3,}|\*{3,})\s*$", line):
                out.append("<hr/>")
                i += 1
                continue
            if line.startswith("|"):
                j = i
                rows = []
                while j < len(lines) and lines[j].startswith("|"):
                    rows.append(lines[j])
                    j += 1
                out.append(self.table(rows))
                i = j
                continue
            if re.match(r"^\s*([-*+]|\d+\.)\s+", line):
                j = i
                buf = []
                while j < len(lines) and (re.match(r"^\s*([-*+]|\d+\.)\s+", lines[j]) or
                                          (lines[j].startswith("  ") and lines[j].strip())):
                    buf.append(lines[j])
                    j += 1
                out.append(self.list_block(buf))
                i = j
                continue
            if line.startswith(">"):
                j = i
                buf = []
                while j < len(lines) and lines[j].startswith(">"):
                    buf.append(lines[j][1:].lstrip())
                    j += 1
                out.append(f"<blockquote>{self.render(chr(10).join(buf))}</blockquote>")
                i = j
                continue
            j = i
            buf = []
            while j < len(lines) and lines[j].strip() and not re.match(
                    r"^(#{1,6}\s|```|:::|\||>|\s*([-*+]|\d+\.)\s)", lines[j]):
                buf.append(lines[j].strip())
                j += 1
            out.append(f"<p>{self.inline(' '.join(buf))}</p>")
            i = j
        return "".join(out)

    def code_block(self, lang: str, code: str) -> str:
        if lang == "mermaid":
            if not self.mermaid_tpl:
                self.warnings.append("mermaid block but no mermaid-macro.xml template; emitted as code macro")
                lang = "text"
            else:
                return self.mermaid_tpl.replace("{{code}}", code)
        lang = lang or "text"
        return (f'<ac:structured-macro ac:name="code" ac:schema-version="1">'
                f'<ac:parameter ac:name="language">{html.escape(lang)}</ac:parameter>'
                f"<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body></ac:structured-macro>")

    def table(self, rows: List[str]) -> str:
        cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
        if len(cells) > 1 and all(re.fullmatch(r":?-+:?", c) for c in cells[1]):
            header, body = cells[0], cells[2:]
        else:
            header, body = None, cells
        out = ["<table><tbody>"]
        if header:
            out.append("<tr>" + "".join(f"<th>{self.inline(c)}</th>" for c in header) + "</tr>")
        for r in body:
            out.append("<tr>" + "".join(f"<td>{self.inline(c)}</td>" for c in r) + "</tr>")
        out.append("</tbody></table>")
        return "".join(out)

    def list_block(self, lines: List[str]) -> str:
        items: List[Tuple[int, bool, str]] = []
        for ln in lines:
            m = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", ln)
            if m:
                items.append((len(m.group(1)), m.group(2)[0].isdigit(), m.group(3)))
            elif items:
                d, o, t = items[-1]
                items[-1] = (d, o, t + " " + ln.strip())
        return self._nest(items, 0)[0]

    def _nest(self, items, pos) -> Tuple[str, int]:
        depth = items[pos][0]
        tag = "ol" if items[pos][1] else "ul"
        out = [f"<{tag}>"]
        while pos < len(items) and items[pos][0] == depth:
            out.append(f"<li>{self.inline(items[pos][2])}")
            pos += 1
            if pos < len(items) and items[pos][0] > depth:
                sub, pos = self._nest(items, pos)
                out.append(sub)
            out.append("</li>")
        out.append(f"</{tag}>")
        return "".join(out), pos


def render_markdown_body(body: str) -> str:
    """Pass-through for gateways whose update tool accepts markdown."""
    return body.strip() + "\n"


# ----------------------------------------------------------------------------
# Confluence storage XML / ADF -> markdown (for remote diff)
# ----------------------------------------------------------------------------

class StorageToMd(HTMLParser):
    def __init__(self, mermaid_macro: Optional[str]):
        super().__init__(convert_charrefs=True)
        self.out: List[str] = []
        self.stack: List[str] = []
        self.macro: List[Dict[str, Any]] = []
        self.list_stack: List[str] = []
        self.row: List[str] = []
        self.cell: Optional[List[str]] = None
        self.in_th = False
        self.table_rows: List[Tuple[bool, List[str]]] = []
        self.mermaid_macro = mermaid_macro
        self.param_name: Optional[str] = None

    def _w(self, s: str):
        if self.cell is not None:
            self.cell.append(s)
        else:
            self.out.append(s)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "ac:structured-macro":
            self.macro.append({"name": a.get("ac:name"), "params": {}, "body": []})
        elif tag == "ac:parameter" and self.macro:
            self.param_name = a.get("ac:name")
        elif tag == "ac:plain-text-body" and self.macro:
            self.stack.append("plain")
        elif tag == "ac:rich-text-body" and self.macro:
            m = self.macro[-1]
            self._w(f"\n:::{m['name']}\n")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._w("\n" + "#" * int(tag[1]) + " ")
        elif tag == "p":
            self._w("\n")
        elif tag in ("strong", "b"):
            self._w("**")
        elif tag in ("em", "i"):
            self._w("*")
        elif tag == "code":
            self._w("`")
        elif tag == "a":
            self.stack.append(a.get("href") or "")
            self._w("[")
        elif tag == "ri:page":
            self._w(f"[[{a.get('ri:content-title', '')}]]")
        elif tag in ("ul", "ol"):
            self.list_stack.append(tag)
        elif tag == "li":
            pad = "  " * (len(self.list_stack) - 1)
            mark = "1." if self.list_stack and self.list_stack[-1] == "ol" else "-"
            self._w(f"\n{pad}{mark} ")
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []
            self.in_th = tag == "th"
        elif tag == "hr":
            self._w("\n---\n")
        elif tag == "br":
            self._w("  \n")
        elif tag == "blockquote":
            self._w("\n> ")

    def handle_endtag(self, tag):
        if tag == "ac:structured-macro" and self.macro:
            m = self.macro.pop()
            name, params, body = m["name"], m["params"], "".join(m["body"])
            if name == "code":
                self._w(f"\n```{params.get('language', '')}\n{body}\n```\n")
            elif self.mermaid_macro and name == self.mermaid_macro:
                src = body or params.get("code") or params.get("source") or ""
                self._w(f"\n```mermaid\n{src}\n```\n")
            elif name in PANEL_TYPES:
                self._w("\n:::\n")
            else:
                self._w(f"\n<!-- macro:{name} {json.dumps(params)} -->\n")
        elif tag == "ac:parameter":
            self.param_name = None
        elif tag == "ac:plain-text-body":
            self.stack.pop()
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p"):
            self._w("\n")
        elif tag in ("strong", "b"):
            self._w("**")
        elif tag in ("em", "i"):
            self._w("*")
        elif tag == "code":
            self._w("`")
        elif tag == "a":
            href = self.stack.pop() if self.stack else ""
            self._w(f"]({href})")
        elif tag in ("ul", "ol"):
            self.list_stack.pop()
            if not self.list_stack:
                self._w("\n")
        elif tag in ("td", "th"):
            self.row.append("".join(self.cell or []).strip().replace("\n", " "))
            self.cell = None
        elif tag == "tr":
            self.table_rows.append((self.in_th, self.row))
            self.in_th = False
        elif tag == "table":
            self._flush_table()

    def _flush_table(self):
        if not self.table_rows:
            return
        rows = self.table_rows
        self.table_rows = []
        first_is_header, first = rows[0]
        if not first_is_header:
            first = [""] * len(first)
            rows = [(True, first)] + rows
        lines = ["| " + " | ".join(rows[0][1]) + " |",
                 "|" + "|".join(" --- " for _ in rows[0][1]) + "|"]
        for _, r in rows[1:]:
            lines.append("| " + " | ".join(r) + " |")
        self._w("\n" + "\n".join(lines) + "\n")

    def handle_data(self, data):
        if self.macro and self.param_name:
            self.macro[-1]["params"][self.param_name] = data
        elif self.macro and self.stack and self.stack[-1] == "plain":
            self.macro[-1]["body"].append(data)
        else:
            self._w(data)

    def unknown_decl(self, data):
        # HTMLParser hands <![CDATA[...]]> here as "CDATA[...".
        if data.startswith("CDATA["):
            self.handle_data(data[6:])

    def result(self) -> str:
        s = "".join(self.out)
        s = re.sub(r"[ \t]+\n", "\n", s)
        s = re.sub(r"\n{3,}", "\n\n", s)
        return s.strip() + "\n"


def adf_to_md(node: Dict[str, Any], depth: int = 0) -> str:
    t = node.get("type")
    kids = node.get("content", [])
    inner = lambda: "".join(adf_to_md(k, depth) for k in kids)  # noqa: E731
    if t == "doc":
        s = inner()
        return re.sub(r"\n{3,}", "\n\n", s).strip() + "\n"
    if t == "text":
        s = node.get("text", "")
        for m in node.get("marks", []):
            mt = m.get("type")
            if mt == "strong":
                s = f"**{s}**"
            elif mt == "em":
                s = f"*{s}*"
            elif mt == "code":
                s = f"`{s}`"
            elif mt == "link":
                s = f"[{s}]({m.get('attrs', {}).get('href', '')})"
        return s
    if t == "paragraph":
        return inner() + "\n\n"
    if t == "heading":
        return "#" * node.get("attrs", {}).get("level", 2) + " " + inner() + "\n\n"
    if t == "codeBlock":
        lang = node.get("attrs", {}).get("language", "") or ""
        return f"```{lang}\n{inner()}\n```\n\n"
    if t in ("bulletList", "orderedList"):
        mark = "1." if t == "orderedList" else "-"
        out = []
        for li in kids:
            body = "".join(adf_to_md(k, depth + 1) for k in li.get("content", [])).strip()
            body = body.replace("\n\n", "\n" + "  " * (depth + 1))
            out.append("  " * depth + f"{mark} {body}")
        return "\n".join(out) + "\n\n"
    if t == "table":
        rows = []
        for r in kids:
            cells = ["".join(adf_to_md(k, depth) for k in c.get("content", [])).strip().replace("\n", " ")
                     for c in r.get("content", [])]
            rows.append((r.get("content", [{}])[0].get("type") == "tableHeader", cells))
        if not rows:
            return ""
        lines = ["| " + " | ".join(rows[0][1]) + " |",
                 "|" + "|".join(" --- " for _ in rows[0][1]) + "|"]
        lines += ["| " + " | ".join(c) + " |" for _, c in rows[1:]]
        return "\n".join(lines) + "\n\n"
    if t == "panel":
        return f":::{node.get('attrs', {}).get('panelType', 'info')}\n{inner().strip()}\n:::\n\n"
    if t == "rule":
        return "---\n\n"
    if t == "hardBreak":
        return "  \n"
    if t == "blockquote":
        return "> " + inner().strip().replace("\n", "\n> ") + "\n\n"
    if t in ("extension", "bodiedExtension", "inlineExtension"):
        attrs = node.get("attrs", {})
        key = attrs.get("extensionKey", "")
        params = attrs.get("parameters", {}) or {}
        if "mermaid" in key.lower():
            src = (params.get("macroParams", {}) or {}).get("code", {}).get("value") if isinstance(
                params.get("macroParams"), dict) else None
            src = src or params.get("code") or params.get("source") or ""
            return f"```mermaid\n{src}\n```\n\n"
        return f"<!-- extension:{key} {json.dumps(params)[:200]} -->\n\n"
    if t in ("listItem", "tableRow", "tableCell", "tableHeader", "expand", "nestedExpand"):
        return inner()
    if t == "mention":
        return "@" + node.get("attrs", {}).get("text", "").lstrip("@")
    if t == "inlineCard":
        return node.get("attrs", {}).get("url", "")
    return inner()


def remote_body_to_md(payload: Any, mermaid_macro: Optional[str]) -> str:
    """Accept whatever getConfluencePage returned: a dict with body.*.value,
    a raw ADF dict, a storage XML string, or a JSON string of either."""
    if isinstance(payload, str):
        s = payload.strip()
        if s.startswith("{"):
            payload = json.loads(s)
        else:
            p = StorageToMd(mermaid_macro)
            p.feed(s)
            return p.result()
    if isinstance(payload, dict):
        body = payload.get("body", payload)
        for key in ("atlas_doc_format", "storage", "view"):
            if isinstance(body, dict) and key in body:
                val = body[key].get("value") if isinstance(body[key], dict) else body[key]
                return remote_body_to_md(val, mermaid_macro)
        if payload.get("type") == "doc":
            return adf_to_md(payload)
        if "value" in payload:
            return remote_body_to_md(payload["value"], mermaid_macro)
    sys.exit("could not find a page body in the remote payload")


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    return r.stdout.strip()


def render_payload(root: Path, cfg: Dict[str, Any], f: Path, fmt: str) -> Dict[str, Any]:
    fm, body = split_front_matter(f.read_text())
    if not fm.get("title"):
        sys.exit(f"{f}: front matter needs a title")
    r = Renderer(root, cfg, f)
    rendered = r.render(body) if fmt == "storage" else render_markdown_body(body)
    conf = fm.get("confluence", {}) or {}
    payload = {
        "cloudId": cfg.get("cloud_id"),
        "spaceId": cfg.get("space_id"),
        "spaceKey": cfg.get("space_key"),
        "parentId": conf.get("parent_id") or cfg.get("parent_id"),
        "pageId": conf.get("page_id") or None,
        "title": fm["title"],
        "labels": fm.get("labels", []),
        "contentFormat": fmt,
        "body": rendered,
        "body_sha": hashlib.sha256(rendered.encode()).hexdigest(),
        "body_bytes": len(rendered.encode()),
        "expected_remote_version": conf.get("version"),
        "warnings": r.warnings,
    }
    if payload["body_bytes"] > 15000:
        payload["warnings"].append(
            f"body is {payload['body_bytes']} bytes; gateway MCP tools often cap ~15-20KB, consider splitting")
    return payload


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------

def cmd_status(a):
    root = find_repo_root(Path.cwd())
    cfg = load_config(root)
    rows = []
    for f in doc_files(root, cfg):
        fm, _ = split_front_matter(f.read_text())
        conf = fm.get("confluence", {}) or {}
        try:
            p = render_payload(root, cfg, f, cfg["body_format"])
            dirty = p["body_sha"] != conf.get("body_sha")
        except SystemExit:
            dirty = True
        rows.append({
            "file": str(f.relative_to(root)),
            "title": fm.get("title"),
            "page_id": conf.get("page_id") or "",
            "version": conf.get("version") or "",
            "state": "never-published" if not conf.get("page_id") else ("dirty" if dirty else "synced"),
        })
    if a.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    w = max(len(r["file"]) for r in rows) if rows else 10
    for r in rows:
        print(f"{r['state']:16} {r['file']:{w}}  page={r['page_id'] or '-':10} v={r['version'] or '-'}  {r['title'] or ''}")


def cmd_new(a):
    root = find_repo_root(Path.cwd())
    cfg = load_config(root)
    tpl = SKILL_DIR / "templates" / f"{a.kind}.md"
    if not tpl.exists():
        sys.exit(f"no template for kind {a.kind}: {sorted(p.stem for p in (SKILL_DIR / 'templates').glob('*.md'))}")
    for f in doc_files(root, cfg):
        fm, _ = split_front_matter(f.read_text())
        if fm.get("title", "").lower() == a.title.lower():
            sys.exit(f"title already used by {f} (Confluence titles are unique per space)")
    out = Path(a.out)
    if out.exists():
        sys.exit(f"{out} exists")
    out.parent.mkdir(parents=True, exist_ok=True)
    text = tpl.read_text().replace("{{title}}", a.title).replace("{{date}}", dt.date.today().isoformat())
    out.write_text(text)
    print(out)


def cmd_render(a):
    root = find_repo_root(Path.cwd())
    cfg = load_config(root)
    p = render_payload(root, cfg, Path(a.file), a.format or cfg["body_format"])
    if a.body_only:
        print(p["body"])
    else:
        print(json.dumps(p, indent=2, ensure_ascii=False))
    for w in p["warnings"]:
        print("WARNING:", w, file=sys.stderr)


def cmd_diff(a):
    root = find_repo_root(Path.cwd())
    f = Path(a.file).resolve()
    fm, _ = split_front_matter(f.read_text())
    conf = fm.get("confluence", {}) or {}
    rel = str(f.relative_to(root))
    base = conf.get("synced_commit")
    if not base:
        print(f"never published; whole file is new ({rel})")
        print(git(root, "diff", "--no-index", "--", "/dev/null", rel) or f.read_text())
        return
    print(git(root, "diff", f"{base}", "--", rel) or "(no change since last sync)")


def cmd_remote_to_md(a):
    root = find_repo_root(Path.cwd())
    cfg = load_config(root)
    payload = Path(a.src).read_text()
    md = remote_body_to_md(payload, cfg.get("mermaid_macro_name"))
    if a.diff:
        _, local = split_front_matter(Path(a.file).read_text())
        import difflib
        for line in difflib.unified_diff(local.strip().splitlines(), md.strip().splitlines(),
                                         "local", "confluence", lineterm=""):
            print(line)
    else:
        print(md)


def cmd_mark_synced(a):
    root = find_repo_root(Path.cwd())
    cfg = load_config(root)
    f = Path(a.file).resolve()
    text = f.read_text()
    fm, body = split_front_matter(text)
    p = render_payload(root, cfg, f, cfg["body_format"])
    conf = fm.get("confluence", {}) or {}
    conf.update({
        "page_id": str(a.page_id),
        "version": int(a.version),
        "synced_commit": git(root, "rev-parse", "--short", "HEAD"),
        "synced_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "body_sha": p["body_sha"],
    })
    fm["confluence"] = conf
    f.write_text(join_front_matter(fm, body))
    print(f"{f.relative_to(root)}: page {a.page_id} v{a.version} recorded; commit this file")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_status)
    s = sub.add_parser("new"); s.add_argument("--kind", required=True); s.add_argument("--title", required=True)
    s.add_argument("--out", required=True); s.set_defaults(fn=cmd_new)
    s = sub.add_parser("render"); s.add_argument("file"); s.add_argument("--format", choices=["storage", "markdown"])
    s.add_argument("--body-only", action="store_true"); s.set_defaults(fn=cmd_render)
    s = sub.add_parser("diff"); s.add_argument("file"); s.set_defaults(fn=cmd_diff)
    s = sub.add_parser("remote-to-md"); s.add_argument("file"); s.add_argument("--from", dest="src", required=True)
    s.add_argument("--diff", action="store_true"); s.set_defaults(fn=cmd_remote_to_md)
    s = sub.add_parser("mark-synced"); s.add_argument("file"); s.add_argument("--page-id", required=True)
    s.add_argument("--version", required=True); s.set_defaults(fn=cmd_mark_synced)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
