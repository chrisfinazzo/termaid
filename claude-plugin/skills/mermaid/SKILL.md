---
name: mermaid
description: Render a Mermaid diagram in the terminal with termaid. Use when the user asks to draw, render, preview or check a Mermaid diagram, a file containing one, or the diagrams in a Markdown document, PR description or README.
---

# Render Mermaid with termaid

termaid draws Mermaid diagrams as Unicode text. Run it with the Bash tool and
show the output to the user in a fenced code block so the box characters
stay aligned.

- One diagram, from a file: `termaid path/to/diagram.mmd`
- One diagram, inline: `printf '%s\n' '<mermaid source>' | termaid`
- Every diagram in a Markdown document, in place: `termaid --markdown README.md`
- A PR description: `gh pr view 42 | termaid --markdown`
- Narrow terminal: add `--width 80`. Plain ASCII: add `--ascii`.

If termaid is not installed, tell the user: `brew install termaid` or
`uv tool install termaid`.

When the user wants to check a diagram, run termaid on it: a parse error is
reported on stderr with a non-zero exit, and a successful render is the
check. Do not paraphrase the drawing; paste it verbatim.
