"""Plain-text extraction."""


def extract_text_from_txt(filepath):
    from app.text_extract import _build_paragraph, mark_reference_sections

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    paragraphs = [
        _build_paragraph(chunk)
        for chunk in content.split('\n\n')
        if chunk.strip()
    ]
    return mark_reference_sections(paragraphs)
