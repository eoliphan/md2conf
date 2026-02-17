---
name: skill-example
description: An example skill that demonstrates md2conf skill generation.
version: "1.0"
allowed-tools: Bash,Read,Write,Glob,Grep
argument-hint: "<file-or-directory>"
user-invocable: true
---
# Example Skill

This is an example skill generated from a Markdown file using `md2conf --skill`.

## Usage

Invoke this skill to demonstrate the skill generation pipeline:

```bash
python3 -m md2conf --skill -o /tmp/skill-output sample/skill-example.md
```

## What it does

1. Reads the source Markdown file
2. Extracts skill frontmatter fields (name, description, etc.)
3. Generates a skill directory with a `SKILL.md` file
4. Copies any referenced local images to an `assets/` subdirectory
