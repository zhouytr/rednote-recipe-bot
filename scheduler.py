"""
定时调度器 - 每日 8:40 自动执行菜谱生成
使用 APScheduler 作为本地定时任务

运行方式：
  python scheduler.py

或使用系统 cron（推荐服务器部署）：
  40 8 * * * cd /your/path && python recipe_generator.py >> logs/recipe.log 2>&1
"""

import logging
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from recipe_generator import run_daily_recipe
from xiaohongshu_publisher import publish_to_xiaohongshu

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/scheduler.log", encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)


def daily_job():
    """每日定时任务：生成内容 + 发布"""
    log.info("🚀 定时任务触发：开始执行每日菜谱流程")
    try:
        # Step 1: 生成菜谱内容和图片
        result = run_daily_recipe()
        log.info(f"✅ 内容生成成功：{result['recipe']['dish_name']}")
        
        # Step 2: 发布到小红书（选择方案）
        publish_result = publish_to_xiaohongshu(
            image_path=result["image_path"],
            post_text=result["post_text"],
            title=result["recipe"]["xiaohongshu_title"],
        )
        
        if publish_result["success"]:
            log.info(f"📱 发布成功！{publish_result.get('message', '')}")
        else:
            log.warning(f"⚠️  发布失败：{publish_result.get('error', '未知错误')}")
            log.info("📋 内容已保存到本地，请手动发布")
            
    except Exception as e:
        log.error(f"❌ 任务执行失败：{e}", exc_info=True)


def main():
    import os
    os.makedirs("logs", exist_ok=True)
    
    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    
    # 每日 8:40 触发
    scheduler.add_job(
        daily_job,
        trigger=CronTrigger(hour=8, minute=40, timezone="Asia/Shanghai"),
        id="daily_recipe",
        name="每日菜谱生成与发布",
        misfire_grace_time=300,  # 5分钟内补发
    )
    
    log.info("⏰ 定时调度器已启动，每日 08:40 (北京时间) 执行")
    log.info("按 Ctrl+C 停止")
    
    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("调度器已停止")


if __name__ == "__main__":
    main()
