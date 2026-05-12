"""
小红书每日菜谱自动化生成器
功能：
- 每日 8:40 自动触发
- 生成不重复的家常菜菜谱
- 使用 OpenAI GPT-4o image 生成图片
- 生成小红书格式文案
- 输出内容供发布使用
"""

import os
import json
import random
import datetime
import requests
import base64
from pathlib import Path
from openai import OpenAI

# ============ 配置区 ============
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "your_openai_api_key_here")
OUTPUT_DIR = Path("./output")
HISTORY_FILE = Path("./history.json")

# 小红书图片尺寸（手机竖版 3:4）
IMAGE_WIDTH = 1080
IMAGE_HEIGHT = 1440

client = OpenAI(api_key=OPENAI_API_KEY)

# ============ 菜谱历史管理 ============

def load_history() -> list:
    """加载历史菜谱记录"""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history: list):
    """保存历史菜谱记录"""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def get_used_dishes(history: list) -> list:
    """获取已使用过的菜名"""
    return [item["dish_name"] for item in history]

# ============ 菜谱生成 ============

def generate_recipe(used_dishes: list) -> dict:
    """使用 GPT-4 生成今日菜谱"""
    used_str = "、".join(used_dishes[-30:]) if used_dishes else "无"
    
    prompt = f"""你是一位专业的家常菜厨师，请生成一道适合普通家庭制作的中国家常菜菜谱。

要求：
1. 不能是以下已使用过的菜：{used_str}
2. 食材简单易得，步骤清晰
3. 适合小红书风格（活泼、接地气）

请严格按照以下 JSON 格式返回，不要有任何其他文字：
{{
  "dish_name": "菜名",
  "dish_emoji": "相关emoji",
  "tagline": "一句话吸引人的描述（15字以内）",
  "ingredients": [
    {{"name": "食材名", "amount": "用量"}},
    ...
  ],
  "steps": [
    {{"step": 1, "action": "步骤标题", "detail": "具体描述"}},
    ...
  ],
  "tips": ["小贴士1", "小贴士2"],
  "tags": ["#标签1", "#标签2", "#标签3", "#标签4", "#标签5"],
  "xiaohongshu_title": "小红书标题（含emoji，吸引人，20字以内）",
  "xiaohongshu_body": "小红书正文（300字左右，活泼风格，包含分步说明和最后的互动引导）",
  "image_prompt_en": "A mouth-watering Chinese home-cooked dish photo of [dish], overhead flat lay shot on white ceramic plate, garnished beautifully, vibrant colors, food photography style, warm lighting, 4K quality"
}}"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
    )
    
    raw = response.choices[0].message.content.strip()
    # 去除可能的 markdown 代码块
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    
    return json.loads(raw.strip())

# ============ 图片生成 ============

def generate_recipe_image(recipe: dict) -> bytes:
    """使用 DALL-E 3 生成菜谱图片"""
    dish_name = recipe["dish_name"]
    
    # 构建详细的图片提示词
    image_prompt = f"""Professional Chinese food photography of {dish_name} (a Chinese home-cooked dish).
Beautiful ceramic bowl/plate presentation, vibrant and appetizing colors, 
steam rising, garnished with green onions or herbs,
warm restaurant lighting, shallow depth of field, 
shot from slightly above at 45-degree angle,
include some ingredients scattered artfully around the dish,
red and orange tones in sauce, ultra-realistic food photography,
magazine quality, 4K resolution."""

    response = client.images.generate(
        model="dall-e-3",
        prompt=image_prompt,
        size="1024x1792",  # 竖版接近手机尺寸
        quality="hd",
        n=1,
    )
    
    image_url = response.data[0].url
    
    # 下载图片
    img_response = requests.get(image_url, timeout=30)
    return img_response.content

# ============ 小红书文案生成 ============

def build_xiaohongshu_post(recipe: dict) -> str:
    """构建完整的小红书发布文案"""
    title = recipe["xiaohongshu_title"]
    body = recipe["xiaohongshu_body"]
    tags = " ".join(recipe["tags"])
    
    post = f"""{title}

{body}

{tags}
#家常菜 #厨房日记 #简单美食 #每日菜谱"""
    
    return post

# ============ 主流程 ============

def run_daily_recipe():
    """每日执行的主函数"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    today = datetime.date.today().strftime("%Y-%m-%d")
    
    print(f"🍳 [{today}] 开始生成今日菜谱...")
    
    # 1. 加载历史，避免重复
    history = load_history()
    used_dishes = get_used_dishes(history)
    print(f"📋 已有 {len(used_dishes)} 道菜历史记录，避免重复")
    
    # 2. 生成菜谱
    print("✍️  正在生成菜谱内容...")
    recipe = generate_recipe(used_dishes)
    print(f"✅ 今日菜谱：{recipe['dish_name']}")
    
    # 3. 生成图片
    print("🎨 正在生成食物图片（DALL-E 3）...")
    image_bytes = generate_recipe_image(recipe)
    
    # 4. 保存图片
    image_path = OUTPUT_DIR / f"{today}_{recipe['dish_name']}.png"
    with open(image_path, "wb") as f:
        f.write(image_bytes)
    print(f"💾 图片已保存：{image_path}")
    
    # 5. 生成文案
    post_text = build_xiaohongshu_post(recipe)
    text_path = OUTPUT_DIR / f"{today}_{recipe['dish_name']}_post.txt"
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(post_text)
    print(f"📝 文案已保存：{text_path}")
    
    # 6. 保存完整菜谱 JSON
    recipe_path = OUTPUT_DIR / f"{today}_{recipe['dish_name']}_recipe.json"
    with open(recipe_path, "w", encoding="utf-8") as f:
        json.dump(recipe, f, ensure_ascii=False, indent=2)
    
    # 7. 更新历史记录
    history.append({
        "date": today,
        "dish_name": recipe["dish_name"],
        "image_path": str(image_path),
        "post_path": str(text_path),
    })
    save_history(history)
    
    print(f"\n{'='*50}")
    print(f"🎉 今日内容已生成完毕！")
    print(f"菜名：{recipe['dish_name']} {recipe['dish_emoji']}")
    print(f"标题：{recipe['xiaohongshu_title']}")
    print(f"{'='*50}\n")
    print("📱 小红书文案预览：")
    print(post_text)
    
    return {
        "recipe": recipe,
        "image_path": str(image_path),
        "post_text": post_text,
        "date": today,
    }

if __name__ == "__main__":
    run_daily_recipe()
