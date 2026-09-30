---
name: confluence-arch-docs
description: Use when writing or publishing software architecture docs (sequence diagrams, APIs, contracts, ADRs) that live as markdown in a git repo and must stay in sync with Confluence through the LiteLLM AI gateway's Atlassian MCP tools. Local markdown is the source of truth; every Confluence write is previewed as a diff and confirmed; Rovo is search-only.
---

# Confluence architecture docs (docs-as-code, gateway-published)

Architecture documentation is written as markdown + mermaid in the repo and
published to Confluence through the Atlassian MCP tools exposed by the LiteLLM
AI gateway. There is no Confluence API token and no direct REST access: the
gateway tools are the only write path.

## Ground rules

1. `docs/architecture/**/*.md` in git is the single source of truth. Confluence
   is a rendered view of it. Never edit prose in Confluence and forget the repo.
2. Every Confluence write goes: render → diff → show the user → explicit "yes"
   → one `updateConfluencePage`/`createConfluencePage` call → `mark-synced`.
   No batch publishes without a per-page confirmation.
3. Rovo (`search`, `fetch`) is for finding pages and reading context. It never
   writes. Never paste generated prompts into Rovo to "improve layout": layout
   comes from `references/page-standards.md` and the gateway's
   `getContentFormatGuide`, applied deterministically by the render script.
4. Diagrams are mermaid source in fenced blocks. The gateway cannot upload
   attachments, so an image-based diagram cannot be published; keep diagrams as
   text (also the reason they stay diffable). Mermaid renders in Confluence
   through the space's mermaid macro (see `references/mermaid-macro.md`).
5. If a colleague edited a page in Confluence since the last sync, show the
   remote change as a diff against the local file and ask which way to merge.
   Never overwrite a newer remote version silently, never auto-merge.
6. Contracts (field names, status codes, enums, sequence steps) are copied
   literally from the markdown. Never let a summary or a rewrite touch them.

## Repo layout

```
confluence.yaml                    # cloudId, space, parent, body format, mermaid macro
docs/architecture/
  README.md                        # index page (lists children)
  <system>/
    context.md                     # C4-ish context + responsibilities
    sequence-<flow>.md             # one flow per page, mermaid sequenceDiagram
    api-<name>.md                  # endpoints, request/response, errors
    contract-<name>.md             # event/message contracts, schemas
    adr/NNNN-<slug>.md             # decisions
```

Each page file carries front matter:

```yaml
---
title: Orders API — v2
labels: [architecture, orders, api]
confluence:
  page_id: "123456"        # empty until first publish
  version: 7               # remote version at last sync
  synced_commit: abc1234   # git commit of the file at last sync
  synced_at: 2026-09-30T10:12:00-03:00
  body_sha: 9f2c…          # sha256 of rendered body at last sync
---
```

## One-time setup (per repo)

1. `cp templates/confluence.yaml ./confluence.yaml` and fill it in:
   - `cloud_id`: call `getAccessibleAtlassianResources` (or read it from an
     existing page URL via `fetch`).
   - `space_id` / `space_key`: `getConfluenceSpaces`.
   - `parent_id`: the page under which the architecture tree lives.
   - `body_format`: what `updateConfluencePage` accepts on this gateway. Run
     the tool search, read the schema of `updateConfluencePage` /
     `createConfluencePage`, and set `markdown` or `storage` accordingly.
     Prefer `storage` when available: it is the only format in which a mermaid
     macro and Confluence `code` macros can be emitted exactly.
2. Discover the mermaid macro shape: open any page in the space that already
   renders a mermaid diagram with `getConfluencePage` (storage format), copy the
   macro XML into `mermaid-macro.xml` replacing the diagram source with
   `{{code}}`. See `references/mermaid-macro.md`.
3. Cache the format guide: call `getContentFormatGuide` once and save the
   answer to `references/content-format-guide.md` (it is gateway/tenant
   specific and short). Re-run when the gateway is upgraded.
4. `python3 scripts/confluence_sync.py status` must run clean.

## Commands (all through `scripts/confluence_sync.py`)

