"""Anchored pattern sections shared by validation, drift and context rendering."""
import re


def slug(heading):
    return re.sub(r"[^\w -]", "", heading.strip().lower()).replace(" ", "-")


def prose(text):
    """Mask fenced code, preserving offsets so code headings/statuses aren't prose."""
    output, fence = [], None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        masked = fence is not None or marker is not None
        if marker:
            token, tail = marker.groups()
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not tail.strip():
                fence = None
        output.append(re.sub(r"[^\r\n]", " ", line) if masked else line)
    return "".join(output)


def pattern_span(text, anchor):
    """Return character offsets for one explicit-anchor or heading-slug section."""
    original, text = text, prose(text)
    headings = list(re.finditer(r"^(#{1,6})\s+(.+)$", text, re.M))
    explicit = re.search(r"^.*?<a\s+[^>]*\bid=[\"']" + re.escape(anchor) + r"[\"'][^>]*>.*$", text, re.M)
    if explicit:
        start = explicit.start()
        own_heading = next((h for h in headings if h.start() >= explicit.end()), None)
        # An anchor may be followed directly by prose/SQL rather than a heading.
        if own_heading and STATUS.sub("", original[explicit.end():own_heading.start()]).strip():
            own_heading = None
    else:
        own_heading = next((h for h in headings if slug(h.group(2)) == anchor), None)
        if own_heading is None:
            raise ValueError("pattern anchor not found")
        start = own_heading.start()
    level = len(own_heading.group(1)) if own_heading else 6
    boundary = own_heading.end() if own_heading else explicit.end()
    ends = [h.start() for h in headings if h.start() > boundary and len(h.group(1)) <= level]
    ends.extend(m.start() for m in re.finditer(r"^.*?<a\s+[^>]*\bid=[\"']", text, re.M)
                if m.start() > boundary)
    return start, min(ends) if ends else len(text)


STATUS = re.compile(r"^\s*(?:<!--\s*)?(?:acf:\s*)?status:\s*(draft|confirmed)(?:\s*-->)?\s*$", re.M)


def pattern_status(section):
    found = STATUS.search(prose(section))
    return found.group(1) if found else "confirmed"


def draft_pattern(text, anchor):
    start, end = pattern_span(text, anchor)
    section = text[start:end]
    if pattern_status(section) == "draft":
        return text
    if (marker := STATUS.search(prose(section))):
        section = section[:marker.start()] + "<!-- acf: status: draft -->" + section[marker.end():]
    else:
        # Put status after the opening anchor/heading, inside exactly this section.
        first, separator, rest = section.partition("\n")
        section = first + "\n<!-- acf: status: draft -->\n" + rest
    return text[:start] + section + text[end:]


def render_reference(text, statuses=None, *, include_drafts=False):
    """Exclude draft pattern sections, or visibly label them on explicit request."""
    masked = prose(text)
    anchors = {m.group(1) for m in re.finditer(r'<a\s+[^>]*\bid=[\"\x27](pattern-[^\"\x27]+)[\"\x27]', masked)}
    headings = list(re.finditer(r"^(#{1,6})\s+(.+)$", masked, re.M))
    anchors.update(slug(m.group(2)) for m in headings if slug(m.group(2)).startswith("pattern-"))
    # Non-deterministic query patterns may use a normal heading and draft marker.
    for marker in STATUS.finditer(masked):
        preceding = [h for h in headings if h.end() <= marker.start()]
        explicit_before = list(re.finditer(r'<a\s+[^>]*\bid=[\"\x27]pattern-[^\"\x27]+[\"\x27]', masked[:marker.start()]))
        if preceding and (not explicit_before or preceding[-1].start() > explicit_before[-1].start()):
            anchors.add(slug(preceding[-1].group(2)))
    anchors.update(statuses or {})
    spans = []
    for anchor in anchors:
        try:
            start, end = pattern_span(text, anchor)
        except ValueError:
            continue
        if (statuses or {}).get(anchor, pattern_status(text[start:end])) != "confirmed":
            spans.append((start, end))
    merged = []
    for start, end in sorted(spans):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    for start, end in reversed(merged):
        replacement = ("> DRAFT — unconfirmed query pattern; do not use as governed guidance.\n\n" + text[start:end]
                       if include_drafts else "")
        text = text[:start] + replacement + text[end:]
    return text, len(merged)
