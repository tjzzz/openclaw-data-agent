"""Markdown text extraction."""

import re


def extract_text_from_markdown(filepath):
    """Retain Markdown syntax while adding heading/code metadata."""
    from app.text_extract import _build_paragraph, mark_reference_sections

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.read().splitlines()

    result = []
    buffer = []
    fence = None

    def append_body():
        if not buffer:
            return
        text = '\n'.join(buffer).strip()
        buffer.clear()
        if text:
            result.append(_build_paragraph(text))

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if fence:
            buffer.append(line)
            if re.match(rf'^\s*{re.escape(fence)}\s*$', line):
                para = _build_paragraph('\n'.join(buffer).strip())
                para['is_code_block'] = True
                result.append(para)
                buffer.clear()
                fence = None
            i += 1
            continue

        fence_match = re.match(r'^\s*(`{3,}|~{3,})', line)
        if fence_match:
            append_body()
            fence = fence_match.group(1)
            buffer.append(line)
            i += 1
            continue

        heading_match = re.match(r'^\s*(#{1,6})\s+(.+?)\s*#*\s*$', line)
        if heading_match:
            append_body()
            result.append(_build_paragraph(
                stripped, style=f'Heading {len(heading_match.group(1))}'
            ))
            i += 1
            continue

        if (stripped and i + 1 < len(lines) and
                re.match(r'^\s*(=+|-+)\s*$', lines[i + 1])):
            append_body()
            level = 1 if lines[i + 1].strip().startswith('=') else 2
            result.append(_build_paragraph(
                f'{line}\n{lines[i + 1]}', style=f'Heading {level}'
            ))
            i += 2
            continue

        if stripped:
            buffer.append(line)
        else:
            append_body()
        i += 1

    if buffer:
        para = _build_paragraph('\n'.join(buffer).strip())
        if fence:
            para['is_code_block'] = True
        result.append(para)

    return mark_reference_sections(result)