| Command | What it does |
|---|---|
| `status` | Lists every doc: page_id, remote version, dirty (body changed since sync), never published. |
| `new --kind api\|sequence\|contract\|context\|adr --title "…" --out path` | Scaffolds a page from `templates/` with front matter. |
| `render <file> [--format storage\|markdown]` | Emits JSON `{title, body, page_id, space_id, parent_id, labels}` ready to pass to the gateway tool. Applies mermaid macro + code macro + layout rules. |
| `diff <file>` | Local change since `synced_commit` (git) — what the user is about to publish. |
| `remote-to-md <file> --from remote.json` | Converts a `getConfluencePage` body (storage XML or ADF JSON) back to markdown for a remote-vs-local diff. |
| `mark-synced <file> --page-id ID --version N` | Records the sync in front matter after a confirmed write. |

## Workflow: publish a page

1. `status` → pick the file. If `page_id` is empty, this is a create.
2. Conflict check (updates only): `getConfluencePage(cloudId, pageId)` →
   compare `version.number` with `confluence.version` in front matter.
   - Equal → safe.
   - Remote newer → `remote-to-md`, diff against local, ask the user
     "puxar pro markdown, sobrescrever, ou parar?". Stop unless told otherwise.
3. `render <file>` → payload. Show the user `diff <file>` (local change) and,
   for a create, the page title + parent.
4. Wait for an explicit yes.
5. Create: `createConfluencePage(cloudId, spaceId, title, body, parentId,
   contentFormat)`. Update: `updateConfluencePage(cloudId, pageId, title, body,
   contentFormat, version)` using remote version + 1 when the tool asks for it.
6. Read back the response version → `mark-synced`. Commit the front matter
   change together with the doc ("docs: publish <title> v<N>").
7. Payload > ~15 KB: gateway MCP tools have request-size limits. Split into a
   parent page plus child pages (one flow / one API per page) instead of
   fighting the limit.

## Workflow: check for remote edits (weekly or before a big rewrite)

For every file with a `page_id`: `getConfluencePage` → if `version.number` >
stored version, `remote-to-md` and show a diff. Offer to apply the remote
change to the markdown (then commit + `mark-synced` with the remote version),
or to republish local over it. Inline comments from colleagues:
`getConfluencePageInlineComments` — surface them as review items, never touch.

## Workflow: research before writing

`search` (Rovo) with the system/API name → `fetch` the top hits → cite them as
links in the page's "Related" section. Jira issues that motivated the change:
`getJiraIssue` → link in the ADR "Context". Never copy Rovo prose into the doc
without reading the source page.

## Writing rules for architecture pages

Full rules in `references/page-standards.md`. Non-negotiables:

- One page = one concern. A sequence page has exactly one `sequenceDiagram`
  plus a numbered step table below it (diagram for shape, table for detail).
- API pages: endpoint table first (method, path, auth, idempotency), then one
  section per endpoint with request/response as fenced `json` (becomes a
  Confluence `code` macro) and an error table (status, code, when, retry?).
- Contracts: schema as fenced `json`/`yaml`, a field table (name, type,
  required, semantics), versioning + compatibility rule stated explicitly.
- ADRs: Status / Context / Decision / Consequences, ≤ 1 screen.
- Headings start at `##` (`#` is the page title and comes from front matter).
- No `<div>`, no inline HTML, no images. Panels: use the `:::info` / `:::warning`
  / `:::note` fences from `references/page-standards.md`; render maps them to
  Confluence panel macros.
- Links between docs are relative markdown links; render rewrites them to the
  target page URL when the target has a `page_id`, and warns otherwise.

## Gateway tool map

Exact names from this gateway (Atlassian MCP v1 subset via LiteLLM tool
search): see `references/gateway-tools.md`. Find tools with the gateway's
tool-search virtual tool (`search_tools` / `mcp_tool_search`) and call by name.
Every call needs `cloudId`.

## Pitfalls

- `getConfluencePage` may return ADF JSON or storage XML depending on the
  `contentFormat` argument; `remote-to-md` handles both, pass what you got.
- Confluence title must be unique within a space. `new` warns when another
  file already has the same title.
- Mermaid macro XML differs per marketplace app. Never guess it; copy it from
  a page that renders (step 2 of setup). If the render output shows
  ```` ```mermaid ```` fences in `storage` mode, the macro template is missing.
- The gateway does not expose attachments, page properties, page width or
  layout ("breakout") settings. Do not promise those.
- Do not run `mark-synced` on a failed write. The response must contain the
  new version number.
