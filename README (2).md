# 🍳 小红书每日菜谱自动化机器人

每日 **8:40** 自动生成家常菜菜谱，包含 AI 生成图片和文案，并推送到你的手机。

---

## 📁 项目结构

```
xiaohongshu_recipe_bot/
├── recipe_generator.py      # 核心：GPT生成菜谱 + DALL-E生成图片
├── xiaohongshu_publisher.py # 发布模块（三种策略）
├── scheduler.py             # 定时调度器（每日8:40触发）
├── requirements.txt         # 依赖包
├── .env.example             # 环境变量模板
├── output/                  # 生成的图片和文案（自动创建）
├── history.json             # 菜谱历史记录（自动创建，防重复）
└── logs/                    # 运行日志（自动创建）
```

---

## 🚀 快速开始

### 第一步：安装依赖

```bash
pip install -r requirements.txt
playwright install chromium  # 如果使用浏览器策略
```

### 第二步：配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填写你的 OpenAI API Key 和通知配置
```

### 第三步：测试运行

```bash
# 立即生成今日菜谱（不等到8:40）
python recipe_generator.py

# 查看 output/ 目录中生成的图片和文案
```

### 第四步：启动定时任务

**方案A：Python 常驻进程（适合本地/个人服务器）**
```bash
python scheduler.py
# 程序会一直运行，每天8:40自动触发
```

**方案B：系统 Cron（推荐服务器部署）**
```bash
# 编辑 crontab
crontab -e

# 添加以下行（北京时间8:40）
40 8 * * * cd /your/project/path && python recipe_generator.py >> logs/recipe.log 2>&1
```

**方案C：GitHub Actions（免费云端定时）**
```yaml
# 创建 .github/workflows/daily_recipe.yml
name: Daily Recipe
on:
  schedule:
    - cron: '40 0 * * *'  # UTC 0:40 = 北京时间 8:40
jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: pip install -r requirements.txt
      - run: python recipe_generator.py
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          SERVERCHAN_KEY: ${{ secrets.SERVERCHAN_KEY }}
```

---

## 📱 发布策略选择

### 策略1：通知推送（推荐✅）

配置 `PUBLISH_STRATEGY=notify`

每天8:40生成内容后，通过以下渠道推送到你手机：
- **Server酱** → 微信消息通知
- **Bark** → iOS 推送通知
- **钉钉机器人** → 钉钉群消息

收到通知后，打开小红书手动复制粘贴发布（30秒搞定）。

**优点**：零封号风险，内容完全由你把控

### 策略2：n8n 自动化（进阶✅）

配置 `PUBLISH_STRATEGY=webhook`

搭配 n8n 工作流，实现：
1. 本脚本生成内容 → 发送 Webhook 到 n8n
2. n8n 接收 → 保存图片到 Google Drive
3. n8n 发送完整内容到你的手机/邮件
4. （可选）通过小红书企业号 API 发布

### 策略3：浏览器自动化（高风险⚠️）

配置 `PUBLISH_STRATEGY=browser`

使用 Playwright 模拟浏览器操作自动发布。

**风险**：小红书检测到自动化行为可能封号，仅建议测试使用。

---

## 📋 生成内容示例

**菜名**：鱼香茄子
**标题**：这道鱼香茄子让我男友以为我去厨师学校了🍆

**文案**：
```
今天给大家分享超级下饭的鱼香茄子！

不需要鱼，照样鱼香味十足✨

【食材】
茄子 2根 | 猪肉末 100g | 豆瓣酱 1勺
蒜末 适量 | 姜末 适量 | 糖/醋/生抽 各适量

【步骤】
1️⃣ 茄子切条，撒盐腌10分钟去水
2️⃣ 热锅冷油，茄子炸至金黄捞出
3️⃣ 留底油爆香蒜姜，加豆瓣酱炒出红油
4️⃣ 下肉末炒散，倒入调好的鱼香汁
5️⃣ 茄子回锅翻炒，大火收汁装盘！

小贴士：鱼香汁 = 糖2勺+醋1勺+生抽1勺+淀粉半勺+水3勺提前调好！

你们喜欢吃茄子嗷？评论区告诉我🍆

#家常菜 #鱼香茄子 #下饭神器 #厨房新手 #每日菜谱
```

---

## ❓ 常见问题

**Q：生成的图片不够好看？**
A：修改 `recipe_generator.py` 中的 `image_prompt` 变量，添加更详细的描述

**Q：想换成竖版 9:16 图片？**
A：将 `size="1024x1792"` 改为 `size="1024x1792"`（DALL-E 3 最大竖版）

**Q：OpenAI 费用怎么控制？**
A：每次运行约消耗 $0.05-0.10（GPT-4o + DALL-E 3），每月约 $1.5-3

**Q：菜谱历史记录在哪？**
A：`history.json` 文件，可以手动编辑删除某道菜以便重新生成
