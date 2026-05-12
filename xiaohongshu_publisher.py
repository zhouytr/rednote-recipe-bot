"""
小红书发布模块
提供两种发布策略：
  A. 企业号 API（需申请资质）
  B. Playwright 浏览器自动化（模拟操作）
  C. 微信/钉钉通知 + 手动确认（最稳妥）
"""

import os
import time
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# 选择发布策略：'browser' | 'notify' | 'webhook'
PUBLISH_STRATEGY = os.environ.get("PUBLISH_STRATEGY", "notify")

# ============ 策略 B：Playwright 浏览器自动化 ============

def publish_via_browser(image_path: str, post_text: str, title: str) -> dict:
    """
    使用 Playwright 模拟浏览器操作发布到小红书
    ⚠️ 注意：此方案有被封号风险，建议仅用于测试
    需要先运行：playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"success": False, "error": "请先安装：pip install playwright && playwright install chromium"}

    XHS_PHONE = os.environ.get("XHS_PHONE", "")
    XHS_PASSWORD = os.environ.get("XHS_PASSWORD", "")
    
    if not XHS_PHONE:
        return {"success": False, "error": "未设置 XHS_PHONE 环境变量"}
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)  # 建议先 headless=False 调试
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            page = context.new_page()
            
            # 1. 打开创作者中心
            page.goto("https://creator.xiaohongshu.com/publish/publish")
            time.sleep(3)
            
            # 2. 如果需要登录
            if "login" in page.url or page.locator(".login-container").count() > 0:
                log.info("需要登录小红书...")
                # 等待手动扫码或输入验证码
                # 建议第一次手动登录，之后保存 cookies
                page.wait_for_url("**/publish**", timeout=60000)
            
            # 3. 上传图片
            page.locator("input[type='file']").set_input_files(image_path)
            time.sleep(5)
            
            # 4. 填写标题
            title_input = page.locator(".titleInput, [placeholder*='标题']").first
            title_input.click()
            title_input.fill(title[:20])  # 小红书标题限制
            
            # 5. 填写正文
            content_input = page.locator(".contenteditable, [placeholder*='内容']").first
            content_input.click()
            content_input.fill(post_text)
            time.sleep(2)
            
            # 6. 点击发布
            publish_btn = page.locator("button:has-text('发布'), .publish-btn").first
            publish_btn.click()
            time.sleep(3)
            
            log.info("✅ 发布操作完成")
            browser.close()
            
            return {"success": True, "message": "已通过浏览器自动化发布"}
            
    except Exception as e:
        log.error(f"浏览器自动化发布失败：{e}")
        return {"success": False, "error": str(e)}


# ============ 策略 C：通知推送（推荐） ============

def publish_via_notification(image_path: str, post_text: str, title: str) -> dict:
    """
    发送通知到手机，提醒手动发布（最稳妥方案）
    支持：Server酱、企业微信、钉钉
    """
    results = []
    
    # --- Server酱推送（微信通知）---
    serverchan_key = os.environ.get("SERVERCHAN_KEY", "")
    if serverchan_key:
        try:
            import requests
            short_text = post_text[:500] + "..." if len(post_text) > 500 else post_text
            resp = requests.post(
                f"https://sctapi.ftqq.com/{serverchan_key}.send",
                data={
                    "title": f"🍳 今日菜谱已就绪：{title}",
                    "desp": f"## 今日小红书内容\n\n**标题：** {title}\n\n**文案：**\n{short_text}\n\n**图片路径：** {image_path}\n\n> 请打开小红书发布以上内容",
                },
                timeout=10
            )
            if resp.json().get("code") == 0:
                results.append("✅ Server酱微信通知已发送")
            else:
                results.append(f"⚠️ Server酱通知失败：{resp.text}")
        except Exception as e:
            results.append(f"❌ Server酱通知异常：{e}")
    
    # --- 钉钉机器人推送 ---
    dingtalk_webhook = os.environ.get("DINGTALK_WEBHOOK", "")
    if dingtalk_webhook:
        try:
            import requests
            resp = requests.post(
                dingtalk_webhook,
                json={
                    "msgtype": "markdown",
                    "markdown": {
                        "title": f"今日菜谱：{title}",
                        "text": f"## 🍳 今日小红书菜谱\n\n**{title}**\n\n{post_text[:400]}...\n\n> 图片：{image_path}"
                    }
                },
                timeout=10
            )
            results.append(f"✅ 钉钉通知已发送")
        except Exception as e:
            results.append(f"❌ 钉钉通知异常：{e}")
    
    # --- Bark 推送（iOS）---
    bark_key = os.environ.get("BARK_KEY", "")
    if bark_key:
        try:
            import requests
            requests.get(
                f"https://api.day.app/{bark_key}/今日菜谱已生成/{title}",
                params={"group": "小红书菜谱", "icon": "https://example.com/food.png"},
                timeout=10
            )
            results.append("✅ Bark iOS通知已发送")
        except Exception as e:
            results.append(f"❌ Bark通知异常：{e}")
    
    if results:
        log.info("\n".join(results))
        return {"success": True, "message": "\n".join(results)}
    else:
        log.warning("未配置任何通知渠道，内容已保存到本地")
        return {"success": True, "message": "内容已保存到本地 output/ 目录"}


# ============ 策略 A：Webhook（n8n / Make.com）============

def publish_via_webhook(image_path: str, post_text: str, title: str) -> dict:
    """
    通过 n8n 或 Make.com 的 Webhook 触发后续发布流程
    """
    webhook_url = os.environ.get("N8N_WEBHOOK_URL", "")
    if not webhook_url:
        return {"success": False, "error": "未设置 N8N_WEBHOOK_URL"}
    
    try:
        import requests
        # 将图片转为 base64
        with open(image_path, "rb") as f:
            import base64
            image_b64 = base64.b64encode(f.read()).decode()
        
        payload = {
            "title": title,
            "post_text": post_text,
            "image_base64": image_b64,
            "image_filename": Path(image_path).name,
            "platform": "xiaohongshu",
        }
        
        resp = requests.post(webhook_url, json=payload, timeout=30)
        if resp.status_code == 200:
            return {"success": True, "message": f"Webhook 触发成功：{resp.text}"}
        else:
            return {"success": False, "error": f"Webhook 响应 {resp.status_code}：{resp.text}"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============ 主入口 ============

def publish_to_xiaohongshu(image_path: str, post_text: str, title: str) -> dict:
    """根据配置选择发布策略"""
    strategy = PUBLISH_STRATEGY
    log.info(f"📤 使用发布策略：{strategy}")
    
    if strategy == "browser":
        return publish_via_browser(image_path, post_text, title)
    elif strategy == "webhook":
        return publish_via_webhook(image_path, post_text, title)
    else:  # notify（默认）
        return publish_via_notification(image_path, post_text, title)
