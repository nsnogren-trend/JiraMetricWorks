import json
from datetime import datetime

def normalize_description_to_markdown(value, options=None):
    """
    Convert Jira Description (ADF or string) to Markdown.
    Returns a string (may be empty).
    """
    opts = {
        "promote_strong_paragraphs_to_headings": True,
        "heading_level": 2,
        "emoji_style": "unicode",  # unicode or shortcode
        "list_indent_spaces": 2,
        "escape_strategy": "minimal",
        "ensure_trailing_newline": True
    }
    if options:
        opts.update(options)

    if value is None:
        return ""

    if isinstance(value, dict) and value.get("type") == "doc":
        md = _adf_doc_to_markdown(value, opts)
        return md

    if isinstance(value, str):
        s = value.replace("\r\n", "\n").rstrip()
        if opts["ensure_trailing_newline"]:
            s += "\n"
        return s

    try:
        s = json.dumps(value, ensure_ascii=False)
    except Exception:
        s = str(value)
    return s + ("\n" if opts["ensure_trailing_newline"] else "")

def _adf_doc_to_markdown(doc, opts):
    blocks = []
    for node in doc.get("content", []) or []:
        block_md = _adf_block_to_markdown(node, opts, depth=0)
        if block_md:
            blocks.append(block_md.rstrip())
    out = "\n\n".join(b for b in blocks if b is not None)
    out = _normalize_blank_lines(out)
    if opts.get("ensure_trailing_newline", True) and not out.endswith("\n"):
        out += "\n"
    return out

def _adf_block_to_markdown(node, opts, depth):
    t = node.get("type")
    if t == "paragraph":
        if opts.get("promote_strong_paragraphs_to_headings", True):
            if _is_strong_only_paragraph(node):
                text = _adf_inline_to_markdown(node.get("content", []) or [], opts)
                level = min(max(int(opts.get("heading_level", 2)), 1), 6)
                return "#" * level + " " + text.strip()
        text = _adf_inline_to_markdown(node.get("content", []) or [], opts)
        return text.strip()

    if t == "heading":
        level = min(max(node.get("attrs", {}).get("level", 2), 1), 6)
        text = _adf_inline_to_markdown(node.get("content", []) or [], opts)
        return "#" * level + " " + text.strip()

    if t == "bulletList":
        items = []
        for li in node.get("content", []) or []:
            items.extend(_adf_list_item(li, opts, ordered=False, depth=depth))
        return "\n".join(items)

    if t == "orderedList":
        items = []
        start = int(node.get("attrs", {}).get("order", 1) or 1)
        for idx, li in enumerate(node.get("content", []) or []):
            items.extend(_adf_list_item(li, opts, ordered=True, depth=depth, number=start + idx))
        return "\n".join(items)

    if t == "blockquote":
        inner = []
        for ch in node.get("content", []) or []:
            b = _adf_block_to_markdown(ch, opts, depth)
            if b:
                lines = b.splitlines() or [""]
                inner.append("\n".join(["> " + ln for ln in lines]))
        return "\n\n".join(inner)

    if t == "rule":
        return "---"

    if t == "codeBlock":
        lang = node.get("attrs", {}).get("language")
        code = _adf_text_from_inline(node.get("content", []) or [])
        fence = "```"
        header = fence + (lang if lang else "")
        return f"{header}\n{code}\n{fence}"

    if t == "panel":
        panel_type = (node.get("attrs", {}) or {}).get("panelType")
        label = f"[{panel_type}]" if panel_type else "[panel]"
        inner_blocks = []
        for ch in node.get("content", []) or []:
            inner_blocks.append(_adf_block_to_markdown(ch, opts, depth))
        inner = "\n\n".join([b for b in inner_blocks if b])
        lines = (label + " " + inner).splitlines()
        return "\n".join(["> " + ln for ln in lines])

    if t in ("mediaSingle", "mediaGroup", "media"):
        return "![attachment](attachment)"

    if t == "table":
        return _adf_table_to_markdown(node, opts)

    if t == "taskList":
        items = []
        indent = " " * (opts.get("list_indent_spaces", 2) * depth)
        for it in node.get("content", []) or []:
            checked = (it.get("attrs", {}) or {}).get("state") == "DONE"
            box = "[x]" if checked else "[ ]"
            text = ""
            for ch in it.get("content", []) or []:
                if ch.get("type") == "paragraph":
                    text = _adf_inline_to_markdown(ch.get("content", []) or [], opts).strip()
            items.append(f"{indent}- {box} {text}")
        return "\n".join(items)

    if "content" in node:
        parts = []
        for ch in node.get("content", []) or []:
            parts.append(_adf_block_to_markdown(ch, opts, depth))
        return "\n\n".join([p for p in parts if p])
    return ""

def _adf_list_item(node, opts, ordered, depth, number=None):
    lines = []
    indent = " " * (opts.get("list_indent_spaces", 2) * depth)
    bullet = f"{number}. " if ordered else "- "
    content = node.get("content", []) or []
    first_line_done = False
    for ch in content:
        if ch.get("type") == "paragraph":
            text = _adf_inline_to_markdown(ch.get("content", []) or [], opts).strip()
            if not first_line_done:
                lines.append(f"{indent}{bullet}{text}")
                first_line_done = True
            else:
                lines.append(f"{indent}{' ' * len(bullet)}{text}")
        elif ch.get("type") in ("bulletList", "orderedList", "taskList"):
            nested = _adf_block_to_markdown(ch, opts, depth + 1)
            if nested:
                lines.append(nested)
        else:
            txt = _adf_block_to_markdown(ch, opts, depth)
            if txt:
                if not first_line_done:
                    lines.append(f"{indent}{bullet}{txt}")
                    first_line_done = True
                else:
                    lines.append(f"{indent}{' ' * len(bullet)}{txt}")
    if not first_line_done:
        lines.append(f"{indent}{bullet}")
    return lines

