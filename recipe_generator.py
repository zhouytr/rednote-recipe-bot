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
import base64
import random
import datetime
import time
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

def generate_recipe(used_dishes: list, max_retries: int = 3) -> dict:
    """使用 GPT-4o 生成今日菜谱内容，包含重试机制与 JSON 模式限制"""
    used_str = "、".join(used_dishes[-30:]) if used_dishes else "无"
    
    prompt = f"""你是一位专业的家常菜厨师，请生成一道适合普通家庭制作的中国家常菜菜谱。

要求：
1. 不能是以下已使用过的菜：{used_str}
2. 食材简单易得，步骤清晰
3. 适合小红书风格（活泼、接地气）
4. ⚠️ 必须严格遵守标准的单行 JSON 对象格式！如果 JSON 的字符串（如文案正文）中需要换行，请务必使用转义字符 \\n ，绝对不能在双引号内部直接按回车键换行！

请严格按照以下 JSON 格式返回，不要有任何其他文字：
{{
  "dish_name": "菜名",
  "dish_emoji": "相关emoji",
  "tagline": "一句话吸引人的描述（15字以内）",
  "ingredients": [
    {{"name": "食材名", "amount": "用量"}}
  ],
  "steps": [
    {{"step": 1, "action": "步骤标题", "detail": "具体描述"}}
  ],
  "tips": ["小贴士1", "小贴士2"],
  "tags": ["#标签1", "#标签2", "#标签3"],
  "xiaohongshu_title": "小红书标题（含emoji，吸引人，20字以内）",
  "xiaohongshu_body": "小红书正文（300字左右，活泼风格，包含分步说明和最后的互动引导）"
}}"""

    # 加入重试机制
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                response_format={ "type": "json_object" }, # 🌟 强制使用 JSON 模式
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9,
            )
            
            raw = response.choices[0].message.content.strip()
            
            # 去除可能的 markdown 代码块标识 (双重保险)
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.lower().startswith("json"):
                    raw = raw[4:]
            
            return json.loads(raw.strip())
            
        except json.JSONDecodeError as e:
            print(f"⚠️ 第 {attempt + 1} 次 JSON 解析失败，格式异常: {e}")
            print(f"异常内容片段: {raw[:100]}...")
            if attempt == max_retries - 1:
                raise Exception("多次重试后仍然无法生成正确的 JSON，请检查 API 或 Prompt。")
            time.sleep(2) # 失败后稍微等待再重试
            
        except Exception as e:
            print(f"⚠️ 第 {attempt + 1} 次 API 请求发生错误: {e}")
            if attempt == max_retries - 1:
                raise Exception("API 请求多次失败，请检查网络或余额。")
            time.sleep(3)

# ============ 图片生成 ============

def generate_recipe_image(recipe: dict, max_retries: int = 3) -> bytes:
    """针对 gptsapi 自定义 v3 接口的专用生成函数"""
    dish_name = recipe["dish_name"]
    
    # 1. 确保 URL 和 Header 准确
    api_url = "https://api.gptsapi.net/api/v3/openai/gpt-image-2-plus/text-to-image"
    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}', 
        'Content-Type': 'application/json'
    }

    # 2. 优化 Prompt (尽量简洁，避免触发风控)
    image_prompt = f"Professional Chinese food photography of {dish_name}, delicious, warm lighting, 4K."

    payload = {
        "prompt": image_prompt,
        "aspect_ratio": "1:1",
        "output_format": "png"
    }

    for attempt in range(max_retries):
        try:
            print(f"🎨 正在请求自定义接口 (第 {attempt + 1}/{max_retries})...")
            
            # 增加超时时间到 120 秒，因为生图很慢
            response = requests.post(api_url, headers=headers, json=payload, timeout=120)
            
            # 如果状态码不是 200，打印详细内容
            if response.status_code != 200:
                print(f"❌ 接口报错! 状态码: {response.status_code}")
                print(f"❌ 响应内容: {response.text}")
                continue # 进入下一次重试

            result = response.json()
            
            # --- 关键解析逻辑开始 ---
            # 根据该平台可能的返回结构，按优先级尝试获取数据
            image_url = None
            image_b64 = None

            # 结构 1: 直接在根目录有 url (你提供的 curl 猜测)
            # 结构 2: 在 data 数组里 (标准 OpenAI 风格)
            # 结构 3: 在 images 数组里 (某些插件风格)
            if "url" in result:
                image_url = result["url"]
            elif "data" in result and len(result["data"]) > 0:
                image_url = result["data"][0].get("url")
                image_b64 = result["data"][0].get("b64_json")
            elif "images" in result and len(result["images"]) > 0:
                image_url = result["images"][0] # 某些接口直接返回链接数组
            
            # --- 执行获取 ---
            if image_url and str(image_url).startswith('http'):
                print(f"🔗 拿到图片链接，正在下载: {image_url[:50]}...")
                img_data = requests.get(image_url, timeout=60).content
                return img_data
            
            elif image_b64:
                print("📜 拿到 Base64 编码数据，正在解码...")
                import base64
                return base64.b64decode(image_b64)
            
            else:
                print(f"❓ 解析失败，未找到图片字段。原始响应: {result}")
                raise Exception("未找到有效的图片数据字段")

        except Exception as e:
            print(f"⚠️ 第 {attempt + 1} 次生成捕获到异常: {str(e)}")
            if attempt == max_retries - 1:
                raise Exception("自定义图片接口多次尝试均失败。")
            time.sleep(5)

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
