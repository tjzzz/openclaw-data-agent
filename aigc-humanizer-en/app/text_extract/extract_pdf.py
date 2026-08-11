"""PDF text extraction."""

import logging
import re
import statistics


def _join_text(left, right):
    left = left.rstrip()
    right = right.lstrip()
    if not left:
        return right
    if not right:
        return left
    if left.endswith('-') and not left.endswith(('<-', '--')):
        return left + right
    return left + ' ' + right


def _clean_block(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ''
    merged = lines[0]
    for line in lines[1:]:
        merged = _join_text(merged, line)
    return merged


def _extract_page_paragraphs(page):
    page_height = float(page.rect.height)
    top_limit = page_height * 0.07
    bottom_limit = page_height * 0.93
    blocks = []

    for block in page.get_text('blocks', sort=True):
        _x0, y0, _x1, y1, text, _block_no, block_type = block
        if block_type != 0 or y0 < top_limit or y1 > bottom_limit:
            continue
        cleaned = _clean_block(text)
        if cleaned:
            blocks.append({'text': cleaned, 'y0': float(y0), 'y1': float(y1)})

    if not blocks:
        return []

    gaps = [max(0.0, blocks[i]['y0'] - blocks[i - 1]['y1'])
            for i in range(1, len(blocks))]
    positive_gaps = [gap for gap in gaps if gap > 0.5]
    normal_gap = statistics.median(positive_gaps) if positive_gaps else 6.0
    paragraph_gap = max(8.0, min(14.0, normal_gap * 1.6))

    paragraphs = []
    current = blocks[0]['text']
    for index, block in enumerate(blocks[1:], start=1):
        gap = max(0.0, block['y0'] - blocks[index - 1]['y1'])
        if gap > paragraph_gap:
            paragraphs.append(current.strip())
            current = block['text']
        else:
            current = _join_text(current, block['text'])
    if current.strip():
        paragraphs.append(current.strip())
    return paragraphs


def _continues(previous, following):
    previous = previous.rstrip()
    following = following.lstrip()
    if not previous or not following:
        return False
    if re.match(r'^\d+(?:\.\d+)*\.?\s+[A-Z]', following):
        return False
    return previous.endswith(('-', ',', ';', ':')) or not re.search(
        r'[.!?][\]\)"\']?$', previous
    )


def extract_text_from_pdf(filepath):
    from app.text_extract import _build_paragraph

    import fitz
    doc = fitz.open(filepath)
    first_two_pages_text = ''.join(
        doc[i].get_text() for i in range(min(2, len(doc)))
    )
    is_turnitin = 'turnitin' in first_two_pages_text.lower()
    page_count = len(doc)
    start_page = 2 if is_turnitin else 0
    page_paragraphs = [
        _extract_page_paragraphs(doc[i])
        for i in range(start_page, page_count)
    ]
    doc.close()

    if is_turnitin:
        logging.info(
            f'Turnitin report detected, skipped first 2 pages ({page_count} pages total)'
        )

    paragraphs = []
    for page_items in page_paragraphs:
        if paragraphs and page_items and _continues(paragraphs[-1], page_items[0]):
            paragraphs[-1] = _join_text(paragraphs[-1], page_items.pop(0))
        paragraphs.extend(page_items)
    return [_build_paragraph(text) for text in paragraphs if text]
