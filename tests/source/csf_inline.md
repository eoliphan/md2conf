<!-- confluence-page-id: 00000000000 -->

# Inline CSF Test Cases

This document tests inline CSF (Confluence Storage Format) embedding using HTML comment syntax.

## Test 1: Inline CSF in paragraph

This is a paragraph with an inline <!-- csf: <ac:structured-macro ac:name="status"><ac:parameter ac:name="colour">Green</ac:parameter><ac:parameter ac:name="title">DONE</ac:parameter></ac:structured-macro> --> status macro.

## Test 2: CSF in table cell

| Ticket | Status |
|--------|--------|
| PROJ-123 | <!-- csf: <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">PROJ-123</ac:parameter></ac:structured-macro> --> |
| PROJ-456 | In Progress |

## Test 3: Multiple CSF in one paragraph

Build status: <!-- csf: <ac:emoticon ac:name="tick" /> --> Tests pass and <!-- csf: <ac:emoticon ac:name="cross" /> --> Deploy failed.

## Test 4: CSF in list item

- Item with status <!-- csf: <ac:structured-macro ac:name="status"><ac:parameter ac:name="colour">Red</ac:parameter><ac:parameter ac:name="title">TODO</ac:parameter></ac:structured-macro> --> marker
- Regular item without CSF
- Another item with <!-- csf: <ac:emoticon ac:name="warning" /> --> warning

## Test 5: Block-level CSF comment

Paragraph before the macro.

<!-- csf: <ac:structured-macro ac:name="info"><ac:rich-text-body><p>This is an info panel inserted via comment syntax.</p></ac:rich-text-body></ac:structured-macro> -->

Paragraph after the macro.

## Test 6: CSF with multiline XML

Testing multiline CSF comment:

<!-- csf:
<ac:structured-macro ac:name="panel">
  <ac:parameter ac:name="title">Panel Title</ac:parameter>
  <ac:parameter ac:name="bgColor">#E3FCEF</ac:parameter>
  <ac:rich-text-body>
    <p>This panel was embedded using <strong>multiline</strong> CSF comment syntax.</p>
  </ac:rich-text-body>
</ac:structured-macro>
-->

End of tests.
