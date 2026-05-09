#!/usr/bin/env python3
"""
Data Agent - 项目初始化
创建简化版 project.yaml
"""

import os
import sys
import re
from datetime import datetime
from pathlib import Path


def extract_word_count(text):
    """从文本提取字数要求"""
    patterns = [
        r'(\d+)\s*words?',
        r'字数[\s:：]*(\d+)',
        r'([\d,]+)\s*字'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            count = int(match.group(1).replace(',', ''))
            return count
    return 0


def extract_format(text):
    """从文本提取格式要求"""
    if re.search(r'\b[Ee]ssay\b', text):
        return "Essay"
    if re.search(r'\b[Rr]eport\b', text):
        return "Report"
    return "Report"


def init_project(name, word_count=0, format_type="Report"):
    """初始化项目"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    project_id = datetime.now().strftime("%Y%m%d") + "_" + re.sub(r'[^\w]', '_', name)

    # 项目目录
    workspace = os.path.expanduser("~/.workbuddy/workspace-data-agent/projects")
    project_dir = Path(workspace) / f"{date_str}_{name.replace(' ', '_')}"
    project_dir.mkdir(parents=True, exist_ok=True)

    # 创建子目录
    (project_dir / "output").mkdir(exist_ok=True)
    (project_dir / "working").mkdir(exist_ok=True)

    # 计算字数范围
    min_count = int(word_count * 0.9) if word_count else 0
    max_count = int(word_count * 1.1) if word_count else 0

    # 创建 project.yaml
    yaml_content = f"""project:
  id: {project_id}
  name: "{name}"
  created_at: "{datetime.now().isoformat()}"

requirements:
  word_count:
    target: {word_count}
    min: {min_count}
    max: {max_count}
  format:
    type: "{format_type}"
    citation_style: "APA"
  tools:
    required: []
  deadline: ""

ai_checks: []

delivery:
  final_file: ""
  delivered_at: ""
"""

    yaml_path = project_dir / "project.yaml"
    with open(yaml_path, 'w') as f:
        f.write(yaml_content)

    print(f"✅ 项目创建成功")
    print(f"   目录: {project_dir}")
    print(f"   配置: {yaml_path}")

    return str(project_dir)


def main():
    if len(sys.argv) < 2:
        print("Usage: init_project.py <项目名称> [字数]")
        sys.exit(1)

    name = sys.argv[1]
    word_count = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    init_project(name, word_count)


if __name__ == "__main__":
    main()
