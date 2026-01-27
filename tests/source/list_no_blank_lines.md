<!-- confluence-page-id: 00000000000 -->

# Lists Without Blank Lines Test

This document tests that lists can immediately follow paragraphs without requiring a blank line separator, which is standard Markdown/CommonMark behavior.

## Unordered list after paragraph
This is a paragraph that ends with a period.
- Item 1
- Item 2
- Item 3

## Ordered list after paragraph
Another paragraph text here, ending with punctuation.
1. First item
2. Second item
3. Third item

## Multiple consecutive lists
Text before the first list.
- Unordered item A
- Unordered item B

Text between lists.
1. Ordered item 1
2. Ordered item 2

## Nested lists without blank lines
Paragraph before nested list structure.
- Top level item
  - Nested item 1
  - Nested item 2
- Another top level item
  1. Nested ordered 1
  2. Nested ordered 2

## Mixed content
Some introductory text.
- List item after text
- Another list item

More text in between.
* Different marker style
* Another item with asterisk

Final paragraph.
1. Last ordered item
2. Another ordered item
