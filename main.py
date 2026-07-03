import sys
import os
import logging
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import config
from database.sqlite_db import SQLiteDatabase
from google_sheets.sheets_sync import GoogleSheetsSyncManager
from bot.handlers import BotHandlerManager
from bot.permission_handler import (
    build_permission_conversation_handler,
    handle_approval_callback,
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main() -> None:
    """Main application launcher."""
    print("====================================================")
    print("🚀 Starting Telegram Attendance & Time Tracking Bot")
    print("====================================================")
    
    # 1. Verify Bot Token
    if not config.TELEGRAM_BOT_TOKEN or config.TELEGRAM_BOT_TOKEN == "your_telegram_bot_token_here":
        logger.error("❌ Error: TELEGRAM_BOT_TOKEN is not set in environment variables or .env file.")
        print("\nPlease:")
        print("  1. Create a '.env' file based on '.env.example'")
        print("  2. Add your Bot Token from BotFather")
        print("  3. Run the bot again.")
        sys.exit(1)

    # 2. Database Initialization
    print(f"📦 Initializing Database at: {config.DB_PATH}...")
    db = SQLiteDatabase(config.DB_PATH)
    try:
        db.connect()
        # Execute schema SQL file
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        db.execute_schema(schema_path)
        print("✅ Database tables and indexes created successfully.")
    except Exception as e:
        logger.critical(f"❌ Failed to initialize database: {e}")
        sys.exit(1)

    # 3. Google Sheets Integration Initialization
    print("📊 Connecting to Google Sheets API...")
    sheets_sync = GoogleSheetsSyncManager()
    sheets_connected = sheets_sync.authenticate()
    if sheets_connected:
        print("✅ Google Sheets synchronization is ACTIVE and running in real time.")
    else:
        print("⚠️ Google Sheets sync is DISABLED. Run offline using SQLite only.")

    # 4. Telegram Application Builder
    print("🤖 Building Telegram Bot instance...")
    try:
        application = (
            ApplicationBuilder()
            .token(config.TELEGRAM_BOT_TOKEN)
            .connect_timeout(30.0)
            .read_timeout(30.0)
            .write_timeout(30.0)
            .build()
        )
    except Exception as e:
        logger.critical(f"❌ Failed to instantiate Telegram Bot: {e}")
        db.close()
        sys.exit(1)

    # 5. Handler Manager Setup
    manager = BotHandlerManager(db, sheets_sync)

    # Share database with bot_data so ConversationHandler can access it
    application.bot_data["db"] = db

    # Register bot event routes
    # IMPORTANT: ConversationHandler must be registered BEFORE the generic
    # MessageHandler so it intercepts the "Permission Request 📋" button first.
    application.add_handler(build_permission_conversation_handler())
    application.add_handler(CommandHandler("start", manager.start_command))
    application.add_handler(CommandHandler("report", manager.report_command))
    application.add_handler(CommandHandler("request", manager.request_command))
    # Admin approval callbacks (pr_approve_N / pr_reject_N)
    application.add_handler(
        CallbackQueryHandler(handle_approval_callback, pattern=r"^pr_(approve|reject)_\d+$")
    )
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manager.handle_message))

    print("\n----------------------------------------------------")
    print(f"🤖 Bot is polling for messages. Press Ctrl+C to terminate.")
    print("----------------------------------------------------\n")
    
    try:
        application.run_polling()
    except KeyboardInterrupt:
        print("\n👋 Stopping Bot...")
    finally:
        db.close()
        print("🔒 Database connection closed. Offline.")

if __name__ == '__main__':
    main()
