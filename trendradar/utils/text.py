# coding=utf-8
"""
文本处理工具
"""

import re


def strip_markdown(text: str) -> str:
    """去除 Markdown 格式"""
    if not text:
        return ""
    
    # 去除加粗 **text**
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    
    # 去除斜体 *text*
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    
    # 去除链接 [text](url) -> text
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    
    # 去除标题 # Title
    text = re.sub(r'^\s*#+\s*', '', text, flags=re.MULTILINE)
    
    # 去除引用 > Quote
    text = re.sub(r'^\s*>\s*', '', text, flags=re.MULTILINE)
    
    # 去除代码块 ```code```
    text = re.sub(r'```[\s\S]*?```', '', text)
    
    # 去除行内代码 `code`
    text = re.sub(r'`(.*?)`', r'\1', text)
    
    return text
