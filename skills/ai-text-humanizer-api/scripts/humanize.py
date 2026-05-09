#!/usr/bin/env python3
"""
AI Text Humanizer API - Python Script
使用 ai-text-humanizer.com API 对英文文本进行去AI化处理

支持:
- 大文件自动分段处理
- 频率限制自动等待
- 错误重试
- 进度显示
"""

import os
import sys
import time
import requests
from pathlib import Path
from typing import Optional, Tuple


class TextHumanizer:
    """AI Text Humanizer API 客户端"""
    
    API_URL = "https://ai-text-humanizer.com/api.php"
    MAX_WORDS_PER_REQUEST = 2000  # API 限制：每次请求最多 2000 words
    RATE_LIMIT_DELAY = 1.2  # API 调用间隔（秒），略高于1秒以避免触发限制
    MAX_RETRIES = 3  # 最大重试次数
    RETRY_DELAY = 2.0  # 重试延迟（秒）
    
    def __init__(self, email: str, password: str):
        """
        初始化客户端
        
        Args:
            email: ai-text-humanizer.com 账户邮箱
            password: 账户密码
        """
        self.email = email
        self.password = password
        self.session = requests.Session()
    
    def humanize_text(self, text: str) -> Tuple[bool, str]:
        """
        对文本进行去AI化处理
        
        Args:
            text: 需要处理的文本
            
        Returns:
            (success, result): 成功标志和处理结果
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.session.post(
                    self.API_URL,
                    data={
                        'email': self.email,
                        'pw': self.password,
                        'text': text
                    },
                    timeout=60
                )
                
                if response.status_code == 200:
                    result = response.text.strip()

                    # 验证返回内容
                    if not result:
                        return False, "API returned empty response"

                    # 检查常见错误格式
                    error_indicators = ['error', 'Error', 'ERROR', 'failed', 'Failed', 'invalid', 'Invalid']
                    if any(indicator in result[:100] for indicator in error_indicators):
                        # 可能是错误信息
                        if len(result) < 500:  # 错误信息通常较短
                            return False, f"API error: {result}"

                    return True, result
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    if attempt < self.MAX_RETRIES - 1:
                        print(f"  ⚠️  Attempt {attempt + 1} failed: {error_msg}")
                        print(f"  Retrying in {self.RETRY_DELAY} seconds...")
                        time.sleep(self.RETRY_DELAY)
                    else:
                        return False, error_msg

            except requests.exceptions.Timeout:
                if attempt < self.MAX_RETRIES - 1:
                    print(f"  ⚠️  Timeout on attempt {attempt + 1}, retrying...")
                    time.sleep(self.RETRY_DELAY)
                else:
                    return False, "Request timeout after multiple retries"
                    
            except requests.exceptions.RequestException as e:
                return False, f"Network error: {str(e)}"
        
        return False, "Max retries exceeded"
    
    def _count_words(self, text: str) -> int:
        """
        统计文本中的单词数
        
        Args:
            text: 文本内容
            
        Returns:
            单词数量
        """
        # 简单的单词统计：按空格分割
        return len(text.split())
    
    def humanize_file(self, input_path: str, output_path: Optional[str] = None) -> Tuple[bool, str]:
        """
        对文件进行去AI化处理
        
        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径（可选）
            
        Returns:
            (success, message): 成功标志和消息
        """
        # 读取输入文件
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                text = f.read()
        except FileNotFoundError:
            return False, f"Input file not found: {input_path}"
        except Exception as e:
            return False, f"Error reading file: {str(e)}"
        
        # 设置输出路径
        if output_path is None:
            input_file = Path(input_path)
            output_path = str(input_file.parent / f"{input_file.stem}_humanized{input_file.suffix}")
        
        text_length = len(text)
        word_count = self._count_words(text)
        print(f"📄 Processing: {input_path}")
        print(f"📊 Text length: {text_length:,} characters, {word_count:,} words")
        
        # 判断是否需要分段（按单词数判断）
        if word_count <= self.MAX_WORDS_PER_REQUEST:
            # 单次处理
            print("🚀 Calling API...")
            success, result = self.humanize_text(text)
            
            if success:
                # 保存结果
                try:
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(result)
                    print(f"✅ Success! Result saved to: {output_path}")
                    return True, output_path
                except Exception as e:
                    return False, f"Error saving file: {str(e)}"
            else:
                return False, result
        else:
            # 分段处理
            return self._process_large_file(text, output_path)
    
    def _split_text_smartly(self, text: str) -> list:
        """
        智能分割文本，保持 Markdown 格式完整
        按 API 限制（2000 words）进行分割

        Args:
            text: 完整文本

        Returns:
            chunks: 分段列表
        """
        chunks = []
        current_chunk = ""
        current_words = 0

        # 按段落分割
        paragraphs = text.split('\n\n')

        for para in paragraphs:
            para_words = self._count_words(para)
            
            # 如果当前段落本身就超过限制，需要进一步拆分
            if para_words > self.MAX_WORDS_PER_REQUEST:
                # 先保存当前 chunk
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                    current_words = 0

                # 按句子拆分超长段落
                sentences = para.replace('. ', '. \n').replace('! ', '! \n').replace('? ', '? \n').split('\n')
                for sentence in sentences:
                    sentence_words = self._count_words(sentence)
                    
                    if current_words + sentence_words <= self.MAX_WORDS_PER_REQUEST:
                        current_chunk += sentence + " "
                        current_words += sentence_words
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sentence + " "
                        current_words = sentence_words
            else:
                # 正常段落处理
                if current_words + para_words <= self.MAX_WORDS_PER_REQUEST:
                    current_chunk += para + "\n\n"
                    current_words += para_words
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = para + "\n\n"
                    current_words = para_words

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def _process_large_file(self, text: str, output_path: str) -> Tuple[bool, str]:
        """
        处理大文件（分段）

        Args:
            text: 完整文本
            output_path: 输出路径

        Returns:
            (success, message): 成功标志和消息
        """
        # 智能分割文本
        chunks = self._split_text_smartly(text)
        
        total_chunks = len(chunks)
        print(f"📦 Split into {total_chunks} chunks for processing")
        
        # 处理每个分段
        results = []
        for i, chunk in enumerate(chunks, 1):
            chunk_words = self._count_words(chunk)
            print(f"  [{i}/{total_chunks}] Processing chunk ({chunk_words:,} words)...")
            
            success, result = self.humanize_text(chunk)
            
            if success:
                results.append(result)
                print(f"  ✓ Chunk {i} done")
            else:
                print(f"  ✗ Chunk {i} failed: {result}")
                return False, f"Failed on chunk {i}: {result}"
            
            # 频率限制等待
            if i < total_chunks:
                time.sleep(self.RATE_LIMIT_DELAY)
        
        # 合并结果
        final_result = "\n\n".join(results)
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_result)
            print(f"\n✅ All chunks processed! Result saved to: {output_path}")
            return True, output_path
        except Exception as e:
            return False, f"Error saving file: {str(e)}"


    def humanize_text_direct(self, text: str) -> Tuple[bool, str]:
        """
        直接对文本进行去AI化处理（不读取文件）
        
        Args:
            text: 需要处理的文本
            
        Returns:
            (success, result): 成功标志和处理结果
        """
        word_count = self._count_words(text)
        print(f"📊 Text length: {len(text):,} characters, {word_count:,} words")
        
        # 判断是否需要分段
        if word_count <= self.MAX_WORDS_PER_REQUEST:
            print("🚀 Calling API...")
            return self.humanize_text(text)
        else:
            # 分段处理
            return self._process_large_text(text)
    
    def _process_large_text(self, text: str) -> Tuple[bool, str]:
        """
        处理大文本（分段），返回结果而非保存文件
        
        Args:
            text: 完整文本
            
        Returns:
            (success, result): 成功标志和处理结果
        """
        chunks = self._split_text_smartly(text)
        
        total_chunks = len(chunks)
        print(f"📦 Split into {total_chunks} chunks for processing")
        
        results = []
        for i, chunk in enumerate(chunks, 1):
            chunk_words = self._count_words(chunk)
            print(f"  [{i}/{total_chunks}] Processing chunk ({chunk_words:,} words)...")
            
            success, result = self.humanize_text(chunk)
            
            if success:
                results.append(result)
                print(f"  ✓ Chunk {i} done")
            else:
                print(f"  ✗ Chunk {i} failed: {result}")
                return False, f"Failed on chunk {i}: {result}"
            
            # 频率限制等待
            if i < total_chunks:
                time.sleep(self.RATE_LIMIT_DELAY)
        
        # 合并结果
        final_result = "\n\n".join(results)
        print(f"\n✅ All chunks processed!")
        return True, final_result


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='AI Text Humanizer - 对英文文本进行去AI化处理',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  # 处理文件
  python3 humanize.py report.md
  python3 humanize.py input.md output.md
  
  # 直接处理文本
  python3 humanize.py --text "This is the text to humanize..."
  python3 humanize.py -t "Your text here" -o output.md
'''
    )
    
    parser.add_argument('input', nargs='?', help='输入文件路径')
    parser.add_argument('output', nargs='?', help='输出文件路径（可选）')
    parser.add_argument('-t', '--text', help='直接输入文本内容（不读取文件）')
    parser.add_argument('-o', '--output', help='输出文件路径（与 --text 配合使用）')
    
    args = parser.parse_args()
    
    # 检查参数
    if not args.input and not args.text:
        parser.print_help()
        print("\n❌ Error: 必须提供输入文件或使用 --text 参数")
        sys.exit(1)
    
    # 获取认证信息
    email = os.environ.get('AI_TEXT_HUMANIZER_EMAIL')
    password = os.environ.get('AI_TEXT_HUMANIZER_PASSWORD')
    
    if not email or not password:
        print("❌ Error: Missing credentials")
        print("\nPlease set environment variables:")
        print("  export AI_TEXT_HUMANIZER_EMAIL=\"your-email@example.com\"")
        print("  export AI_TEXT_HUMANIZER_PASSWORD=\"your-password\"")
        sys.exit(1)
    
    # 创建客户端
    humanizer = TextHumanizer(email, password)
    
    # 处理输入
    if args.text:
        # 直接处理文本
        print("📄 Processing text input...")
        success, result = humanizer.humanize_text_direct(args.text)
        
        if success:
            # 如果指定了输出文件，保存结果
            output_path = args.output
            if output_path:
                try:
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(result)
                    print(f"✅ Result saved to: {output_path}")
                except Exception as e:
                    print(f"❌ Error saving file: {str(e)}")
                    sys.exit(1)
            else:
                # 直接输出到控制台
                print("\n" + "="*60)
                print("RESULT:")
                print("="*60)
                print(result)
        else:
            print(f"\n❌ Failed: {result}")
            sys.exit(1)
    else:
        # 处理文件
        success, message = humanizer.humanize_file(args.input, args.output)
        
        if not success:
            print(f"\n❌ Failed: {message}")
            sys.exit(1)


if __name__ == "__main__":
    main()
