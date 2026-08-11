"""AI 率检测路由。

文件上传后先通过 extract_text 提取结构化节点，再由
paragraph_list_to_text 将所有带 text 字段的节点拼成纯文本。因此，原文 AI
率检测会分析标题、正文、参考文献、代码块和短段落等全部已提取文本；表格
占位、图片本身等不含 text 字段的节点不参与检测。

结构化节点会另外保存在 session 中，仅供用户确认改写后进行 segment 分块、
结构保护和原文格式回填；首次 AI 率检测不会经过 segmenter。
"""

import uuid
import os
import logging
import shutil
from flask import Blueprint, request, jsonify, session
from app.extensions import limiter
from app.helpers import login_required
from app.text_extract import extract_text, paragraph_list_to_text
from config import ALLOWED_UPLOAD_MIMETYPES, PRICE_PER_1000_WORDS, DELETE_UPLOADED_FILE

analysis_bp = Blueprint('analysis', __name__)


@analysis_bp.route('/api/analyze', methods=['POST'])
@limiter.limit("60 per minute")
@login_required
def api_analyze():
    """
    Analyze text for AI content.
    Accepts: text (direct paste) OR file (upload)
    Returns: AI score, paragraph analysis, suggestions
    """
    text = None
    paragraphs = None
    filename = None
    original_format = 'txt'
    original_filename = None
    source_file_key = None
    from flask import current_app
    app = current_app

    # Check if file was uploaded
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename:
            if file.content_type and file.content_type not in ALLOWED_UPLOAD_MIMETYPES:
                return jsonify({"error": "不支持的文件格式，仅支持 .docx、.pdf、.txt、.md"}), 400

            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in ['.docx', '.pdf', '.txt', '.md']:
                return jsonify({"error": "仅支持 .docx、.pdf、.txt、.md 格式"}), 400

            original_filename = file.filename
            original_format = ext[1:]
            filename = f"{uuid.uuid4().hex}{ext}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            try:
                paragraphs = extract_text(filepath)
                text = paragraph_list_to_text(paragraphs)
                if ext == '.docx':
                    source_file_key = filename
                    shutil.copy2(
                        filepath,
                        os.path.join(app.config['SOURCE_DOCS_FOLDER'], source_file_key)
                    )
            except Exception:
                logging.exception(f"Failed to extract text from {filepath}")
                return jsonify({"error": "文件解析失败，请确认文件格式正确"}), 400
            finally:
                if DELETE_UPLOADED_FILE:
                    try:
                        os.remove(filepath)
                    except OSError:
                        logging.warning(f"Failed to remove temp file: {filepath}")

    # Check if text was pasted
    if not text:
        data = request.get_json(silent=True) or {}
        text = data.get('text', '').strip()
        if not text:
            return jsonify({"error": "请上传文档或粘贴英文文本"}), 400

    text = text.strip()

    # Store original format info in session
    session['last_original_format'] = original_format
    session['last_original_filename'] = original_filename
    session['last_source_file_key'] = source_file_key
    session['last_text'] = text
    # 段落结构（含 style），供改写阶段判断标题/短段用；无样式信息时为 None
    session['last_paragraphs'] = paragraphs

    if len(text) < 50:
        return jsonify({"error": "文本太短，请提供至少 50 个字符"}), 400

    word_count = len(text.split())

    # 检测免费；返回改写费用预估（改写扣 word_balance，price 仅作展示）
    price = round(PRICE_PER_1000_WORDS * (word_count / 1000), 2)

    # Run AI detection (整篇 AI 率检测；段落/维度分析已移除，供改写对比使用)
    from app.extensions import ai_detector
    try:
        full_analysis = ai_detector(text, stage="analyze")
    except Exception:
        logging.exception("AI analysis failed")
        return jsonify({"error": "分析出错，请稍后重试"}), 500

    session['last_text'] = text
    # D 方案：缓存原文检测，供 /api/rewrite 复用（省 1 次 sapling 调用）
    from app.helpers.tasks import cache_original_analysis
    cache_original_analysis(text, full_analysis)

    return jsonify({
        "success": True,
        "analysis": full_analysis,
        "text": text,
        "text_preview": text[:500] + "..." if len(text) > 500 else text,
        "word_count": word_count,
        "price": round(price, 2),
        "rewrite_words": word_count,   # 改写需扣除的 word_balance 词数
        "has_extracted_text": original_format != 'txt',
        "original_format": original_format,
        "original_filename": original_filename
    })
