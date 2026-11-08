"""Read HWPX paragraphs in document order, including nested table cells."""


def paragraphs(node):
    # Flush surrounding paragraph fragments before/after a nested table cell.
    parts = []

    def flush():
        line = "".join(parts).strip()
        parts.clear()
        if line:
            lines.append(line)

    def walk(el):
        name = el.tag.rsplit("}", 1)[-1]
        if name == "p":
            flush()
        if name == "t":
            parts.append("".join(el.itertext()))
        else:
            for ch in el:
                walk(ch)
        if name == "p":
            flush()

    lines = []
    walk(node)
    flush()
    return lines
