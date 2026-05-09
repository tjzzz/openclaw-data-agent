#!/usr/bin/env python3
"""
记录 AI 检测结果到 project.yaml
"""

import sys
import yaml
from datetime import datetime
from pathlib import Path


def record_ai_check(project_dir, file_name, score, issues=None):
    """记录 AI 检测结果"""
    yaml_path = Path(project_dir) / "project.yaml"

    with open(yaml_path, 'r') as f:
        config = yaml.safe_load(f)

    if 'ai_checks' not in config:
        config['ai_checks'] = []

    config['ai_checks'].append({
        'date': datetime.now().isoformat(),
        'file': file_name,
        'score': score,
        'issues': issues or []
    })

    with open(yaml_path, 'w') as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)

    print(f"✅ AI检测已记录: {file_name} = {score}%")


def main():
    if len(sys.argv) < 4:
        print("Usage: record_ai_check.py <项目目录> <文件名> <AI率> [问题1,问题2]")
        print("Example: record_ai_check.py ./projects/xxx essay.md 18 'sentence_length'")
        sys.exit(1)

    project_dir = sys.argv[1]
    file_name = sys.argv[2]
    score = int(sys.argv[3])
    issues = sys.argv[4].split(',') if len(sys.argv) > 4 else []

    record_ai_check(project_dir, file_name, score, issues)


if __name__ == "__main__":
    main()
