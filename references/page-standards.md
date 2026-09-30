# Page standards for architecture docs in Confluence

These rules exist so pages look the same regardless of who wrote them and so
that the render step is deterministic. They match what Confluence's own
formatting guide (`getContentFormatGuide`) and Atlassian's writing guidelines
ask for; adjust only after re-reading the cached guide.

## Structure

- Title from front matter, never an `#` in the body. Titles: `<Thing> — <what>`
  (e.g. `Orders API — v2`, `Checkout — payment authorization flow`). Unique per
  space.
- Body starts with `##`. Depth ≤ 3 (`####` is a smell: split the page).
- First section answers "what is this and why does it exist" in ≤ 5 lines.
- One concern per page. A page that needs a table of contents is two pages.
- Last section is `## Related` with links: Jira, sibling pages, ADRs.

## Tables

- Tables are for facts with the same shape (endpoints, fields, errors,
  actors). Prose is for reasoning.
- Header row always. First column is the identifier (name, #, status).
- Keep cells to one line; a cell that needs a list belongs in its own section.
- Confluence cannot set column widths through the gateway; don't try.

## Code and diagrams

- Fenced code with a language: `json`, `yaml`, `http`, `sql`, `mermaid`.
  Renders as a Confluence code macro with syntax highlight.
- Mermaid only (no images): `sequenceDiagram` with `autonumber`, `flowchart LR`
  for context, `erDiagram` for data, `stateDiagram-v2` for lifecycles.
- A diagram never carries detail a table can carry: keep messages short on
  the arrows, put payload/contract/failure detail in the step table below.
- Participants named as the systems are named in the org, not as roles.

## Panels

```
:::info      background / where the truth lives
:::warning   constraints, compatibility rules, "do not"
:::note      side remarks
:::tip       shortcuts
:::error     known broken behaviour
```

Max one panel per section. Panels are not for prose that belongs in the flow.

## Links

- Between architecture pages: relative markdown links to the `.md` file.
  Render turns them into Confluence page links; if the target isn't published
  yet, the link degrades to plain text and a warning is printed.
- Jira: full URL. External: full URL.
- Never link to a Confluence page by copying its URL into markdown when the
  page is one of ours: use the relative file link.

## Wording

- Present tense, active voice, short sentences. "The gateway rejects…" not
  "requests will be rejected by the gateway".
- Names of fields, endpoints, statuses, enums in backticks and copied
  literally from the contract source. Never paraphrase a contract.
- Acronyms expanded once per page.
- No "TBD" in a published page; publish the ADR as `Proposed` instead.

## Labels

`architecture` on everything, plus one of `context`, `sequence`, `api`,
`contract`, `adr`, `index`, plus the system name. Labels are what Rovo search
and Confluence filters key on.
