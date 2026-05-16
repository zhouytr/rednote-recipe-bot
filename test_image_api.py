"""
快速诊断脚本：测试 gptsapi image-edit 接口
运行：python test_image_api.py
"""

import os
import requests
import json

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

if not OPENAI_API_KEY:
    print("❌ 未检测到 OPENAI_API_KEY 环境变量，请先设置：")
    print("   export OPENAI_API_KEY=你的key")
    exit(1)

print(f"🔑 Key 前缀: {OPENAI_API_KEY[:8]}...")

# ── 测试 1：image-edit 接口 ──────────────────────────────────
print("\n" + "="*55)
print("测试 1：gpt-image-2-plus / image-edit")
print("="*55)

url = "https://api.gptsapi.net/api/v3/openai/gpt-image-2-plus/image-edit"
headers = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json",
}
payload = {
    "prompt": "A bowl of Chinese tomato egg soup, food photography.",
    "images": ["https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=512&q=80"],
    "output_format": "png",
}

try:
    print(f"→ POST {url}")
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    print(f"← HTTP {resp.status_code}")
    try:
        data = resp.json()
        print(f"← JSON: {json.dumps(data, ensure_ascii=False, indent=2)[:800]}")
    except Exception:
        print(f"← 非 JSON 响应: {resp.text[:500]}")
except Exception as e:
    print(f"← 请求异常: {e}")

# ── 测试 2：text-to-image 接口（备选）────────────────────────
print("\n" + "="*55)
print("测试 2：gpt-image-2-plus / text-to-image（备选）")
print("="*55)

url2 = "https://api.gptsapi.net/api/v3/openai/gpt-image-2-plus/text-to-image"
payload2 = {
    "prompt": "A bowl of Chinese tomato egg soup, food photography.",
    "aspect_ratio": "1:1",
    "output_format": "png",
}

try:
    print(f"→ POST {url2}")
    resp2 = requests.post(url2, headers=headers, json=payload2, timeout=60)
    print(f"← HTTP {resp2.status_code}")
    try:
        data2 = resp2.json()
        print(f"← JSON: {json.dumps(data2, ensure_ascii=False, indent=2)[:800]}")
    except Exception:
        print(f"← 非 JSON 响应: {resp2.text[:500]}")
except Exception as e:
    print(f"← 请求异常: {e}")

# ── 测试 3：标准 OpenAI DALL-E 3 接口（最后兜底）────────────
print("\n" + "="*55)
print("测试 3：标准 OpenAI images/generations（DALL-E 3）")
print("="*55)

url3 = "https://api.gptsapi.net/v1/images/generations"
payload3 = {
    "model": "dall-e-3",
    "prompt": "A bowl of Chinese tomato egg soup, food photography, 4K.",
    "n": 1,
    "size": "1024x1024",
}

try:
    print(f"→ POST {url3}")
    resp3 = requests.post(url3, headers=headers, json=payload3, timeout=60)
    print(f"← HTTP {resp3.status_code}")
    try:
        data3 = resp3.json()
        print(f"← JSON: {json.dumps(data3, ensure_ascii=False, indent=2)[:800]}")
    except Exception:
        print(f"← 非 JSON 响应: {resp3.text[:500]}")
except Exception as e:
    print(f"← 请求异常: {e}")

print("\n✅ 诊断完成，请把上方输出结果告诉我！")
