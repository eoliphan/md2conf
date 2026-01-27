<!-- confluence-page-id: 00000000000 -->

# Macro Expansion Test Cases

This document tests the macro expansion facility that provides shorthand syntax for Confluence macros.

## JIRA Macros

### Basic JIRA macro (default showSummary)

See ticket <!-- macro:jira: PROJ-123 --> for details.

### JIRA macro with showSummary=true

This ticket <!-- macro:jira: PROJ-456, showSummary=true --> shows the summary.

### JIRA macro with showSummary=false

This ticket <!-- macro:jira: PROJ-789, showSummary=false --> does not show the summary.

### Multiple JIRA macros in one paragraph

Related tickets: <!-- macro:jira: PROJ-100 --> and <!-- macro:jira: PROJ-200, showSummary=false --> are blocked by <!-- macro:jira: PROJ-300 -->.

## Status Macros

### Status with positional parameters

Build status: <!-- macro:status: green, Passing -->

Deploy status: <!-- macro:status: red, Failed -->

Code review: <!-- macro:status: yellow, In Progress -->

### Status with named parameters

Feature flag: <!-- macro:status: color="blue", title="Beta" -->

## Emoticon Macros

### Various emoticons

Tests pass <!-- macro:emoticon: tick --> but deployment failed <!-- macro:emoticon: cross -->.

Important note <!-- macro:emoticon: warning --> about deprecated features.

Good job <!-- macro:emoticon: thumbs-up --> on fixing the bug!

More info <!-- macro:emoticon: info --> can be found in the documentation.

## Macros in Tables

| Ticket | Status | Result |
|--------|--------|--------|
| <!-- macro:jira: PROJ-500 --> | <!-- macro:status: green, Done --> | <!-- macro:emoticon: tick --> |
| <!-- macro:jira: PROJ-501, showSummary=false --> | <!-- macro:status: yellow, In Progress --> | <!-- macro:emoticon: warning --> |
| <!-- macro:jira: PROJ-502 --> | <!-- macro:status: red, Blocked --> | <!-- macro:emoticon: cross --> |

## Macros in Lists

### Unordered list with macros

- Fix bug <!-- macro:jira: PROJ-600 --> - status: <!-- macro:status: green, Done -->
- Implement feature <!-- macro:jira: PROJ-601, showSummary=false --> - status: <!-- macro:status: yellow, In Progress -->
- Review code <!-- macro:jira: PROJ-602 --> - status: <!-- macro:status: red, Pending -->

### Ordered list with macros

1. First task <!-- macro:jira: PROJ-700 --> is complete <!-- macro:emoticon: tick -->
2. Second task <!-- macro:jira: PROJ-701 --> is in progress <!-- macro:emoticon: warning -->
3. Third task <!-- macro:jira: PROJ-702, showSummary=false --> is blocked <!-- macro:emoticon: cross -->

## Mixed Content

Here's a complex example with multiple macro types in one paragraph:

The ticket <!-- macro:jira: PROJ-800 --> has status <!-- macro:status: green, Resolved --> which means we're done <!-- macro:emoticon: thumbs-up -->. However, ticket <!-- macro:jira: PROJ-801, showSummary=false --> is still <!-- macro:status: yellow, Pending --> and needs attention <!-- macro:emoticon: warning -->.

## Edge Cases

### Macro at start of paragraph

<!-- macro:jira: PROJ-900 --> is the first thing in this paragraph.

### Macro at end of paragraph

This paragraph ends with a JIRA ticket <!-- macro:jira: PROJ-901 -->

### Macro in heading

## Task <!-- macro:jira: PROJ-902 --> Implementation

This section discusses the implementation of <!-- macro:jira: PROJ-902, showSummary=false -->.

### Macro in blockquote

> Important: Please review ticket <!-- macro:jira: PROJ-903 --> before proceeding.
> Status is currently <!-- macro:status: yellow, In Review -->.

### Macros with special characters in status title

Test results: <!-- macro:status: green, All Tests Passed! -->

Build info: <!-- macro:status: blue, v2.0.1 (RC-1) -->

## Combined with Raw CSF

This tests that macros work alongside raw CSF comments:

Macro version: <!-- macro:jira: PROJ-1000 -->

Raw CSF version: <!-- csf: <ac:structured-macro ac:name="jira" ac:schema-version="1"><ac:parameter ac:name="key">PROJ-1001</ac:parameter></ac:structured-macro> -->

Both should render correctly.
