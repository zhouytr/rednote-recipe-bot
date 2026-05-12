"""
小红书每日菜谱自动化生成器
功能：
- 每日 8:40 自动触发
- 生成不重复的家常菜菜谱
- 使用 代理平台 图像模型生成图片
- 生成小红书格式文案
- 输出内容供发布使用
"""

import os
import json
import random
import datetime
import requests
from pathlib import Path
from openai import OpenAI

# ============ 配置区 ============
# 优先从环境变量读取 API Key
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OUTPUT_DIR = Path("./output")
HISTORY_FILE = Path("./history.json")

# 初始化 OpenAI 客户端 (使用中转代理地址)
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://api.gptsapi.net/v1" 
)

# ============ 菜谱历史管理 ============

def load_history() -> list:
    """加载历史菜谱记录"""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
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
    """使用 GPT-4o 生成今日菜谱内容"""
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
  "xiaohongshu_body": "小红书正文（300字左右，活泼风格，包含分步说明和最后的互动引导）"
}}"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
    )
    
    raw = response.choices[0].message.content.strip()
    # 去除可能的 markdown 代码块标识
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    
    return json.loads(raw.strip())

# ============ 图片生成 ============

def generate_recipe_image(recipe: dict) -> bytes:
    """使用代理平台支持的图片模型生成菜谱图片"""
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

    print(f"🎨 正在请求模型 [gpt-image-2-plus] 为 {dish_name} 生成竖版图片...")
    
    response = client.images.generate(
        model="gpt-image-2-plus",  # 代理平台支持的模型名称
        prompt=image_prompt,
        size="1024x1792",          # 恢复竖版比例 (3:4 或 9:16 的近似值)
        n=1,
    )
    
    image_url = response.data[0].url
    print(f"🔗 图片生成成功，下载中: {image_url[:50]}...")
    
    # 下载图片
    img_response = requests.get(image_url, timeout=60)
    return img_response.content

# ============ 文案整理 ============

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
    
    print(f"\n🍳 [{today}] 开始生成今日内容...")
    
    # 1. 加载历史，避免重复
    history = load_history()
    used_dishes = get_used_dishes(history)
    print(f"📋 已有 {len(used_dishes)} 道菜历史记录")
    
    # 2. 生成菜谱内容
    print("✍️ 正在构思菜谱文案...")
    try:
        recipe = generate_recipe(used_dishes)
        print(f"✅ 今日菜谱：{recipe['dish_name']}")
    except Exception as e:
        print(f"❌ 菜谱文案生成失败: {e}")
        return

    # 3. 生成图片
    try:
        print("🎨 正在绘制菜谱配图...")
        image_bytes = generate_recipe_image(recipe)
        
        # 保存图片
        image_path = OUTPUT_DIR / f"{today}_{recipe['dish_name']}.png"
        with open(image_path, "wb") as f:
            f.write(image_bytes)
        print(f"💾 图片保存成功：{image_path}")
    except Exception as e:
        print(f"⚠️ 图片生成失败 (程序将继续生成文案): {e}")
        image_path = "生成失败"

    # 4. 保存文案
    post_text = build_xiaohongshu_post(recipe)
    text_path = OUTPUT_DIR / f"{today}_{recipe['dish_name']}_post.txt"
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(post_text)
    
    # 5. 保存完整 JSON 记录
    recipe_json_path = OUTPUT_DIR / f"{today}_{recipe['dish_name']}_recipe.json"
    with open(recipe_json_path, "w", encoding="utf-8") as f:
        json.dump(recipe, f, ensure_ascii=False, indent=2)
    
    # 6. 更新历史记录
    history.append({
        "date": today,
        "dish_name": recipe["dish_name"],
        "image_path": str(image_path),
        "post_path": str(text_path),
    })
    save_history(history)
    
    print(f"\n{'='*50}")
    print(f"🎉 今日内容生成完毕！")
    print(f"菜名：{recipe['dish_name']} {recipe['dish_emoji']}")
    print(f"标题：{recipe['xiaohongshu_title']}")
    print(f"{'='*50}\n")
    print("📱 文案预览：")
    print(post_text)

if __name__ == "__main__":
    run_daily_recipe()
