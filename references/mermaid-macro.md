# Getting the mermaid macro shape for this space

Every Mermaid marketplace app (Mermaid Macros for Confluence, Mermaid Studio,
Just Add+, draw.io's mermaid mode, …) stores its diagram in a different macro,
and Confluence Cloud has no native one. The render script therefore needs a
template copied from a page that already renders a diagram in this space.

## Steps

1. Find a page in the space with a working mermaid diagram (ask, or Rovo
   `search` for "mermaid" + the space name).
2. `getConfluencePage(cloudId, pageId, contentFormat="storage")` (name of the
   format parameter as the gateway exposes it). Take `body.storage.value`.
3. Locate the `<ac:structured-macro ac:name="...">` that wraps the diagram.
   Typical shapes:

   Mermaid Macros for Confluence (plain-text body):
   ```xml
   <ac:structured-macro ac:name="mermaid-cloud" ac:schema-version="1">
     <ac:plain-text-body><![CDATA[{{code}}]]></ac:plain-text-body>
   </ac:structured-macro>
   ```

   Apps that keep the source in a parameter:
   ```xml
   <ac:structured-macro ac:name="mermaid" ac:schema-version="1">
     <ac:parameter ac:name="code">{{code}}</ac:parameter>
   </ac:structured-macro>
   ```

   Forge apps often store it as an `ac:adf-extension` block instead; copy the
   whole block and put `{{code}}` where the source text sits.
4. Save it as `mermaid-macro.xml` in the repo root with the diagram text
   replaced by `{{code}}`. Set `mermaid_macro_name` in `confluence.yaml` to the
   `ac:name` (used when converting remote pages back to markdown).
5. Publish one small test page with a 3-line `sequenceDiagram`, open it,
   confirm it renders. If the page shows raw text, the macro shape is wrong;
   compare against the reference page again.

## If the gateway only accepts markdown bodies

Some gateway builds expose `updateConfluencePage` with a markdown body only.
Then the macro cannot be expressed and mermaid fences arrive as code blocks.
Options, in order:
- Ask the gateway team to allow `storage` (it is a one-line change in the
  Atlassian MCP config).
- Keep the diagram as a code block in Confluence and add the rendered picture
  by hand once; treat the code block as the source. Note this in the page.

## ADF payloads

When `getConfluencePage` returns ADF (`atlas_doc_format`), a mermaid macro
shows up as an `extension` / `bodiedExtension` node with `extensionKey`
containing "mermaid". `remote-to-md` handles the common parameter names
(`code`, `source`, `macroParams.code.value`); if yours differs, add it in
`adf_to_md` and note the shape here.
