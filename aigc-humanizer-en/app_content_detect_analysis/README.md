# app_content_detect_analysis

> 备份目录：原 app 中"段落分析 / 维度分析 / 修改建议"相关逻辑，因前端流程改版（检测后不再展示分析结果）而从主代码中移除，这里留档备份。

## 移除原因

前端改造：点击检测后不再展示段落分析结果、子维度分数、修改建议，改为——余额够直接进入改写前后结果对比，余额不够直接弹出支付宝充值。因此后端不再需要这些分析逻辑。

## 保留 vs 移除

| 能力 | 是否保留 | 说明 |
|---|---|---|
| 整体 AI 率（ai_score） | ✅ 保留 | 检测和改写对比都需要 |
| risk_level / risk_description | ✅ 保留 | 改写流程展示需要 |
| 段落分析（analyze_by_paragraphs） | ❌ 移除 | 前端不再展示逐段结果，且 API 模式下每段调 API 慢 |
| 修改建议（generate_modification_suggestions） | ❌ 移除 | 前端不再展示 |
| 维度分析（sub_scores 展示） | ❌ 移除返回/展示 | 计算仍在（ai_score 依赖），仅不再回显 |

## 备份的函数

### 1. analyze_by_paragraphs（段落分析）
原位置：`app/ai_detector/rule_based.py`

```python
def analyze_by_paragraphs(text: str) -> List[Dict]:
    """Analyze text paragraph by paragraph."""
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    results = []

    for i, paragraph in enumerate(paragraphs, 1):
        if len(paragraph) >= 100:
            analysis = analyze_text(paragraph)
            results.append({
                "paragraph": i,
                "preview": paragraph[:100] + "..." if len(paragraph) > 100 else paragraph,
                "ai_score": analysis.get("ai_score", 0),
                "risk_level": analysis.get("risk_level", "Unknown")
            })

    return results
```

依赖：`analyze_text`（保留）、`split_sentences`（保留）。

### 2. _make_paragraph_analyzer（API 段落分析生成器）
原位置：`app/ai_detector/adapter.py`

```python
def _make_paragraph_analyzer(detect_fn):
    """用给定的 detect_fn 生成 analyze_by_paragraphs。"""
    def _para(text: str):
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        results = []
        for i, para in enumerate(paragraphs, 1):
            if len(para) >= 100:
                analysis = detect_fn(para)
                results.append({
                    "paragraph": i,
                    "preview": para[:100] + "..." if len(para) > 100 else para,
                    "ai_score": analysis.get("ai_score", 0),
                    "risk_level": analysis.get("risk_level", "Unknown"),
                })
        return results
    return _para
```

### 3. generate_modification_suggestions（修改建议）
原位置：`app/helpers/analysis_helpers.py`

```python
def generate_modification_suggestions(analysis_result, text):
    """Generate suggestions based on AI analysis results."""
    suggestions = []
    sub_scores = analysis_result.get("sub_scores", {})
    sub_details = analysis_result.get("sub_score_details", {})

    # 1. Perplexity suggestion
    if sub_scores.get("perplexity_score", 0) > 50:
        suggestions.append({
            "target": "perplexity",
            "icon": "📊",
            "title": "词汇多样性不足",
            "detail": "你的文本词汇模式过于可预测，AI检测模型容易识别。建议增加同义词替换和句式变化。",
            "severity": "high" if sub_scores["perplexity_score"] > 70 else "medium"
        })

    # 2. Pattern suggestion
    pattern_data = sub_details.get("pattern", {})
    if pattern_data.get("ai_phrase_count", 0) > 3:
        top_phrases = pattern_data.get("top_phrases", [])
        suggestions.append({
            "target": "pattern",
            "icon": "🔍",
            "title": f"检测到 {pattern_data['ai_phrase_count']} 个AI常用短语",
            "detail": f"常见AI短语如「{'」、「'.join(top_phrases[:3])}」在AI生成文本中频繁出现，替换为更自然的表达可降低AI率。",
            "severity": "high"
        })

    # 3. Readability suggestion
    readability = sub_details.get("readability", {})
    fk_grade = readability.get("flesch_kincaid", 10)
    avg_sent = readability.get("avg_sentence_length", 20)
    if fk_grade > 14 or avg_sent > 25:
        suggestions.append({
            "target": "readability",
            "icon": "✂️",
            "title": f"句长过于均匀（平均 {avg_sent:.0f} 词/句）",
            "detail": "AI生成的文本句子长度变化较小，缺乏人类写作的自然节奏感。建议混合长短句，增加句长变化。",
            "severity": "high" if avg_sent > 30 else "medium"
        })

    # 4. Burstiness suggestion
    if sub_scores.get("burstiness_score", 50) < 30:
        suggestions.append({
            "target": "burstiness",
            "icon": "📏",
            "title": "句式变化不足",
            "detail": "句子长度和结构变化不够丰富。建议混入短句（<10词）和长句（>30词），打破AI写作的规律性。",
            "severity": "medium"
        })

    # 5. Structure suggestion
    structure = sub_details.get("structure", {})
    if structure.get("formulaic_ratio", 0) > 0.2:
        suggestions.append({
            "target": "structure",
            "icon": "🏗️",
            "title": "句式开头较为刻板",
            "detail": "过多句子以「It is」「This is」「There is」等固定模式开头，建议变化句子起始方式。",
            "severity": "medium"
        })

    # Default suggestion if nothing specific
    if not suggestions:
        suggestions.append({
            "target": "general",
            "icon": "✅",
            "title": "文本质量良好",
            "detail": "AI检测指标正常，当前文本不太可能被标记为AI生成。",
            "severity": "low"
        })

    return suggestions
```

依赖：`sub_scores` / `sub_score_details`（analyze_text 返回，保留计算）。

## 结论

被移除的函数均可在需要时从本目录找回。整体 AI 率（ai_score / risk_level）检测与改写流程保留，不受影响。
