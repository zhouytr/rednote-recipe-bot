"""
小红书每日菜谱自动化生成器
功能：
- 每日 8:40 自动触发（配合 cron / GitHub Actions）
- 生成不重复的家常菜菜谱
- 使用 gpt-image-2-plus image-edit 接口生成图片
- 生成小红书格式文案
- 📧 自动发送精美 HTML 邮件到指定邮箱
"""

import os
import json
import base64
import datetime
import time
import smtplib
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from pathlib import Path
from openai import OpenAI

# ============ 配置区（优先读取环境变量，其次用下方默认值）============
OPENAI_API_KEY   = os.environ.get("OPENAI_API_KEY", "")

# QQ 邮箱发件配置
SENDER_EMAIL     = os.environ.get("SENDER_QQ_EMAIL",     "2760717022@qq.com")
SENDER_AUTH_CODE = os.environ.get("SENDER_QQ_AUTH_CODE", "ehihntjmtzmdddca")
RECEIVER_EMAIL   = os.environ.get("RECEIVER_EMAIL",       SENDER_EMAIL)   # 默认发给自己

SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 465   # QQ 邮箱 SSL 端口

OUTPUT_DIR   = Path("./output")
HISTORY_FILE = Path("./history.json")

client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://api.gptsapi.net/v1",
)

# ============ 菜谱历史管理 ============

def load_history() -> list:
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def save_history(history: list):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def get_used_dishes(history: list) -> list:
    return [item["dish_name"] for item in history]

# ============ 菜谱生成 ============

