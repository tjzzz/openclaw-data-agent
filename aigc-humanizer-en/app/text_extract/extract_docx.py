"""DOCX text extraction."""

import re


class _NumberingResolver:
    """Resolve Word numbering definitions into visible list markers."""

    def __init__(self, doc):
        self._num_id_to_abs = {}
        self._abs_to_lvls = {}
        self._counters = {}
        self._prev_key = None

        try:
            numbering = doc.part.numbering_part
        except Exception:
            numbering = None
        if numbering is None:
            return

        from docx.oxml.ns import qn
        element = numbering.element
        for num in element.findall(qn('w:num')):
            num_id = num.get(qn('w:numId'))
            abs_el = num.find(qn('w:abstractNumId'))
            if num_id is not None and abs_el is not None:
                self._num_id_to_abs[num_id] = abs_el.get(qn('w:val'))

        for abstract in element.findall(qn('w:abstractNum')):
            abstract_id = abstract.get(qn('w:abstractNumId'))
            levels = {}
            for level in abstract.findall(qn('w:lvl')):
                level_id = level.get(qn('w:ilvl'))
                if level_id is None:
                    continue
                num_fmt = level.find(qn('w:numFmt'))
                level_text = level.find(qn('w:lvlText'))
                left = None
                paragraph_props = level.find(qn('w:pPr'))
                if paragraph_props is not None:
                    indent = paragraph_props.find(qn('w:ind'))
                    if indent is not None:
                        left = indent.get(qn('w:left'))
                levels[level_id] = {
                    'fmt': num_fmt.get(qn('w:val')) if num_fmt is not None else None,
                    'text': level_text.get(qn('w:val')) if level_text is not None else None,
                    'left': left,
                }
            if abstract_id is not None:
                self._abs_to_lvls[abstract_id] = levels

    def resolve(self, paragraph):
        from docx.oxml.ns import qn
        paragraph_props = paragraph._p.pPr
        if paragraph_props is None:
            return None, None, None
        numbering_props = paragraph_props.find(qn('w:numPr'))
        if numbering_props is None:
            return None, None, None

        num_id_element = numbering_props.find(qn('w:numId'))
        level_element = numbering_props.find(qn('w:ilvl'))
        if num_id_element is None:
            return None, None, None
        num_id = num_id_element.get(qn('w:val'))
        level_id = level_element.get(qn('w:val')) if level_element is not None else '0'

        indent = None
        indent_element = paragraph_props.find(qn('w:ind'))
        if indent_element is not None:
            indent = indent_element.get(qn('w:left'))

        abstract_id = self._num_id_to_abs.get(num_id)
        level_def = self._abs_to_lvls.get(abstract_id, {}).get(level_id)
        fmt = level_def['fmt'] if level_def else None
        level_text = level_def['text'] if level_def else None
        if indent is None and level_def:
            indent = level_def.get('left')

        key = (num_id, level_id)
        if self._prev_key is not None and key != self._prev_key:
            previous_level = int(self._prev_key[1]) if self._prev_key[1].isdigit() else 0
            current_level = int(level_id) if level_id.isdigit() else 0
            if current_level <= previous_level:
                self._counters.pop(key, None)
                for counter_key in list(self._counters):
                    if int(counter_key[1]) >= current_level:
                        self._counters.pop(counter_key, None)
        self._prev_key = key

        counter = self._counters.get(key, 0) + 1
        self._counters[key] = counter
        return self._render(fmt, counter, level_text), int(level_id), indent

    @classmethod
    def _render(cls, fmt, counter, level_text):
        if level_text is None:
            return str(counter)
        rendered = cls._format_number(fmt, counter, level_text)
        if '%' not in level_text:
            return rendered
        return re.sub(r'%\d+', rendered, level_text, count=1).strip()

    @classmethod
    def _format_number(cls, fmt, counter, level_text=None):
        if fmt == 'decimal':
            return str(counter)
        if fmt == 'lowerLetter':
            return cls._to_alpha(counter)
        if fmt == 'upperLetter':
            return cls._to_alpha(counter).upper()
        if fmt == 'lowerRoman':
            return cls._to_roman(counter)
        if fmt == 'upperRoman':
            return cls._to_roman(counter).upper()
        if fmt == 'bullet':
            if level_text and '\uf075' in level_text:
                return '\u25aa'
            if level_text and '\uf06e' in level_text:
                return '\u25e6'
            return '\u2022'
        return str(counter)

    @staticmethod
    def _to_alpha(number):
        result = ''
        while number > 0:
            number, remainder = divmod(number - 1, 26)
            result = chr(ord('a') + remainder) + result
        return result

    @staticmethod
    def _to_roman(number):
        values = [
            (1000, 'm'), (900, 'cm'), (500, 'd'), (400, 'cd'),
            (100, 'c'), (90, 'xc'), (50, 'l'), (40, 'xl'),
            (10, 'x'), (9, 'ix'), (5, 'v'), (4, 'iv'), (1, 'i'),
        ]
        result = ''
        for value, numeral in values:
            while number >= value:
                result += numeral
                number -= value
        return result


def extract_text_from_docx(filepath):
    """Extract paragraphs and table placeholders in document-flow order."""
    from docx import Document
    from docx.text.paragraph import Paragraph

    from app.text_extract import _build_paragraph, mark_reference_sections

    doc = Document(filepath)
    result = []
    table_index = 0
    resolver = _NumberingResolver(doc)

    for body_index, child in enumerate(doc.element.body.iterchildren()):
        tag = child.tag.split('}')[-1]
        if tag == 'p':
            paragraph = Paragraph(child, doc)
            text = paragraph.text.strip()
            if not text:
                continue
            style = paragraph.style.name if paragraph.style else None
            list_text, list_level, indent = resolver.resolve(paragraph)
            item = _build_paragraph(
                text, style, list_text=list_text,
                list_level=list_level, indent=indent,
            )
            item['has_image'] = bool(
                paragraph._p.xpath('.//w:drawing') or
                paragraph._p.xpath('.//w:pict')
            )
            item['has_hyperlink'] = bool(paragraph._p.xpath('.//w:hyperlink'))
            item['body_index'] = body_index
            result.append(item)
        elif tag == 'tbl':
            table_index += 1
            result.append({'table': table_index, 'body_index': body_index})

    return mark_reference_sections(result)
