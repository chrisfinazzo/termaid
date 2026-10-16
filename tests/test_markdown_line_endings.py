import pytest

from termaid.markdown import split_markdown


@pytest.mark.parametrize("fence", ["```", "~~~"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_fences_preserve_document_line_endings(fence, newline):
    document = newline.join(
        ["before", fence + "mermaid", "graph LR", "  A --> B", fence, "after", ""]
    )

    segments = split_markdown(document)
    diagrams = [segment for segment in segments if segment.is_mermaid]

    assert len(diagrams) == 1
    assert diagrams[0].line == 2
    assert diagrams[0].text.splitlines() == ["graph LR", "  A --> B"]
    assert "\n".join(s.raw if s.is_mermaid else s.text for s in segments) == document