def generate_recipe(used_dishes: list, max_retries: int = 3) -> dict:
    used_str = "、".join(used_dishes[-30:]) if used_dishes else "无"

    prompt = f"""你是一位专业的家常菜厨师，请生成一道适合普通家庭制作的中国家常菜菜谱。

要求：
1. 不能是以下已使用过的菜：{used_str}
2. 食材简单易得，步骤清晰
3. 适合小红书风格（活泼、接地气）
4. JSON 字符串中的换行必须用 \\n，不可直接回车

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

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.lower().startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())

        except json.JSONDecodeError as e:
            print(f"⚠️ 第 {attempt + 1} 次 JSON 解析失败: {e}")
            if attempt == max_retries - 1:
                raise Exception("多次重试后仍无法生成正确的 JSON。")
            time.sleep(2)

        except Exception as e:
            print(f"⚠️ 第 {attempt + 1} 次 API 请求失败: {e}")
            if attempt == max_retries - 1:
                raise Exception("API 请求多次失败，请检查网络或余额。")
            time.sleep(3)

# ============ 图片生成（gpt-image-2-plus 异步轮询）============
#
# 该平台为【异步接口】，调用流程：
#   Step 1: POST 提交任务 → 返回 task_id + result_url（status: "created"）
#   Step 2: GET 轮询 result_url → 直到 status 变为 "succeeded"，outputs 里才有图片
#
# 两个端点均走相同的异步流程，优先使用 text-to-image（无需传参考图，更稳定）

def _poll_result(result_url: str, headers: dict,
                 poll_interval: int = 8, max_wait: int = 90) -> bytes:
    """
    轮询异步任务结果，返回图片二进制数据。
    - poll_interval=8s，避免限流
    - max_wait=90s，超时放弃，不阻塞 Actions
    - 每次都打印完整响应，方便排查
    """
    waited = 0
    while waited < max_wait:
        time.sleep(poll_interval)
        waited += poll_interval

        try:
            resp = requests.get(result_url, headers=headers, timeout=30)
        except Exception as e:
            print(f"   轮询请求异常: {e}，继续等待...")
            continue

        print(f"   [{waited}s] HTTP {resp.status_code} | 响应: {resp.text[:400]}")

        if resp.status_code != 200:
            continue

        try:
            data = resp.json()
        except Exception:
            print(f"   响应非 JSON，跳过")
            continue

        # 兼容 {"data": {"status":...}} 和直接 {"status":...}
        task = data.get("data", data)
        status = str(task.get("status", "")).lower()

        if status == "succeeded":
            outputs = task.get("outputs", [])
            if outputs:
                img_url = outputs[0]
                print(f"   生图完成！下载: {img_url[:80]}...")
                img_resp = requests.get(img_url, timeout=60)
                if img_resp.status_code == 200:
                    return img_resp.content
                raise Exception(f"图片下载失败 HTTP {img_resp.status_code}")
            # succeeded 但 outputs 还是空（平台偶发），再等一轮
            print(f"   status=succeeded 但 outputs=[]，再等一轮...")
            continue

        if status in ("failed", "canceled", "error"):
            raise Exception(f"任务失败 status={status}，响应: {data}")

        # processing / created / running → 继续等
        print(f"   status={status}，继续等待...")

    raise Exception(f"轮询超时（>{max_wait}s），任务未完成，放弃")


def generate_recipe_image(recipe: dict) -> bytes:
    """
    提交图片生成任务并轮询结果，返回图片二进制数据。
    优先使用 text-to-image，失败后自动降级到 image-edit。
    """
    dish_name = recipe["dish_name"]
    tagline   = recipe.get("tagline", "")

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    image_prompt = (
        f"Professional Chinese food photography of {dish_name}. "
        f"{tagline}. "
        "Beautifully plated on a wooden table, warm studio lighting, "
        "shallow depth of field, 45-degree angle, vibrant appetizing colors, "
        "no text, no watermark, 4K quality."
    )

    # 优先用 text-to-image，失败再试 image-edit
    endpoints = [
        {
            "name": "text-to-image",
            "url":  "https://api.gptsapi.net/api/v3/openai/gpt-image-2-plus/text-to-image",
            "payload": {
                "prompt":        image_prompt,
                "aspect_ratio":  "1:1",
                "output_format": "png",
            },
        },
        {
            "name": "image-edit",
            "url":  "https://api.gptsapi.net/api/v3/openai/gpt-image-2-plus/image-edit",
            "payload": {
                "prompt":        image_prompt,
                "images":        ["https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=512&q=80"],
                "output_format": "png",
            },
        },
    ]

    last_err = None
    for ep in endpoints:
        try:
            print(f"🎨 提交生图任务（{ep['name']}）...")
            resp = requests.post(ep["url"], headers=headers, json=ep["payload"], timeout=30)
            print(f"   HTTP {resp.status_code}")

            if resp.status_code != 200:
                print(f"   ❌ 提交失败: {resp.text[:300]}")
                last_err = f"HTTP {resp.status_code}"
                continue

            result = resp.json()
            print(f"   提交响应: {json.dumps(result, ensure_ascii=False)[:300]}")

            # 取轮询地址：优先 data.urls.get，其次根级别 urls.get
            task_data  = result.get("data", result)
            result_url = (
                task_data.get("urls", {}).get("get")
                or result.get("urls", {}).get("get")
            )

            if not result_url:
                raise Exception(f"未找到轮询 URL，响应: {result}")

            print(f"   🔗 轮询地址: {result_url}")
            return _poll_result(result_url, headers)

        except Exception as e:
            print(f"   ⚠️ {ep['name']} 失败: {e}")
            last_err = str(e)
            time.sleep(3)

    raise Exception(f"所有图片接口均失败，最后错误: {last_err}")

# ============ 文案构建 ============

def build_xiaohongshu_post(recipe: dict) -> str:
    tags = " ".join(recipe["tags"])
    return (
        f"{recipe['xiaohongshu_title']}\n\n"
        f"{recipe['xiaohongshu_body']}\n\n"
        f"{tags}\n#家常菜 #厨房日记 #简单美食 #每日菜谱"
    )

# ============ 邮件发送 ============

def build_email_html(recipe: dict, today: str) -> str:
    """生成精美的 HTML 邮件正文"""
    ingredient_rows = "".join(
        f"<tr>"
        f"<td style='padding:8px 14px;border-bottom:1px solid #f5ebe0;'>{ing['name']}</td>"
        f"<td style='padding:8px 14px;border-bottom:1px solid #f5ebe0;color:#c0392b;font-weight:600;'>{ing['amount']}</td>"
        f"</tr>"
        for ing in recipe["ingredients"]
    )

    step_items = "".join(
        f"""<div style='display:flex;gap:14px;margin-bottom:16px;align-items:flex-start;'>
              <div style='min-width:30px;height:30px;background:#e74c3c;color:white;border-radius:50%;
                          font-weight:bold;font-size:14px;flex-shrink:0;line-height:30px;text-align:center;'>{s['step']}</div>
              <div>
                <div style='font-weight:600;color:#2c3e50;margin-bottom:3px;'>{s['action']}</div>
                <div style='color:#666;font-size:14px;line-height:1.6;'>{s['detail']}</div>
              </div>
            </div>"""
        for s in recipe["steps"]
    )

    tip_items = "".join(
        f"<li style='margin-bottom:7px;color:#555;font-size:14px;line-height:1.6;'>{tip}</li>"
        for tip in recipe["tips"]
    )

    tag_spans = "".join(
        f"<span style='background:#fff0f0;color:#e74c3c;border-radius:20px;padding:4px 11px;"
        f"font-size:13px;margin:3px;display:inline-block;'>{tag}</span>"
        for tag in recipe["tags"] + ["#家常菜", "#厨房日记", "#简单美食", "#每日菜谱"]
    )

    body_html = recipe["xiaohongshu_body"].replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f8f4ef;font-family:'PingFang SC','Microsoft YaHei',sans-serif;">
<div style="max-width:620px;margin:30px auto;background:white;border-radius:16px;
            overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.10);">

  <!-- 顶部 Banner -->
  <div style="background:linear-gradient(135deg,#e74c3c 0%,#c0392b 100%);padding:30px 32px;text-align:center;">
    <div style="font-size:12px;color:rgba(255,255,255,0.75);letter-spacing:3px;margin-bottom:10px;text-transform:uppercase;">
      TODAY'S RECIPE · {today}
    </div>
    <div style="font-size:48px;margin-bottom:8px;">{recipe['dish_emoji']}</div>
    <div style="font-size:28px;font-weight:700;color:white;margin-bottom:8px;">{recipe['dish_name']}</div>
    <div style="display:inline-block;background:rgba(255,255,255,0.2);color:white;
                border-radius:20px;padding:5px 16px;font-size:14px;">{recipe['tagline']}</div>
  </div>

  <!-- 菜品图片 -->
  <div style="background:#fdf6f0;text-align:center;padding:24px 24px 8px;">
    <img src="cid:recipe_image" alt="{recipe['dish_name']}"
         style="max-width:100%;border-radius:12px;box-shadow:0 4px 16px rgba(0,0,0,0.12);"
         onerror="this.parentElement.style.display='none'">
  </div>

  <div style="padding:28px 32px;">

    <!-- 食材清单 -->
    <h2 style="font-size:17px;color:#2c3e50;border-left:4px solid #e74c3c;
               padding-left:12px;margin:0 0 16px;">🛒 食材清单</h2>
    <table style="width:100%;border-collapse:collapse;background:#fffaf7;
                  border-radius:10px;overflow:hidden;margin-bottom:28px;font-size:14px;">
      <thead>
        <tr style="background:#e74c3c;">
          <th style="padding:10px 14px;color:white;text-align:left;font-weight:600;">食材</th>
          <th style="padding:10px 14px;color:white;text-align:left;font-weight:600;">用量</th>
        </tr>
      </thead>
      <tbody>{ingredient_rows}</tbody>
    </table>

    <!-- 烹饪步骤 -->
    <h2 style="font-size:17px;color:#2c3e50;border-left:4px solid #e74c3c;
               padding-left:12px;margin:0 0 18px;">👨‍🍳 烹饪步骤</h2>
    <div style="margin-bottom:28px;">{step_items}</div>

    <!-- 小贴士 -->
    <div style="background:#fffbf0;border:1px solid #fde3a7;border-radius:10px;
                padding:16px 20px;margin-bottom:28px;">
      <div style="font-weight:600;color:#d68910;margin-bottom:10px;font-size:15px;">💡 厨房小贴士</div>
      <ul style="margin:0;padding-left:18px;">{tip_items}</ul>
    </div>

    <!-- 小红书文案 -->
    <h2 style="font-size:17px;color:#2c3e50;border-left:4px solid #e74c3c;
               padding-left:12px;margin:0 0 16px;">📱 小红书文案（复制即可发布）</h2>
    <div style="background:#fff5f5;border:1px dashed #f1a1a1;border-radius:10px;
                padding:20px;margin-bottom:20px;">
      <div style="font-weight:700;font-size:16px;color:#c0392b;margin-bottom:12px;">
        {recipe['xiaohongshu_title']}
      </div>
      <div style="color:#444;font-size:14px;line-height:1.9;">{body_html}</div>
    </div>

    <!-- 标签 -->
    <div style="margin-bottom:28px;">{tag_spans}</div>

    <hr style="border:none;border-top:1px solid #f0e6d3;margin:20px 0;">

    <div style="text-align:center;color:#bbb;font-size:12px;line-height:1.8;">
      🤖 由 AI 自动生成 &nbsp;·&nbsp; 每日 8:40 准时送达<br>
      Powered by GPT-4o &amp; gpt-image-2-plus
    </div>
  </div>
</div>
</body>
</html>"""


