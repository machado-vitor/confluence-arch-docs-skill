# confluence-arch-docs

Claude Code skill: software-architecture docs (sequence diagrams, APIs,
contracts, ADRs) written as markdown + mermaid in git and published to
Confluence through the Atlassian MCP tools exposed by a LiteLLM AI gateway.
No API token, no direct REST: the gateway is the only write path, every write
is diffed and confirmed, Rovo is search-only.

## Install (work Mac)

```bash
git clone <this repo> ~/.claude/skills/confluence-arch-docs
```

Then in the docs repo:

```bash
cp ~/.claude/skills/confluence-arch-docs/templates/confluence.yaml ./confluence.yaml
# fill it in with values from the gateway tools (see SKILL.md, "One-time setup")
python3 ~/.claude/skills/confluence-arch-docs/scripts/confluence_sync.py status
```

Stdlib only; runs on the system python3.

## Files

- `SKILL.md` — the skill itself (rules, workflows, tool map).
- `scripts/confluence_sync.py` — status / new / adopt / render / diff / remote-to-md / mark-synced.
- `templates/` — page scaffolds (context, sequence, api, contract, adr, index) and `confluence.yaml`.
- `references/page-standards.md` — layout and writing rules.
- `references/mermaid-macro.md` — how to capture the space's mermaid macro shape.
- `references/gateway-tools.md` — the gateway's Atlassian tool inventory and what is not available.
- `tests/` — renderer round-trip tests.
