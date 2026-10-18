"""Draw Mermaid blocks in Claude Code's responses as they stream.

Claude Code's ``MessageDisplay`` hook hands the assistant's text to a
command in batches of completed lines and shows the command's answer in
their place. This module is that command::

    termaid --claude-hook

The hard part is that a fence can straddle batches, so the diagram's
lines are held back until the closing fence arrives and the drawing is
then emitted in their place. Nothing changes in the transcript: Claude
keeps seeing the Mermaid source, only the screen shows the diagram.

:class:`StreamRenderer` knows nothing about Claude Code. It is a line
filter whose state can be saved between calls, so another tool with a
similar streaming display can wrap it the same way :func:`run_claude_hook`
does here.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, field

from .markdown import _OPEN, _dedent
from .utils import display_width

_DEFAULT_WIDTH = 80
_MARGIN = 4  # Claude Code indents messages; keep diagrams clear of the edge


@dataclass
class StreamRenderer:
    """Line filter that replaces fenced Mermaid blocks with drawings.

    Feed it text with :meth:`feed` and print what comes back. Lines inside
    a Mermaid fence are held until the fence closes, so a call may return
    less text than it was given, and a later call returns the drawing.
    """

    width: int | None = None
    use_ascii: bool = False
    # Fence state, kept simple so it survives a round trip through JSON.
    fence: str = ""        # the opening fence's characters, "" when outside
    indent: str = ""
    held: list[str] = field(default_factory=list)   # original lines, fence included
    carry: str = ""        # a final batch may end mid-line

    def feed(self, text: str, final: bool = False) -> str:
        out: list[str] = []
        text = self.carry + text
        self.carry = ""
        lines = text.split("\n")
        tail = lines.pop()  # "" when the text ended on a newline
        if tail and not final:
            self.carry = tail
            tail = ""
        for line in lines:
            out.extend(self._line(line))
        shown = "".join(line + "\n" for line in out)
        if final:
            if tail:
                shown += "".join(line + "\n" for line in self._line(tail)).rstrip("\n")
            if self.fence:
                # Message ended inside a fence: show it as Claude wrote it
                shown += "".join(line + "\n" for line in self.held)
                if tail and self.held and self.held[-1] == tail:
                    shown = shown.rstrip("\n")
                self._reset()
        return shown

    def _line(self, line: str) -> list[str]:
        if self.fence:
            self.held.append(line)
            close = re.compile(
                r"^[ \t]*" + re.escape(self.fence[0]) + "{" + str(len(self.fence)) + r",}[ \t]*\r?$"
            )
            if not close.match(line):
                return []
            body = [_dedent(raw, len(self.indent)).rstrip("\r") for raw in self.held[1:-1]]
            drawn = self._draw("\n".join(body))
            held, self.held = self.held, []
            self._reset()
            return drawn if drawn is not None else held
        match = _OPEN.match(line)
        if match and not (match.group("fence")[0] == "`" and "`" in match.group("info")):
            words = match.group("info").split()
            if words and words[0].lower() == "mermaid":
                self.fence = match.group("fence")
                self.indent = match.group("indent")
                self.held = [line]
                return []
        return [line]

    def _reset(self) -> None:
        self.fence = ""
        self.indent = ""
        self.held = []

    def _draw(self, source: str) -> list[str] | None:
        """Render one diagram, or None when it cannot be drawn."""
        from . import render

        if not source.strip():
            return None
        width = self.width
        if width is None:
            width = max(shutil.get_terminal_size((_DEFAULT_WIDTH, 24)).columns - _MARGIN, 20)
        width = max(width - display_width(self.indent), 20)
        try:
            text = render(source, use_ascii=self.use_ascii)
            for gap, pad in ((2, 4), (1, 2), (1, 0)):
                if _widest(text) <= width:
                    break
                text = render(source, use_ascii=self.use_ascii, gap=gap, padding_x=pad)
        except Exception:
            return None
        if not text.strip():
            return None
        # A code fence keeps the box characters monospaced and unformatted
        # when the display renders Markdown.
        fence = "```"
        while fence in text:
            fence += "`"
        return [self.indent + fence] + [self.indent + ln for ln in text.split("\n")] + [self.indent + fence]

    def to_json(self) -> str:
        return json.dumps({k: v for k, v in asdict(self).items() if k in ("fence", "indent", "held", "carry")})

    def load(self, data: str) -> None:
        saved = json.loads(data)
        self.fence = saved.get("fence", "")
        self.indent = saved.get("indent", "")
        self.held = list(saved.get("held", []))
        self.carry = saved.get("carry", "")


def _widest(text: str) -> int:
    return max((display_width(line) for line in text.split("\n")), default=0)


def _state_path(message_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", message_id)[:80]
    folder = os.path.join(tempfile.gettempdir(), "termaid-claude-hook")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, safe + ".json")


def run_claude_hook(stdin=None, stdout=None, *, width: int | None = None, use_ascii: bool = False) -> int:
    """Handle one MessageDisplay call: read the batch, print the replacement.

    State is kept per ``message_id`` in the temp directory so a fence that
    spans several batches is still drawn. A batch that holds lines back
    returns an empty ``displayContent``; the drawing comes with the batch
    that closes the fence. Any failure prints nothing, and Claude Code then
    shows the original text.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    try:
        event = json.load(stdin)
    except (ValueError, OSError):
        return 0
    if event.get("hook_event_name") not in (None, "MessageDisplay"):
        return 0
    delta = event.get("delta") or ""
    final = bool(event.get("final", True))
    message_id = str(event.get("message_id") or "")

    renderer = StreamRenderer(width=width, use_ascii=use_ascii)
    path = _state_path(message_id) if message_id else None
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                renderer.load(f.read())
        except (OSError, ValueError):
            pass

    shown = renderer.feed(delta, final=final)

    if path:
        if final or not (renderer.fence or renderer.carry):
            try:
                os.remove(path)
            except OSError:
                pass
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(renderer.to_json())

    json.dump({"hookSpecificOutput": {"hookEventName": "MessageDisplay", "displayContent": shown}}, stdout)
    stdout.write("\n")
    return 0
