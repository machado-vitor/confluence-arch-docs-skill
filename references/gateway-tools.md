# Atlassian tools exposed by the LiteLLM AI gateway

Inventory taken from the gateway's tool search (30 of 32 confirmed). This is
the Atlassian MCP **v1** tool set, not v2: no attachments, no page properties,
no version diff, no space instructions, no Bitbucket/Compass/Loom. Rovo here
is search-only. Re-run the tool search after any gateway upgrade and update
this list.

Every call needs `cloudId` (from `getAccessibleAtlassianResources`, or read
the site from any page URL via `fetch`).

## Confluence — read

| Tool | Use in this skill |
| --- | --- |
| getConfluencePage | Conflict check (version), remote body for `remote-to-md`, macro template discovery |
| getConfluencePageDescendants | Verify the page tree under `parent_id` |
| getConfluencePageFooterComments | Review items after publish |
| getConfluencePageInlineComments | Review items after publish (never modify) |
| getConfluenceCommentChildren | Thread context for a comment |
| getConfluenceSpaces | `space_id` / `space_key` for confluence.yaml |
| getPagesInConfluenceSpace | Title-collision check before create |
| searchConfluenceUsingCql | Precise lookups: `title = "…" AND space = "…"`, `label = "architecture"` |
| search (Rovo) | Fuzzy research before writing; find related pages/issues |
| fetch | Read a hit from `search` by ARI |
| getContentFormatGuide | Cache once into `references/content-format-guide.md` |

## Confluence — write

| Tool | Use |
| --- | --- |
| createConfluencePage | First publish. Needs spaceId, title, body, parentId, content format |
| updateConfluencePage | Every later publish. Needs pageId, title, body, format, version (remote + 1 where required) |
| createConfluenceFooterComment | Optional: leave a "published from repo @ commit" note |
| createConfluenceInlineComment | Reply to a reviewer on a specific passage |

## Jira

Read: getJiraIssue, getJiraIssueRemoteIssueLinks, getJiraIssueTypeMetaWithFields,
getJiraProjectIssueTypesMetadata, getVisibleJiraProjects,
getTransitionsForJiraIssue, getIssueLinkTypes, lookupJiraAccountId.

Write: createJiraIssue, editJiraIssue, addCommentToJiraIssue,
addWorklogToJiraIssue, createIssueLink, transitionJiraIssue.

Use in this skill: `getJiraIssue` to cite the motivating issue in an ADR;
`addCommentToJiraIssue` to drop the published page link on the issue after
the user confirms.

## Not available (do not promise)

- Attachments / images → diagrams must be text (mermaid macro).
- Page properties, content appearance, page width / breakout, layout.
- Version diff server-side → done locally by `remote-to-md --diff`.
- Labels as a separate call → pass labels on create/update if the tool accepts
  them; otherwise labels are set once by hand.
- Delete / archive / move.

## Calling pattern

The gateway hides the catalogue behind a virtual tool search
(`search_tools` / `mcp_tool_search`) and a generic call tool. Search by the
exact name above, read the returned schema (parameter names vary slightly
between gateway builds: `contentFormat` vs `body_format`, `spaceId` vs
`space_id`), then call. Record the observed parameter names here the first
time so the next session doesn't rediscover them:

```
createConfluencePage:  (fill in after first successful call)
updateConfluencePage:  (fill in)
getConfluencePage:     (fill in)
```
