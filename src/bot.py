import asyncio
import aiohttp
import logging
from typing import Set
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from lightstreamer.client import LightstreamerClient, Subscription
from config import (
    TELEGRAM_TOKEN,
    CHECK_INTERVAL,
    SUBSCRIBERS_FILE,
    MIN_CHANGE_THRESHOLD
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class ISSUrineTracker:
    def __init__(self):
        self.subscribers: Set[int] = set()
        self.last_urine_level: float = 0.0
        self.load_subscribers()
        self.lightstreamer_client = None
        self.current_value = None

    def load_subscribers(self) -> None:
        try:
            with open(SUBSCRIBERS_FILE, 'r') as f:
                self.subscribers = set(map(int, f.read().splitlines()))
        except FileNotFoundError:
            self.subscribers = set()

    def save_subscribers(self) -> None:
        with open(SUBSCRIBERS_FILE, 'w') as f:
            f.write('\n'.join(map(str, self.subscribers)))

    def on_item_update(self, item_name, value, timestamp):
        if item_name == "NODE3000005":
            try:
                self.current_value = float(value["Value"])
                logger.info(f"Received urine tank update: {self.current_value}")
            except ValueError as e:
                logger.error(f"Could not convert urine tank value '{value}' to float: {e}")

    async def connect_lightstreamer(self):
        # Connect to Lightstreamer
        self.lightstreamer_client = LightstreamerClient("https://push.lightstreamer.com", "ISSLIVE")
        self.lightstreamer_client.connect()

        # Subscribe to NODE3000005 (Urine Tank)
        subscription = Subscription(
            mode="MERGE",
            items=["NODE3000005"],
            fields=["Value", "TimeStamp"]
        )
        subscription.addListener(self.on_item_update)
        self.lightstreamer_client.subscribe(subscription)

    async def check_urine_level(self) -> float:
        return self.current_value

    async def monitor_urine_level(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        current_level = await self.check_urine_level()
        
        if current_level is None:
            return

        if abs(current_level - self.last_urine_level) >= MIN_CHANGE_THRESHOLD:
            change = current_level - self.last_urine_level
            message = (
                f"🚽 ISS Urine Tank Update!\n"
                f"Previous level: {self.last_urine_level:.1f}%\n"
                f"Current level: {current_level:.1f}%\n"
                f"Change: {change:+.1f}%"
            )
            
            for chat_id in self.subscribers:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=message)
                except Exception as e:
                    logger.error(f"Failed to send message to {chat_id}: {e}")
            
            self.last_urine_level = current_level

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if chat_id not in tracker.subscribers:
        tracker.subscribers.add(chat_id)
        tracker.save_subscribers()
        await update.message.reply_text(
            "Welcome to ISS Urine Tank Tracker! 🚀🚽\n"
            "You will receive notifications when the urine tank level changes."
        )
    else:
        await update.message.reply_text("You're already subscribed!")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if chat_id in tracker.subscribers:
        tracker.subscribers.remove(chat_id)
        tracker.save_subscribers()
        await update.message.reply_text("You've been unsubscribed from notifications.")
    else:
        await update.message.reply_text("You weren't subscribed!")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_level = await tracker.check_urine_level()
    if current_level is not None:
        await update.message.reply_text(
            f"Current ISS Urine Tank Level: {current_level:.1f}%"
        )
    else:
        await update.message.reply_text("Unable to fetch current urine tank level.")

def main() -> None:
    # Initialize the application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("status", status))

    # Initialize job queue
    job_queue = application.job_queue
    
    # Start the job after the application is running
    async def start_jobs(application: Application) -> None:
        await tracker.connect_lightstreamer()
        job_queue.run_repeating(tracker.monitor_urine_level, interval=CHECK_INTERVAL, first=1)

    application.post_init = start_jobs

    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    tracker = ISSUrineTracker()
    main() 