def send_email(recipe: dict, image_bytes: bytes | None, today: str):
    """通过 QQ 邮箱 SMTP 发送 HTML 邮件，菜品图内嵌显示"""
    print(f"📧 正在发送邮件至 {RECEIVER_EMAIL} ...")

    msg = MIMEMultipart("related")
    msg["Subject"] = f"🍳 今日菜谱：{recipe['dish_name']} {recipe['dish_emoji']} | {today}"
    msg["From"]    = f"每日菜谱机器人 <{SENDER_EMAIL}>"
    msg["To"]      = RECEIVER_EMAIL

    html_body = build_email_html(recipe, today)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if image_bytes:
        img = MIMEImage(image_bytes, _subtype="png")
        img.add_header("Content-ID", "<recipe_image>")
        img.add_header("Content-Disposition", "inline", filename=f"{recipe['dish_name']}.png")
        msg.attach(img)

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(SENDER_EMAIL, SENDER_AUTH_CODE)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())

    print(f"✅ 邮件发送成功！收件人：{RECEIVER_EMAIL}")

# ============ 主流程 ============

def run_daily_recipe():
    OUTPUT_DIR.mkdir(exist_ok=True)
    today = datetime.date.today().strftime("%Y-%m-%d")

    print(f"\n🍳 [{today}] 开始生成今日内容...")

    # 1. 历史记录防重复
    history     = load_history()
    used_dishes = get_used_dishes(history)
    print(f"📋 已有 {len(used_dishes)} 道菜历史记录")

    # 2. 生成菜谱文案
    print("✍️  正在构思菜谱文案...")
    try:
        recipe = generate_recipe(used_dishes)
        print(f"✅ 今日菜谱：{recipe['dish_name']}")
    except Exception as e:
        print(f"❌ 菜谱文案生成失败: {e}")
        return

    # 3. 生成配图
    image_bytes = None
    image_path  = "生成失败"
    try:
        print("🎨 正在绘制菜谱配图...")
        image_bytes = generate_recipe_image(recipe)
        image_path  = OUTPUT_DIR / f"{today}_{recipe['dish_name']}.png"
        with open(image_path, "wb") as f:
            f.write(image_bytes)
        print(f"💾 图片已保存：{image_path}")
    except Exception as e:
        print(f"⚠️ 图片生成失败（继续生成文案和邮件）: {e}")

    # 4. 保存文案 & JSON
    post_text = build_xiaohongshu_post(recipe)
    text_path = OUTPUT_DIR / f"{today}_{recipe['dish_name']}_post.txt"
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(post_text)

    recipe_json_path = OUTPUT_DIR / f"{today}_{recipe['dish_name']}_recipe.json"
    with open(recipe_json_path, "w", encoding="utf-8") as f:
        json.dump(recipe, f, ensure_ascii=False, indent=2)

    # 5. 📧 发送邮件
    try:
        send_email(recipe, image_bytes, today)
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        print("   检查：① QQ 邮箱是否开启 SMTP 服务 ② 授权码是否正确")

    # 6. 更新历史
    history.append({
        "date":       today,
        "dish_name":  recipe["dish_name"],
        "image_path": str(image_path),
        "post_path":  str(text_path),
    })
    save_history(history)

    print(f"\n{'='*52}")
    print(f"🎉 今日内容生成完毕！")
    print(f"   菜名：{recipe['dish_name']} {recipe['dish_emoji']}")
    print(f"   标题：{recipe['xiaohongshu_title']}")
    print(f"{'='*52}\n")
    print("📱 文案预览：")
    print(post_text)


if __name__ == "__main__":
    run_daily_recipe()
