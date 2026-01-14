# coding=utf-8
"""
AI 关键词自动生成工具

通过 AI 为指定领域生成 frequency_words.txt 规则。
"""

import sys
import os
import asyncio
import argparse
from pathlib import Path

# 添加 src 到路径
sys.path.append(str(Path(__file__).parent.parent / "src"))

from trendradar.core.loader import load_config
from trendradar.core.llm_service import LLMService

PROMPT_TEMPLATE = """
你是一个专业的新闻分析专家。我需要你为一个新闻监测系统生成“频率词过滤与分类规则”。

【目标领域】：{domain}

【规则语法说明】：
1. 分类包含逻辑：/正则表达式/ => 分类名称 (只有命中此规则的新闻才会保留并归类)
2. 必须词逻辑：+词 (该组内的所有必须词都匹配才算中)
3. 排除逻辑：!词 (命中此词的新闻将被丢弃，优先级最高)

【要求】：
1. 请生成 3-5 个细分话题的包含逻辑正则和分类。
2. 请额外生成 3-5 个在该领域常见的噪音词（排除逻辑）。
3. 只输出规则内容，不要任何解释。
4. 每行一条规则。

【输出示例】：
/比特币|以太坊|加密货币|Web3/ => 加密货币趋势
/数字货币|交易所|挖矿|中本聪/ => 币圈动态
!虚拟货币套路
!杀猪盘

现在，请为【{domain}】领域生成规则：
"""

async def main():
    parser = argparse.ArgumentParser(description="AI 关键词自动生成工具")
    parser.add_argument("domain", help="想要生成的领域描述（例如：低空经济、半导体等）")
    parser.add_argument("--append", action="store_true", help="追加到现有文件而不是覆盖")
    parser.add_argument("-y", "--yes", action="store_true", help="自动确认并不再提示")
    args = parser.parse_args()

    # 1. 加载配置和 LLM
    try:
        config = load_config()
        llm = LLMService(config)
        
        if not llm.is_enabled():
            print("❌ 错误: LLM 服务未启用。请在 .env 中设置 LLM_ENABLED=true 并配置相关参数。")
            return
    except Exception as e:
        print(f"❌ 加载配置失败: {e}")
        return

    # 2. 生成关键词
    print(f"🚀 正在为领域【{args.domain}】生成关键词配置...")
    prompt = PROMPT_TEMPLATE.format(domain=args.domain)
    
    system_prompt = "你是一个专业规则生成助手，只输出 frequency_words.txt 格式的规则。"
    response = await llm.ask(prompt, system_prompt=system_prompt)
    
    if "Request failed" in response:
        print(f"❌ AI 生成失败: {response}")
        return

    # 清理响应内容
    lines = [line.strip() for line in response.split("\n") if line.strip() and not line.startswith("```")]
    cleaned_content = "\n".join(lines)

    print("\n" + "="*40)
    print("✨ AI 生成的规则预览：")
    print("-" * 40)
    print(cleaned_content)
    print("="*40 + "\n")

    # 3. 写入文件
    if args.yes:
        confirm = 'y'
    else:
        confirm = input("⚠️ 是否确认将上述规则写入 config/frequency_words.txt? (y/n): ")
    
    if confirm.lower() != 'y':
        print("🛑 已取消操作。")
        return

    target_path = Path("config/frequency_words.txt")
    
    # 如果目标目录不存在，先创建
    target_path.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if args.append and target_path.exists() else "w"
    
    try:
        with open(target_path, mode, encoding="utf-8") as f:
            if mode == "a":
                f.write("\n\n")
                f.write(f"# --- AI 增加领域: {args.domain} ---\n")
            f.write(cleaned_content)
            f.write("\n")
        
        print(f"✅ 成功写入 {target_path} (模式: {'追加' if mode == 'a' else '重写'})")
    except Exception as e:
        print(f"❌ 写入文件失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())
