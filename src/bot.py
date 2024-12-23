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
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

class ISSUrineTracker:
    def __init__(self):
        self.subscribers: Set[int] = set()
        self.last_urine_level: float = 0.0
        self.load_subscribers()
        self.lightstreamer_client = None
        self.current_value = None
        self.subscription = None
        self.connected = False

    def load_subscribers(self) -> None:
        try:
            with open(SUBSCRIBERS_FILE, 'r') as f:
                self.subscribers = set(map(int, f.read().splitlines()))
        except FileNotFoundError:
            self.subscribers = set()

    def save_subscribers(self) -> None:
        with open(SUBSCRIBERS_FILE, 'w') as f:
            f.write('\n'.join(map(str, self.subscribers)))

    def onStatusChange(self, status):
        """Called when the connection status changes"""
        logger.info(f"Lightstreamer connection status changed to: {status}")
        if status.startswith("CONNECTED:"):  # Accept any CONNECTED status
            self.connected = True
        elif status == "DISCONNECTED":
            self.connected = False

    def onServerError(self, code, message):
        """Called when the server returns an error"""
        logger.error(f"Lightstreamer server error: {code} - {message}")

    def onPropertyChange(self, property_name):
        """Called when a property of the LightstreamerClient changes"""
        logger.debug(f"Lightstreamer property changed: {property_name}")

    def onItemUpdate(self, update):
        """Called when we receive an update"""
        try:
            logger.debug(f"Raw update received: {update}")
            
            if isinstance(update, dict):
                # Handle initial snapshot
                logger.info(f"Received snapshot: {update}")
                if "Value" in update:
                    try:
                        self.current_value = float(update["Value"])
                        logger.info(f"Initial value set to: {self.current_value}")
                        self.last_urine_level = self.current_value
                    except ValueError as e:
                        logger.error(f"Could not convert initial value '{update['Value']}' to float: {e}")
            else:
                # Handle updates
                item_name = update.getItemName()
                if item_name == "NODE3000005":
                    value = update.getValue("Value")
                    timestamp = update.getValue("TimeStamp")
                    status = update.getValue("Status.Class")
                    
                    if value is not None:  # Accept any status for now, just log it
                        try:
                            self.current_value = float(value)
                            logger.info(f"Received urine tank update: {self.current_value} at {timestamp} (Status: {status})")
                        except ValueError as e:
                            logger.error(f"Could not convert value '{value}' to float: {e}")
                    
                    if status != "24":  # Just log non-default status
                        logger.warning(f"Received update with non-default status: {status}")
                
        except Exception as e:
            logger.error(f"Error processing update: {e}", exc_info=True)

    def onEndOfSnapshot(self, item_name, item_pos):
        """Called when a snapshot is complete"""
        logger.info(f"End of snapshot for {item_name}")

    def onClearSnapshot(self, item_name, item_pos):
        """Called when the snapshot is cleared"""
        logger.info(f"Snapshot cleared for {item_name}")

    def onSubscription(self):
        """Called when the subscription is successfully established"""
        logger.info("Subscription successfully established")

    def onUnsubscription(self):
        """Called when the subscription is successfully closed"""
        logger.info("Subscription successfully closed")

    def onSubscriptionError(self, code, message):
        """Called when the server rejects a subscription"""
        logger.error(f"Subscription error: {code} - {message}")

    async def connect_lightstreamer(self):
        try:
            # Connect to Lightstreamer
            self.lightstreamer_client = LightstreamerClient("https://push.lightstreamer.com", "ISSLIVE")
            
            # Add connection status listener
            self.lightstreamer_client.addListener(self)
            
            # Configure subscription for NODE3000005 (Urine Tank)
            self.subscription = Subscription(
                mode="MERGE",
                items=["NODE3000005"],
                fields=["Value", "TimeStamp", "Status.Class"]
            )
            self.subscription.setRequestedSnapshot("yes")
            self.subscription.addListener(self)
            
            logger.info("Connecting to Lightstreamer...")
            
            # Connect and subscribe
            self.lightstreamer_client.connect()
            
            # Wait for initial connection
            for _ in range(30):  # Wait up to 30 seconds
                if self.connected:
                    self.lightstreamer_client.subscribe(self.subscription)
                    logger.info("Successfully connected to Lightstreamer")
                    return
                await asyncio.sleep(1)
            
            if not self.connected:
                raise Exception("Failed to connect to Lightstreamer after 30 seconds")

        except Exception as e:
            logger.error(f"Error connecting to Lightstreamer: {e}", exc_info=True)
            raise

    async def check_urine_level(self) -> float:
        if self.current_value is None:
            logger.warning("No urine tank value available yet")
        return self.current_value

    async def monitor_urine_level(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        if self.current_value is None:
            logger.warning("Skipping monitor - no value available yet")
            return

        if abs(self.current_value - self.last_urine_level) >= MIN_CHANGE_THRESHOLD:
            change = self.current_value - self.last_urine_level
            message = (
                f"🚽 ISS Urine Tank Update!\n"
                f"Previous level: {self.last_urine_level:.1f}%\n"
                f"Current level: {self.current_value:.1f}%\n"
                f"Change: {change:+.1f}%"
            )
            
            logger.info(f"Sending update to {len(self.subscribers)} subscribers")
            for chat_id in self.subscribers:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=message)
                except Exception as e:
                    logger.error(f"Failed to send message to {chat_id}: {e}")
            
            self.last_urine_level = self.current_value

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        current_level = await self.check_urine_level()
        connection_status = "Connected" if self.connected else "Disconnected"
        if current_level is not None:
            await update.message.reply_text(
                f"Connection Status: {connection_status}\n"
                f"Current ISS Urine Tank Level: {current_level:.1f}%"
            )
        else:
            await update.message.reply_text(
                f"Connection Status: {connection_status}\n"
                "Unable to fetch current urine tank level."
            )

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

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Test command to verify connection and last received values"""
    connection_status = "Connected" if tracker.connected else "Disconnected"
    current_value = tracker.current_value
    last_update = tracker.last_urine_level
    
    message = (
        f"🔍 Connection Test:\n"
        f"Connection Status: {connection_status}\n"
        f"Current Value: {f'{current_value:.1f}%' if current_value is not None else 'None'}\n"
        f"Last Update Value: {f'{last_update:.1f}%' if last_update is not None else 'None'}\n"
    )
    await update.message.reply_text(message)

def main() -> None:
    # Initialize the application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("test", test))

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