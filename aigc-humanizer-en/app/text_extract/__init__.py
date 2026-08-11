"""Shared extraction helpers, public API, and format dispatcher."""

import os
import re


def _is_heading_style(style_name):
    if not style_name:
        return False
    normalized = style_name.lower().strip()
    return (
        'heading' in normalized or
        normalized == 'title' or
        normalized.startswith('toc')
    )


def _is_reference_heading(paragraph):
    if not paragraph or 'text' not in paragraph:
        return False
    text = paragraph['text'].splitlines()[0].lower().strip()
    text = re.sub(r'^#{1,6}\s*', '', text).strip().rstrip(':')
    return text in {
        'reference',
        'references',
        'reference list',
        'bibliography',
        'works cited',
        'literature cited',
    }


def mark_reference_sections(paragraphs):
    """Mark content after a references heading until the next heading."""
    in_reference = False
    for paragraph in paragraphs:
        if 'text' not in paragraph:
            continue
        if paragraph.get('is_heading', False):
            in_reference = _is_reference_heading(paragraph)
        elif in_reference:
            paragraph['is_reference'] = True
    return paragraphs


def _build_paragraph(text, style=None, list_text=None,
                     list_level=None, indent=None):
    text = text.strip()
    paragraph = {
        'text': text,
        'word_count': len(text.split()),
    }
    if style is not None:
        paragraph['style'] = style
        paragraph['is_heading'] = _is_heading_style(style)
    if list_text is not None:
        paragraph['list_text'] = list_text
        paragraph['list_level'] = list_level
    if indent is not None:
        paragraph['indent'] = indent
    return paragraph


def _finalize_nodes(nodes, source_format):
    """Apply the shared node identity model after format-specific parsing."""
    paragraph_index = 0
    for content_index, node in enumerate(nodes):
        node['node_id'] = f'{source_format}-node-{content_index:04d}'
        node['content_index'] = content_index
        node['source_format'] = source_format
        if node.get('text'):
            node['paragraph_index'] = paragraph_index
            paragraph_index += 1
    return nodes


def extract_text_from_docx(filepath):
    from app.text_extract.extract_docx import extract_text_from_docx as extractor
    return _finalize_nodes(extractor(filepath), 'docx')


def extract_text_from_pdf(filepath):
    from app.text_extract.extract_pdf import extract_text_from_pdf as extractor
    return _finalize_nodes(extractor(filepath), 'pdf')


def extract_text_from_markdown(filepath):
    from app.text_extract.extract_markdown import extract_text_from_markdown as extractor
    return _finalize_nodes(extractor(filepath), 'md')


def extract_text_from_txt(filepath):
    from app.text_extract.extract_txt import extract_text_from_txt as extractor
    return _finalize_nodes(extractor(filepath), 'txt')


def extract_text(filepath):
    """Dispatch an uploaded file to its format-specific extractor."""
    extension = os.path.splitext(filepath)[1].lower()
    extractors = {
        '.docx': extract_text_from_docx,
        '.pdf': extract_text_from_pdf,
        '.md': extract_text_from_markdown,
        '.txt': extract_text_from_txt,
    }
    extractor = extractors.get(extension)
    if extractor is None:
        raise ValueError(f'Unsupported file format: {extension}')
    paragraphs = extractor(filepath)
    return mark_reference_sections(paragraphs)


def paragraph_list_to_text(paragraphs):
    """Join textual document nodes with a blank line."""
    return '\n\n'.join(
        paragraph.get('text')
        for paragraph in paragraphs
        if paragraph.get('text')
    )
