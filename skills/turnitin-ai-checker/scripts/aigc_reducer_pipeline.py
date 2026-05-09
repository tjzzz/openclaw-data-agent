#!/usr/bin/env python3
"""
应用 aigc-reducer 的5个模块处理文本
1. 词汇精炼器 - 清洗AI黑话
2. 节奏变频师 - 打乱句法节奏
3. 逻辑衔接专家 - 移除机械连词
4. 语义精细化工具 - 注入学术克制
5. 困惑度重构员 - 重构困惑度
"""

import re

# 模块1：AI黑话替换词典
AI_WORD_REPLACEMENTS = {
    # 动词类
    r'\bdelve\b': 'analyze',
    r'\bfoster\b': 'promote',
    r'\bunderscore\b': 'show',
    r'\bshed light on\b': 'explain',
    r'\bensure\b': 'help to',
    r'\bguarantee\b': 'support',
    # 形容词类
    r'\bmultifaceted\b': 'complex',
    r'\bpivotal\b': 'key',
    r'\bintricate\b': 'complex',
    r'\bcomprehensive\b': 'systematic',
    r'\bremarkable\b': 'significant',
    r'\brevolutionary\b': 'innovative',
    # 名词类
    r'\btapestry\b': 'picture',
    r'\bparadigm\b': 'framework',
    r'\bmilestone\b': 'important step',
    r'\bbreakthrough\b': 'progress',
}

# 模块3：禁用连词
FORBIDDEN_CONNECTORS = [
    'furthermore', 'moreover', 'additionally', 'therefore', 'thus', 'hence',
    'consequently', 'nevertheless', 'nonetheless', 'subsequently',
    'in conclusion', 'to summarize', 'to conclude', 'in summary'
]

# 模块4：绝对化动词替换
ABSOLUTE_VERBS = {
    r'\bproved\b': 'suggested',
    r'\bensures\b': 'may help',
    r'\bguarantees\b': 'supports',
    r'\bdemonstrates\b': 'shows',
    r'\bclearly shows\b': 'indicates',
    r'\bundeniably\b': '',
    r'\bwithout doubt\b': '',
    r'\bit is clear that\b': 'it appears that',
}

def module1_vocabulary_refinement(text):
    """模块1：词汇精炼器"""
    result = text
    for pattern, replacement in AI_WORD_REPLACEMENTS.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result

def module2_sentence_rhythm(text):
    """模块2：节奏变频师 - 添加短句打断"""
    # 将一些长句中的逗号连接改为句号，创建短句
    sentences = re.split(r'(?<=[.!?])\s+', text)
    modified = []

    for i, sentence in enumerate(sentences):
        # 如果句子超过50个词，尝试拆分
        words = sentence.split()
        if len(words) > 50 and i > 0:
            # 找到中间某个点，用句号替换逗号
            mid = len(words) // 2
            for j in range(mid, len(words)):
                if words[j] in [',', ';']:
                    words[j] = '.'
                    words[j+1] = words[j+1].capitalize() if j+1 < len(words) else words[j+1]
                    break
            sentence = ' '.join(words)
        modified.append(sentence)

    return ' '.join(modified)

def module3_connector_removal(text):
    """模块3：逻辑衔接专家"""
    result = text
    for connector in FORBIDDEN_CONNECTORS:
        # 替换段首的连接词
        result = re.sub(rf'\b{connector}\b,?\s*', '', result, flags=re.IGNORECASE)
        result = re.sub(rf'\s+{connector}\b,?\s*', ', ', result, flags=re.IGNORECASE)
    return result

def module4_academic_restraint(text):
    """模块4：语义精细化工具"""
    result = text
    for pattern, replacement in ABSOLUTE_VERBS.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result

def module5_perplexity(text):
    """模块5：困惑度重构 - 添加思考词汇"""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    modified = []

    thinking_words = ['Perhaps', 'It seems', 'One might argue', 'This suggests that']

    for i, sentence in enumerate(sentences):
        # 每隔几段在开头添加思考词汇
        if i > 0 and i % 7 == 0 and not sentence.startswith(tuple(tinking_words := thinking_words)):
            starter = thinking_words[i % len(thinking_words)]
            # 替换句首
            words = sentence.split()
            if words:
                words[0] = words[0].lower()
                sentence = starter.lower() + ', ' + ' '.join(words)
        modified.append(sentence)

    return ' '.join(modified)

def process_aigc_reducer(text):
    """按顺序应用5个模块"""
    # 恢复段落格式
    paragraphs = text.split('\n\n')
    processed_paragraphs = []

    for para in paragraphs:
        if len(para.strip()) < 50:
            processed_paragraphs.append(para)
            continue

        para = module1_vocabulary_refinement(para)
        para = module2_sentence_rhythm(para)
        para = module3_connector_removal(para)
        para = module4_academic_restraint(para)
        para = module5_perplexity(para)

        processed_paragraphs.append(para)

    return '\n\n'.join(processed_paragraphs)

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python aigc_reducer_pipeline.py <input_file> <output_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    print(f"Reading {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        text = f.read()

    print("Applying aigc-reducer 5 modules...")
    result = process_aigc_reducer(text)

    print(f"Writing to {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(result)

    print("Done!")