def _adf_inline_to_markdown(inlines, opts):
    out = []
    for node in inlines:
        t = node.get("type")
        if t == "text":
            text = node.get("text", "")
            marks = node.get("marks", []) or []
            out.append(_apply_marks(text, marks, opts))
        elif t == "hardBreak":
            out.append("\n")
        elif t == "emoji":
            out.append(_render_emoji(node.get("attrs", {}) or {}, opts))
        elif t == "mention":
            attrs = node.get("attrs", {}) or {}
            label = attrs.get("text") or attrs.get("id") or "mention"
            out.append("@" + label)
        elif t in ("inlineCard", "blockCard"):
            attrs = node.get("attrs", {}) or {}
            url = attrs.get("url") or (attrs.get("data", {}) or {}).get("url")
            if url:
                title = (attrs.get("data", {}) or {}).get("name") or url
                out.append(f"[{_escape_md(title)}]({url})")
            else:
                out.append("[card]")
        elif t == "date":
            attrs = node.get("attrs", {}) or {}
            ts = attrs.get("timestamp")
            if ts:
                try:
                    dt = datetime.fromtimestamp(int(ts) / 1000.0)
                    out.append(dt.strftime("%Y-%m-%d"))
                except Exception:
                    out.append(_escape_md(str(ts)))
            else:
                out.append("[date]")
        elif t == "status":
            attrs = node.get("attrs", {}) or {}
            txt = attrs.get("text") or ""
            color = attrs.get("color")
            if color:
                out.append(f"[status: {_escape_md(txt)} ({color})]")
            else:
                out.append(f"[status: {_escape_md(txt)}]")
        else:
            out.append(_escape_md(str(node.get("text", ""))))
    return "".join(out)

def _is_strong_only_paragraph(node):
    content = node.get("content", []) or []
    if len(content) != 1 or content[0].get("type") != "text":
        return False
    marks = content[0].get("marks", []) or []
    if not content[0].get("text", "").strip():
        return False
    return all(m.get("type") == "strong" for m in marks) and len(marks) >= 1

def _apply_marks(text, marks, opts):
    if not marks:
        return _escape_md(text)

    has_code = any(m.get("type") == "code" for m in marks)
    if has_code:
        return f"`{_escape_backticks(text)}`"

    wrapped = _escape_md(text)
    types = [m.get("type") for m in marks if m.get("type")]
    if "link" in types:
        link_mark = next((m for m in marks if m.get("type") == "link"), None)
        href = (link_mark.get("attrs") or {}).get("href") if link_mark else None
        title = (link_mark.get("attrs") or {}).get("title") if link_mark else None
        label = wrapped
        if href:
            if title:
                wrapped = f"[{label}]({href} \"{_escape_quotes(title)}\")"
            else:
                wrapped = f"[{label}]({href})"
        types = [t for t in types if t != "link"]

    if "strong" in types:
        wrapped = f"**{wrapped}**"
    if "em" in types:
        wrapped = f"_{wrapped}_"
    if "strike" in types:
        wrapped = f"~~{wrapped}~~"

    return wrapped

def _escape_md(s):
    if not s:
        return ""
    specials = "\\`*_{}[]()#+-|!>"
    out = []
    for ch in s:
        if ch in specials:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)

def _escape_backticks(s):
    return s.replace("`", "\\`")

def _escape_quotes(s):
    return s.replace('"', '\\"')

def _render_emoji(attrs, opts):
    style = opts.get("emoji_style", "unicode")
    txt = attrs.get("text") or attrs.get("shortName") or ""
    if style == "shortcode":
        return txt or ""
    id_ = attrs.get("id")
    mapping = {
        "atlassian-plus": "➕",
        "atlassian-warning": "⚠️",
    }
    if id_ in mapping:
        return mapping[id_]
    short = (attrs.get("shortName") or "").strip(":")
    known = {"plus": "➕", "warning": "⚠️"}
    if short in known:
        return known[short]
    return txt if txt else "🙂"

def _normalize_blank_lines(s):
    lines = s.replace("\r\n", "\n").split("\n")
    out = []
    blank = False
    for ln in lines:
        ln = ln.rstrip()
        if ln == "":
            if not blank:
                out.append("")
            blank = True
        else:
            out.append(ln)
            blank = False
    return "\n".join(out)

def _adf_text_from_inline(inlines):
    parts = []
    for node in inlines:
        if node.get("type") == "text":
            parts.append(node.get("text", ""))
        elif node.get("type") == "hardBreak":
            parts.append("\n")
    return "".join(parts)

def _adf_table_to_markdown(node, opts):
    rows = node.get("content", []) or []
    if not rows:
        return ""
    first_row = rows[0]
    is_header = any(cell.get("type") == "tableHeader" for cell in (first_row.get("content", []) or []))
    md_rows = []

    def render_cell(cell):
        txt = ""
        for ch in cell.get("content", []) or []:
            if ch.get("type") == "paragraph":
                txt += _adf_inline_to_markdown(ch.get("content", []) or [], opts).strip()
        return txt

    for r in rows:
        cells = []
        for cell in (r.get("content", []) or []):
            cells.append(render_cell(cell))
        md_rows.append("| " + " | ".join(cells) + " |")

    if is_header:
        cols = len((first_row.get("content", []) or []))
        sep = "| " + " | ".join(["---"] * cols) + " |"
        md_rows.insert(1, sep)
    return "\n".join(md_rows)