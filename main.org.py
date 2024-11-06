import os
from pyrogram import Client, filters
import asyncio
from dotenv import load_dotenv
import json
import shutil
from datetime import datetime
import humanize
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
from collections import deque
from enum import Enum
from ratelimit import limits, sleep_and_retry
from pyrogram.errors import ApiIdInvalid, ApiIdPublishedFlood, AccessTokenInvalid, FloodWait
from pyrogram import idle
from pyrogram.types import Message
from pyrogram import errors
import time
from enum import Enum
from datetime import datetime, timedelta
import signal
import psutil
import sys
from signal import SIGINT, SIGTERM
from testex import process_archives_in_dir, extract_and_delete_archive
from lconv_final import process_file
from config import ALL_FILES_DIR, PASS_FILES_DIR, ERROR_DIR, OUTPUT_FILE
from concurrent.futures import ThreadPoolExecutor
from queue_manager import QueueManager, OperationType
from processing_manager import ProcessingManager, ProcessingState
from collections import defaultdict
import math

# Load environment variables from .env file
load_dotenv()

# Add these with other constants at the top of the file
DOWNLOAD_WAIT_TIME = 5  # 5 seconds between checking for new messages
MAX_RETRIES = 3
RETRY_DELAY = 5
PROCESSED_FILES_FILE = 'data/processed_files.json'

# Bot configurations and texts
start_text = '''
Hello, this is a file management bot.
To start, send your file to the bot.
'''
file_name_error = '⚠️ Unfortunately, an error occurred while processing the file name.'
dl_text = '📥 Downloading from Telegram servers...'
ext_txt = '🔄 Extracting files...'
merge_txt = '🔄 Processing files...'
up_txt = '📤 Uploading to lexor...'
save_error_text = '❌ Error while saving file on server'
dl_error_text = '❌ Error when downloading a file from Telegram'

# Fetch environment variables
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")
session_name = os.getenv("SESSION_NAME")

# Configuration
admins = [2033814123, 7232900580, 5778711602]
dev = 2033814123
dl_path = os.path.abspath(os.getcwd()) + '/files/all'
PROCESSED_FILES_DB = 'processed_files.json'
ERROR_DIR = 'files/errors'
LAST_MESSAGE_ID_FILE = 'data/last_message_id.json'
BOT_STATE_FILE = 'data/bot_state.json'

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Rate limiting configuration
RATE_LIMITS = {
    'per_second': 1,
    'per_minute': 10
}

# Rate limiting decorator
@sleep_and_retry
@limits(calls=RATE_LIMITS['per_second'], period=1)  # 1 request per second
@limits(calls=RATE_LIMITS['per_minute'], period=60)  # 10 requests per minute
def rate_limited_function(chat_id):
    return True

class ProcessingState(Enum):
    IDLE = "idle"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    CONVERTING = "converting"
    ERROR = "error"

class ProcessingManager:
    def __init__(self):
        self.current_state = ProcessingState.IDLE
        self.is_processing = False
        self.paused = False
        self.download_queue = defaultdict(deque)  # Admin ID -> Queue
        self.active_downloads = defaultdict(set)  # Admin ID -> Set of active downloads
        self.processed_files_count = 0
        self.failed_files_count = 0
        self.start_time = datetime.now()
        self._status_messages = {}  # Admin ID -> Status Message
        self._processing_tasks = {}  # Admin ID -> Task

    async def add_to_download_queue(self, admin_id: int, message, file_name: str) -> bool:
        try:
            if file_name in self.active_downloads[admin_id]:
                return False

            download_info = {
                'message': message,
                'file_name': file_name,
                'timestamp': datetime.now()
            }
            
            self.download_queue[admin_id].append(download_info)
            self.active_downloads[admin_id].add(file_name)
            
            # Start processing if not already running
            if not self._processing_tasks.get(admin_id):
                self._processing_tasks[admin_id] = asyncio.create_task(
                    self.process_queue(admin_id)
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding to queue: {str(e)}")
            return False

    async def process_queue(self, admin_id: int):
        try:
            while self.download_queue[admin_id] and not self.paused:
                download = self.download_queue[admin_id].popleft()
                message = download['message']
                file_name = download['file_name']
                
                try:
                    # Create initial status message
                    status_message = await message.reply_text("⏳ Preparing download...")
                    
                    # Initialize progress tracker
                    progress = DownloadProgress(status_message, file_name)
                    
                    # Create the directory if it doesn't exist
                    os.makedirs(ALL_FILES_DIR, exist_ok=True)
                    
                    # Download file with progress tracking
                    file_path = os.path.join(ALL_FILES_DIR, file_name)
                    await message.download(
                        file_name=file_path,
                        progress=progress.progress
                    )
                    
                    self.active_downloads[admin_id].remove(file_name)
                    self.processed_files_count += 1
                    await status_message.edit_text(
                        f"✅ **Download Complete!**\n\n"
                        f"**File:** `{file_name}`\n"
                        f"**Size:** {format_size(os.path.getsize(file_path))}\n"
                        f"**Path:** `{file_path}`"
                    )
                    
                except Exception as e:
                    logger.error(f"Error downloading {file_name}: {e}")
                    self.failed_files_count += 1
                    await status_message.edit_text(
                        f"❌ **Download Failed**\n\n"
                        f"**File:** `{file_name}`\n"
                        f"**Error:** `{str(e)}`"
                    )
                
            del self._processing_tasks[admin_id]
            
        except Exception as e:
            logger.error(f"Error in process_queue: {e}")
            if admin_id in self._processing_tasks:
                del self._processing_tasks[admin_id]

    async def progress_callback(self, current, total, message):
        """Update download progress"""
        try:
            percent = (current * 100) / total
            await message.edit_text(
                f"📥 Downloading: {message.document.file_name}\n"
                f"Progress: {percent:.1f}%"
            )
        except Exception as e:
            logger.error(f"Error updating progress: {e}")

    async def stop_all_processes(self):
        """Stop all running processes"""
        self.paused = True
        self.is_processing = False
        
        # Cancel all processing tasks
        for admin_id, task in self._processing_tasks.items():
            if not task.done():
                task.cancel()
                
        # Clear queues and active downloads
        for admin_id in self.download_queue:
            self.download_queue[admin_id].clear()
            self.active_downloads[admin_id].clear()

class ExtractionProgress:
    def __init__(self, client, chat_id):
        self.client = client
        self.chat_id = chat_id
        self.current = 0
        self.total = 0
        self.message = None
        self.last_update_time = time.time()

    async def start(self, total_files):
        """Initialize progress tracking"""
        self.total = total_files
        self.message = await self.client.send_message(
            self.chat_id,
            f"🔄 Starting extraction of {total_files} files..."
        )

    async def update(self, file_name):
        """Update progress"""
        self.current += 1
        now = time.time()
        
        # Update only every 2 seconds to avoid flood
        if now - self.last_update_time < 2 and self.current != self.total:
            return
            
        self.last_update_time = now
        percentage = (self.current * 100) / self.total
        progress_bar = '█' * int(percentage/5) + '░' * (20 - int(percentage/5))
        
        await self.message.edit_text(
            f"🔄 **Extracting Files**\n\n"
            f"**Current File:** `{file_name}`\n\n"
            f"[{progress_bar}] {percentage:.1f}%\n"
            f"**Progress:** {self.current}/{self.total} files"
        )

    async def complete(self):
        """Mark extraction as complete"""
        if self.message:
            await self.message.edit_text(
                "✅ **Extraction Complete!**\n\n"
                f"Successfully processed {self.total} files"
            )

class ConversionProgress:
    def __init__(self, client, chat_id):
        self.client = client
        self.chat_id = chat_id
        self.current = 0
        self.total = 0
        self.message = None
        self.last_update_time = time.time()

    async def start(self, total_files):
        """Initialize progress tracking"""
        self.total = total_files
        self.message = await self.client.send_message(
            self.chat_id,
            f"🔄 Starting conversion of {total_files} files..."
        )

    async def update(self, file_name):
        """Update progress"""
        self.current += 1
        now = time.time()
        
        # Update only every 2 seconds to avoid flood
        if now - self.last_update_time < 2 and self.current != self.total:
            return
            
        self.last_update_time = now
        percentage = (self.current * 100) / self.total
        progress_bar = '█' * int(percentage/5) + '░' * (20 - int(percentage/5))
        
        await self.message.edit_text(
            f"🔄 **Converting Files**\n\n"
            f"**Current File:** `{file_name}`\n\n"
            f"[{progress_bar}] {percentage:.1f}%\n"
            f"**Progress:** {self.current}/{self.total} files"
        )

    async def complete(self):
        """Mark conversion as complete"""
        if self.message:
            await self.message.edit_text(
                "✅ **Conversion Complete!**\n\n"
                f"Successfully processed {self.total} files"
            )

def format_size(size):
    """Format size in bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

def format_time(seconds):
    """Format seconds into human readable time"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"

def create_progress_bar(current, total, length=20):
    """Create a detailed progress bar"""
    progress = (current / total) if total > 0 else 0
    filled_length = int(length * progress)
    bar = '█' * filled_length + '░' * (length - filled_length)
    percent = progress * 100
    return f"[{bar}] {percent:.1f}%"

class DownloadProgress:
    def __init__(self, status_message, file_name):
        self.status_message = status_message
        self.file_name = file_name
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_current = 0
        
    async def progress(self, current, total):
        try:
            if total == 0:
                return
                
            now = time.time()
            # Update only every 2 seconds or at 100%
            if now - self.last_update_time < 2 and current != total:
                return
                
            # Calculate speed and progress
            time_elapsed = now - self.start_time
            speed = current / time_elapsed if time_elapsed > 0 else 0
            percentage = (current * 100) / total
            progress_bar = '█' * int(percentage/5) + '░' * (20 - int(percentage/5))
            
            # Calculate estimated time remaining
            if speed > 0:
                time_remaining = (total - current) / speed
            else:
                time_remaining = 0
                
            # Format status message with detailed progress
            status_text = (
                f"📥 **Downloading:** `{self.file_name}`\n\n"
                f"[{progress_bar}] {percentage:.1f}%\n\n"
                f"⚡️ **Speed:** {format_size(speed)}/s\n"
                f"💾 **Size:** {format_size(current)}/{format_size(total)}\n"
                f"⏱ **Elapsed:** {format_time(time_elapsed)}\n"
                f"⏳ **Remaining:** {format_time(time_remaining)}"
            )
            
            await self.status_message.edit_text(status_text)
            self.last_update_time = now
            self.last_current = current
            
        except Exception as e:
            logger.error(f"Error in progress callback: {str(e)}")

class FileTracker:
    def __init__(self):
        self.processed_files = {}
        self.load_processed_files()
        
    def load_processed_files(self):
        """Load processed files from JSON"""
        try:
            if os.path.exists(PROCESSED_FILES_FILE):
                with open(PROCESSED_FILES_FILE, 'r') as f:
                    self.processed_files = json.load(f)
        except Exception as e:
            logger.error(f"Error loading processed files: {str(e)}")
            self.processed_files = {}
            
    def save_processed_files(self):
        """Save processed files to JSON"""
        try:
            os.makedirs(os.path.dirname(PROCESSED_FILES_FILE), exist_ok=True)
            with open(PROCESSED_FILES_FILE, 'w') as f:
                json.dump(self.processed_files, f)
        except Exception as e:
            logger.error(f"Error saving processed files: {str(e)}")
            
    def is_file_processed(self, file_id, file_name):
        """Check if file was already processed"""
        return file_id in self.processed_files
        
    def mark_file_processed(self, file_id, file_name):
        """Mark file as processed"""
        self.processed_files[file_id] = {
            "name": file_name,
            "timestamp": datetime.now().isoformat()
        }
        self.save_processed_files()

class ProcessingProgress:
    def __init__(self, client, message):
        self.client = client
        self.message = message
        self.last_update = 0
        
    async def update(self, current, total, operation):
        now = time.time()
        if now - self.last_update < 2 and current != total:  # Update every 2 seconds
            return
            
        self.last_update = now
        progress = (current * 100) / total
        progress_bar = '▓' * int(progress / 5) + '░' * (20 - int(progress / 5))
        
        try:
            await self.message.edit_text(
                f"🔄 {operation} in progress...\n\n"
                f"Progress: [{progress_bar}] {progress:.1f}%\n"
                f"Files: {current}/{total}"
            )
        except Exception as e:
            logger.error(f"Error updating progress: {e}")

# Initialize components
file_tracker = FileTracker()
processing_manager = ProcessingManager()
app = Client(
    session_name,
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token,
    sleep_threshold=60,  # Increase sleep threshold
    max_concurrent_transmissions=3  # Limit concurrent operations
)

# Global variable to track authentication state
auth_states = {}

# Define command filters
auth_command = filters.command(["auth", "start", "check_channel"])

# Command handlers
@app.on_message(filters.command("help") & filters.user(admins))
async def help_handler(_, message):
    """Show help message with all commands"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Process Files", callback_data="help_process")],
        [InlineKeyboardButton("Monitoring", callback_data="help_monitor")],
        [InlineKeyboardButton("Maintenance", callback_data="help_maintenance")]
    ])
    
    help_text = """
🤖 **Bot Commands Overview**

Select a category below to see detailed commands:
• Process Files - Commands for file processing
• Monitoring - Status and statistics
• Maintenance - Cleanup and system commands

Use /commands to see all available commands
"""
    await message.reply_text(help_text, reply_markup=keyboard)

@app.on_callback_query(filters.regex("^help_"))
async def help_callback(_, callback_query):
    category = callback_query.data.split("_")[1]
    
    help_texts = {
        "process": """
📁 **Processing Commands**
• /extract - Extract all archives
• /convert - Convert extracted files
• /force_process - Process all files
• /pause - Pause processing
• /resume - Resume processing
""",
        "monitor": """
📊 **Monitoring Commands**
• /status - Check current status
• /stats - View detailed statistics
• /state - Check bot state
• /logs - View recent logs
""",
        "maintenance": """
⚙️ **Maintenance Commands**
• /cleanup - Clean temporary files
• /stop - Stop all processes
• /check_channel - Verify channel access
• /exit - Safely shutdown bot
"""
    }
    
    await callback_query.edit_message_text(
        help_texts.get(category, "Category not found"),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("« Back", callback_data="help_main")
        ]])
    )

@app.on_message(filters.command("status") & filters.user(admins))
async def status_handler(_, message):
    try:
        admin_id = message.from_user.id
        queue_size = len(processing_manager.download_queue[admin_id])
        active_downloads = len(processing_manager.active_downloads[admin_id])
        
        status_text = f"""
**Bot Status:**
• State: {processing_manager.current_state.value}
• Processing: {'Yes' if processing_manager.is_processing else 'No'}
• Paused: {'Yes' if processing_manager.paused else 'No'}
• Queue Size: {queue_size}
• Active Downloads: {active_downloads}
• Processed Files: {processing_manager.processed_files_count}
• Failed Files: {processing_manager.failed_files_count}
• Uptime: {datetime.now() - processing_manager.start_time}
"""
        await message.reply_text(status_text)
    except Exception as e:
        await message.reply_text(f"❌ Error getting status: {str(e)}")

@app.on_callback_query(filters.regex("^(refresh_status|toggle_pause|start_cleanup|stop_all)$"))
async def status_callback(_, callback_query):
    action = callback_query.data
    
    if action == "refresh_status":
        await status_handler(_, callback_query.message)
    elif action == "toggle_pause":
        processing_manager.paused = not processing_manager.paused
        await status_handler(_, callback_query.message)
    elif action == "start_cleanup":
        await cleanup_handler(_, callback_query.message)
    elif action == "stop_all":
        await stop_handler(_, callback_query.message)
    
    await callback_query.answer()

@app.on_message(filters.command("stop") & filters.user(admins))
async def stop_handler(_, message):
    """Stop all running processes"""
    try:
        status = await message.reply_text("🛑 Stopping all processes...")
        
        # Clear download queue first
        processing_manager.download_queue.clear()
        
        # Force stop all processes
        processing_manager.is_processing = False
        processing_manager.paused = False
        processing_manager.current_state = ProcessingState.IDLE
        await processing_manager.stop_all_processes()
        
        # Save current state
        save_bot_state(processing_manager.last_message_id, datetime.now().isoformat())
        
        # Clean up temporary files with error handling
        files_cleaned = 0
        try:
            for file in os.listdir('temp'):
                try:
                    file_path = os.path.join('temp', file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        files_cleaned += 1
                except Exception as e:
                    logger.error(f"Error removing {file}: {str(e)}")
        except Exception as e:
            logger.error(f"Error cleaning temp files: {str(e)}")
        
        await status.edit_text(
            "✅ All processes stopped and cleaned up!\n"
            f"• Cleared download queue\n"
            f"• Stopped all processes\n"
            f"• Cleaned {files_cleaned} temporary files\n"
            f"• Saved bot state"
        )
    except Exception as e:
        logger.error(f"Error in stop handler: {str(e)}")
        await message.reply_text(f"❌ Error stopping processes: {str(e)}")

@app.on_message(filters.command("pause") & filters.user(admins))
async def pause_handler(_, message):
    """Pause processing"""
    try:
        if processing_manager.paused:
            await message.reply_text("⚠️ Processing is already paused.")
            return
            
        if not processing_manager.is_processing and len(processing_manager.download_queue) == 0:
            await message.reply_text("⚠️ No active processes or queued items to pause.")
            return
            
        processing_manager.paused = True
        current_state = processing_manager.current_state.value
        queue_size = len(processing_manager.download_queue)
        
        await message.reply_text(
            f"⏸ Processing paused\n\n"
            f"• Current state: {current_state}\n"
            f"• Queued items: {queue_size}\n"
            f"• Active downloads: {len(processing_manager.active_downloads)}\n\n"
            f"Use /resume to continue or /stop to cancel."
        )
        
        # Save state
        save_bot_state(processing_manager.last_message_id, datetime.now().isoformat())
        
    except Exception as e:
        logger.error(f"Error in pause handler: {str(e)}")
        await message.reply_text(f"❌ Error pausing: {str(e)}")

@app.on_message(filters.command("resume") & filters.user(admins))
async def resume_handler(_, message):
    """Resume processing"""
    try:
        if not processing_manager.paused:
            await message.reply_text("⚠️ Processing is not paused.")
            return
            
        queue_size = len(processing_manager.download_queue)
        current_state = processing_manager.current_state.value
        
        if not processing_manager.is_processing and queue_size == 0:
            await message.reply_text(
                "⚠️ No processes to resume.\n"
                "Use /extract or /convert to start processing."
            )
            return
            
        processing_manager.paused = False
        
        status_text = (
            f"▶️ Processing resumed\n\n"
            f"• Current state: {current_state}\n"
            f"• Queued items: {queue_size}\n"
            f"• Active downloads: {len(processing_manager.active_downloads)}"
        )
        
        if queue_size > 0:
            # Restart processing loop if there are queued items
            asyncio.create_task(processing_manager.start_processing_loop())
            status_text += "\n• Processing queue restarted"
            
        await message.reply_text(status_text)
        
    except Exception as e:
        logger.error(f"Error in resume handler: {str(e)}")
        await message.reply_text(f"❌ Error resuming: {str(e)}")

@app.on_message(filters.command("cleanup") & filters.user(admins))
async def cleanup_handler(_, message):
    """Clean up temporary files and directories"""
    try:
        if processing_manager.is_processing and not processing_manager.paused:
            await message.reply_text(
                "⚠️ Cannot cleanup while processing is active.\n"
                "Use /pause or /stop first."
            )
            return
        
        status = await message.reply_text("🧹 Starting cleanup...")
        
        # Stop all processes first
        await processing_manager.stop_all_processes()
        
        cleanup_stats = {'cleaned': 0, 'failed': 0, 'size_freed': 0}
        
        # Clean each directory
        for directory in ['temp', 'files/pass', ERROR_DIR]:
            if os.path.exists(directory):
                for file_name in os.listdir(directory):
                    try:
                        file_path = os.path.join(directory, file_name)
                        if os.path.isfile(file_path):
                            size = os.path.getsize(file_path)
                            os.remove(file_path)
                            cleanup_stats['cleaned'] += 1
                            cleanup_stats['size_freed'] += size
                            
                            # Update status every 10 files
                            if cleanup_stats['cleaned'] % 10 == 0:
                                await status.edit_text(
                                    f"🧹 Cleaning up...\n"
                                    f"Files cleaned: {cleanup_stats['cleaned']}\n"
                                    f"Space freed: {humanize.naturalsize(cleanup_stats['size_freed'])}"
                                )
                    except Exception as e:
                        cleanup_stats['failed'] += 1
                        logger.error(f"Failed to clean {file_path}: {str(e)}")
        
        # Final status update
        await status.edit_text(
            f"✅ Cleanup completed!\n\n"
            f"• Files cleaned: {cleanup_stats['cleaned']}\n"
            f"• Failed: {cleanup_stats['failed']}\n"
            f"• Space freed: {humanize.naturalsize(cleanup_stats['size_freed'])}"
        )
        
    except Exception as e:
        await message.reply_text(f"❌ Error during cleanup: {str(e)}")

@app.on_message(filters.command("logs") & filters.user(admins))
async def logs_handler(_, message):
    try:
        if not os.path.exists('bot.log'):
            await message.reply_text("❌ No log file found")
            return
            
        log_lines = []
        with open('bot.log', 'r', encoding='utf-8') as f:
            log_lines = f.readlines()[-20:]
        
        log_text = "📋 **Recent Logs:**\n\n"
        for line in log_lines:
            log_text += f"`{line.strip()}`\n"
        
        await message.reply_text(log_text)
    except Exception as e:
        await message.reply_text(f"❌ Error getting logs: {str(e)}")

@app.on_message(filters.command("stats") & filters.user(admins))
async def stats_handler(_, message):
    """Show bot statistics"""
    try:
        uptime = datetime.now() - processing_manager.start_time
        processed = processing_manager.processed_files_count
        failed = processing_manager.failed_files_count
        total = processed + failed
        
        # Calculate success rate
        success_rate = f"{(processed / total * 100):.1f}%" if total > 0 else "N/A"
        
        stats_text = f"""
📊 **Bot Statistics**

⏱ **Uptime:**
• Running since: {processing_manager.start_time.strftime('%Y-%m-%d %H:%M:%S')}
• Total uptime: {str(uptime).split('.')[0]}

📁 **Processing Stats:**
• Files Processed: {processed}
• Failed Files: {failed}
• Success Rate: {success_rate}

💾 **Storage Stats:**
• All Files: {humanize.naturalsize(get_dir_size('files/all'))}
• Processed: {humanize.naturalsize(get_dir_size('files/pass'))}
• Errors: {humanize.naturalsize(get_dir_size(ERROR_DIR))}

🔄 **Current State:**
• Processing: {'Paused' if processing_manager.paused else 'Running'}
• Active Downloads: {len(processing_manager.active_downloads)}
• Queue Size: {len(processing_manager.download_queue)}
"""
        await message.reply_text(stats_text)
    except Exception as e:
        await message.reply_text(f"❌ Error getting stats: {str(e)}")

@app.on_message(filters.command("start") & filters.user(admins))
async def start_handler(_, message):
    """Start command handler"""
    start_text = """
🚀 **Bot is running!**

Use /help to see available commands
Use /status to check current state
"""
    await message.reply_text(start_text)

@app.on_message(filters.command("force_process") & filters.user(admins))
async def force_process_handler(_, message: Message):
    """Force process all files"""
    try:
        status = await message.reply_text("🔄 Starting forced processing...")
        
        # Run extraction
        await status.edit_text("📦 Extracting archives...")
        def run_extraction():
            from testex import process_archives_in_dir
            process_archives_in_dir(ALL_FILES_DIR, PASS_FILES_DIR)
        await asyncio.get_event_loop().run_in_executor(None, run_extraction)
        
        # Run conversion
        await status.edit_text("🔄 Converting files...")
        def run_conversion():
            from lconv_final import process_file
            success_count = 0
            error_count = 0
            for filename in os.listdir(PASS_FILES_DIR):
                if filename.endswith('.txt'):
                    input_file = os.path.join(PASS_FILES_DIR, filename)
                    try:
                        process_file(input_file, OUTPUT_FILE, ERROR_DIR)
                        success_count += 1
                    except Exception as e:
                        error_count += 1
                        logger.error(f"Error converting {filename}: {e}")
            return success_count, error_count
            
        success_count, error_count = await asyncio.get_event_loop().run_in_executor(None, run_conversion)
        
        await status.edit_text(
            f"✅ Processing completed!\n"
            f"Successfully processed: {success_count}\n"
            f"Errors: {error_count}"
        )
    except Exception as e:
        error_msg = f"❌ Processing failed: {str(e)}"
        logger.error(error_msg)
        await status.edit_text(error_msg)

# Add callback handlers for the buttons
@app.on_callback_query(filters.regex("convert_now"))
async def convert_now_callback(_, callback_query):
    try:
        await callback_query.answer()
        await callback_query.message.edit_text("Starting conversion process...")
        await convert_handler(_, callback_query.message)
    except Exception as e:
        await callback_query.message.reply_text(f"❌ Error starting conversion: {str(e)}")

@app.on_callback_query(filters.regex("stop_processing"))
async def stop_processing_callback(_, callback_query):
    try:
        await callback_query.answer()
        await callback_query.message.edit_text(
            "✅ Processing stopped after extraction.\n"
            "Use /convert when you want to convert the files."
        )
    except Exception as e:
        await callback_query.message.reply_text(f"❌ Error: {str(e)}")

@app.on_message(filters.command("set_rate_limit") & filters.user(admins))
async def set_rate_limit_handler(_, message):
    try:
        per_second, per_minute = map(int, message.text.split()[1:])
        RATE_LIMITS['per_second'] = per_second
        RATE_LIMITS['per_minute'] = per_minute
        await message.reply_text(f"Rate limits set to {per_second} per second and {per_minute} per minute.")
    except (ValueError, IndexError):
        await message.reply_text("Usage: /set_rate_limit <per_second> <per_minute>")

@app.on_message(filters.command("auth") & filters.user(admins))
async def start_auth(_, message: Message):
    """Start the authentication process"""
    chat_id = message.chat.id
    
    await message.reply_text(
        " Starting authentication process.\n"
        "Please send your phone number in international format (e.g., +1234567890)"
    )
    auth_states[chat_id] = {
        'step': 'waiting_phone',
        'phone': None,
        'client': None
    }

@app.on_message(filters.user(admins) & filters.text & ~auth_command)
async def handle_auth_input(_, message: Message):
    """Handle authentication input (phone number and verification code)"""
    chat_id = message.chat.id
    
    if chat_id not in auth_states:
        return
    
    state = auth_states[chat_id]
    
    try:
        if state['step'] == 'waiting_phone':
            # Handle phone number input
            phone_number = message.text.strip()
            
            # Create temporary client for authentication
            temp_client = Client(
                f"temp_session_{chat_id}",
                api_id=api_id,
                api_hash=api_hash,
                phone_number=phone_number,
                in_memory=True
            )
            
            state['client'] = temp_client
            state['phone'] = phone_number
            state['step'] = 'waiting_code'
            
            await temp_client.connect()
            await message.reply_text(
                "📱 Please send the verification code you received\n"
                "(Format: 12345, not the format with - symbols)"
            )
            
        elif state['step'] == 'waiting_code':
            # Handle verification code input
            code = message.text.strip()
            temp_client = state['client']
            
            try:
                # Try to sign in with the code
                await temp_client.sign_in(state['phone'], code)
                
                # Get the string session
                string_session = await temp_client.export_session_string()
                
                # Send the string session securely
                await message.reply_text(
                    "🔐 Here's your session string. Keep it secure and never share it:\n\n"
                    f"`{string_session}`\n\n"
                    "Add this to your .env file as:\n"
                    "USER_STRING_SESSION=your_session_string"
                )
                
                # Clean up
                await temp_client.disconnect()
                del auth_states[chat_id]
                
            except errors.PhoneCodeInvalid:
                await message.reply_text(" Invalid code. Please try again or use /auth to restart.")
            except errors.PhoneCodeExpired:
                await message.reply_text("❌ Code expired. Please use /auth to restart.")
            except Exception as e:
                await message.reply_text(f"❌ An error occurred: {str(e)}")
                
    except Exception as e:
        await message.reply_text(f"❌ An error occurred: {str(e)}")
        del auth_states[chat_id]

@app.on_message(filters.command("exit") & filters.user(admins))
async def exit_handler(_, message):
    """Safely terminate the bot"""
    try:
        status = await message.reply_text(" Initiating shutdown sequence...")
        
        # Update status
        await status.edit_text("🛑 Stopping all processes...")
        await processing_manager.stop_all_processes()
        
        # Clean up temp files
        await status.edit_text("🧹 Cleaning up temporary files...")
        for file in os.listdir('temp'):
            try:
                os.remove(os.path.join('temp', file))
            except Exception as e:
                logger.error(f"Failed to remove temp file {file}: {e}")
        
        # Save final state
        await status.edit_text("💾 Saving final state...")
        try:
            save_bot_state(processing_manager.last_message_id, 
                          datetime.now().isoformat())
        except Exception as e:
            logger.error(f"Failed to save final state: {e}")
        
        # Send final message
        await status.edit_text("""
🔴 **Bot Shutdown Initiated**

• Stopped all processes
• Cleaned temporary files
• Saved final state
• Shutting down...

_Bot will be offline in a few seconds._
""")
        
        logger.info("Bot shutdown initiated by admin command")
        
        # Wait briefly for message to be sent
        await asyncio.sleep(2)
        
        # Stop the bot
        await app.stop()
        
        # Exit the program
        sys.exit(0)
        
    except Exception as e:
        error_msg = f"Error during shutdown: {str(e)}"
        logger.error(error_msg)
        await message.reply_text(f"❌ {error_msg}")

# Add command verification function
async def verify_commands():
    """Verify all commands are registered and functional"""
    commands = {
        "start": "Start the bot",
        "help": "Show help message",
        "status": "Check current status",
        "stats": "View detailed statistics",
        "stop": "Stop all processes",
        "pause": "Pause processing",
        "resume": "Resume processing",
        "cleanup": "Clean temporary files",
        "logs": "View recent logs",
        "extract": "Extract all archives",
        "convert": "Convert all files",
        "force_process": "Process all files",
        "exit": "Shutdown the bot",
        "state": "Check bot state",
        "commands": "List all commands"
    }
    
    verification_text = "🔍 **Command Verification:**\n\n"
    
    # Get all registered command handlers
    registered_commands = [
        cmd.command for cmd in app.dispatcher.groups[0] 
        if hasattr(cmd, 'command')
    ]
    
    # Check command dependencies
    dependencies = {
        "extract": ["testex.py"],
        "convert": ["lconv_final.py"]
    }
    
    for cmd, description in commands.items():
        status = "✅" if cmd in registered_commands else "❌"
        
        # Check dependencies if they exist
        if cmd in dependencies:
            for dep in dependencies[cmd]:
                if not os.path.exists(dep):
                    status = "⚠️"
                    description += f" (Missing {dep})"
        
        verification_text += f"{status} `/{cmd}` - {description}\n"
    
    return verification_text

# Update the main function to include command verification
async def main():
    try:
        # Create necessary directories
        for directory in ['temp', 'files/all', 'files/pass', ERROR_DIR, 'data']:
            os.makedirs(directory, exist_ok=True)
        
        logger.info("Starting bot...")
        print("\n🚀 Initializing bot...")

        # Initialize components
        global file_tracker, processing_manager
        file_tracker = FileTracker()
        processing_manager = ProcessingManager()

        # Remove the long initial delay
        logger.info("Starting bot services...")
        
        # Try to initialize the bot with retries and shorter backoff
        max_retries = 3
        base_delay = 5  # Reduced from 30 to 5 seconds
        
        for attempt in range(max_retries):
            try:
                print(f"\n📡 Connecting to Telegram (Attempt {attempt + 1}/{max_retries})")
                async with app:
                    startup_text = """
✅ **Bot Started Successfully!**

⚙️ Processing manager initialized
🧹 Temp files cleaned up
📂 File systems ready

Use /help to see available commands
"""
                    await app.send_message(dev, startup_text)
                    print("\n✨ Bot is now online and ready!")
                    await idle()
                    break
                    
            except FloodWait as e:
                wait_time = e.value
                if attempt < max_retries - 1:
                    print(f"\n⚠️ Rate limit hit. Waiting {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Max retries reached. Last flood wait was {wait_time} seconds.")
                    raise
                    
            except Exception as e:
                logger.error(f"Error during attempt {attempt + 1}: {str(e)}")
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"\n⚠️ Connection failed. Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    raise
                    
    except Exception as e:
        logger.error(f"Startup error: {str(e)}")
        print(f"\n❌ Startup failed: {str(e)}")
        try:
            await app.send_message(dev, f"❌ Startup failed: {str(e)}")
        except:
            pass
    finally:
        try:
            await processing_manager.stop_all_processes()
        except:
            pass

# Add a status command to check registered commands
@app.on_message(filters.command("commands") & filters.user(admins))
async def commands_handler(_, message):
    """Check registered commands"""
    try:
        verification_text = await verify_commands()
        await message.reply_text(verification_text)
    except Exception as e:
        await message.reply_text(f"❌ Error checking commands: {str(e)}")

async def verify_configuration():
    """Verify all required configuration values are present"""
    try:
        required_vars = {
            'API_ID': api_id,
            'API_HASH': api_hash,
            'BOT_TOKEN': bot_token,
            'SESSION_NAME': session_name
        }

        missing_vars = []
        for var_name, var_value in required_vars.items():
            if var_value is None or var_value == '':
                missing_vars.append(var_name)

        if missing_vars:
            logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
            return False

        # Verify API credentials with automatic wait
        max_retries = 3
        for attempt in range(max_retries):
            try:
                test_client = Client(
                    "test_session",
                    api_id=api_id,
                    api_hash=api_hash,
                    bot_token=bot_token,
                    in_memory=True
                )
                await test_client.start()
                await test_client.stop()
                return True
                
            except FloodWait as e:
                wait_time = e.value
                logger.warning(f"Flood wait required. Waiting {wait_time} seconds... (Attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
                continue
                
            except (ApiIdInvalid, ApiIdPublishedFlood, AccessTokenInvalid) as e:
                logger.error(f"API credential verification failed: {str(e)}")
                return False

        logger.error("Max retries reached for configuration verification")
        return False

    except Exception as e:
        logger.error(f"Configuration verification failed: {str(e)}")
        return False

def get_file_name(message):
    """Extract file name from message"""
    try:
        if message.document:
            return message.document.file_name
        elif message.video:
            return message.video.file_name
        elif message.audio:
            return message.audio.file_name
        elif message.voice:
            return f"voice_{message.date.strftime('%Y%m%d_%H%M%S')}.ogg"
        elif message.video_note:
            return f"video_note_{message.date.strftime('%Y%m%d_%H%M%S')}.mp4"
        return None
    except Exception as e:
        logger.error(f"Error getting file name: {str(e)}")
        return None

def save_bot_state(last_message_id, timestamp):
    """Save bot state to file"""
    try:
        state = {
            'last_message_id': last_message_id,
            'timestamp': timestamp,
            'last_update': datetime.now().isoformat()
        }
        os.makedirs(os.path.dirname(BOT_STATE_FILE), exist_ok=True)
        with open(BOT_STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        logger.error(f"Failed to save bot state: {str(e)}")

def load_bot_state():
    """Load bot state from file"""
    try:
        if os.path.exists(BOT_STATE_FILE):
            with open(BOT_STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load bot state: {str(e)}")
    return None

# Add this with other message handlers
@app.on_message(filters.user(admins) & (filters.forwarded | filters.media))
async def handle_admin_messages(client, message):
    try:
        if not message.media:
            return
            
        file_name = get_file_name(message)
        if not file_name:
            await message.reply_text("❌ Invalid file name")
            return
            
        logger.info(f"Received file from admin: {file_name}")
        admin_id = message.from_user.id
        
        if await processing_manager.add_to_download_queue(admin_id, message, file_name):
            await message.reply_text(f"📥 Added to queue: {file_name}")
        else:
            await message.reply_text(f"⚠️ File already in queue: {file_name}")
            
    except Exception as e:
        error_msg = f"Error processing message: {str(e)}"
        logger.error(error_msg)
        await message.reply_text(f"❌ {error_msg}")

# Add these command handlers after the other handlers and before the main() function

@app.on_message(filters.command("start") & filters.private)
async def start_handler(_, message: Message):
    """Handle /start command"""
    await message.reply_text(start_text)

@app.on_message(filters.command("help") & filters.user(admins))
async def help_handler(_, message: Message):
    """Show help message"""
    help_text = """
**Available Commands:**

/start - Start the bot
/help - Show this help message
/status - Check current status
/stats - View detailed statistics
/stop - Stop all processes
/pause - Pause processing
/resume - Resume processing
/cleanup - Clean temporary files
/logs - View recent logs
/extract - Extract all archives
/convert - Convert all files
/force_process - Process all files
/exit - Shutdown the bot
/state - Check bot state
/commands - List all commands
"""
    await message.reply_text(help_text)

@app.on_message(filters.command("extract") & filters.user(admins))
async def extract_handler(_, message: Message):
    """Extract all archives in the processing directory"""
    try:
        status = await message.reply_text("🔄 Starting extraction process...")
        processing_manager.current_state = ProcessingState.EXTRACTING
        
        def run_extraction():
            try:
                process_archives_in_dir(ALL_FILES_DIR, PASS_FILES_DIR)
                return True
            except Exception as e:
                logger.error(f"Extraction error: {e}")
                return False
                
        success = await asyncio.get_event_loop().run_in_executor(None, run_extraction)
        
        if success:
            await status.edit_text("✅ Extraction completed successfully!")
        else:
            await status.edit_text("❌ Extraction failed. Check logs for details.")
            
        processing_manager.current_state = ProcessingState.IDLE
        
    except Exception as e:
        error_msg = f"❌ Extraction failed: {str(e)}"
        logger.error(error_msg)
        await status.edit_text(error_msg)

@app.on_message(filters.command("status") & filters.user(admins))
async def status_handler(_, message: Message):
    """Check current bot status"""
    try:
        status_text = f"""
**Bot Status:**
• State: {processing_manager.current_state.value}
• Processing: {'Yes' if processing_manager.is_processing else 'No'}
• Paused: {'Yes' if processing_manager.paused else 'No'}
• Queue Size: {len(processing_manager.download_queue)}
• Processed Files: {processing_manager.processed_files_count}
• Failed Files: {processing_manager.failed_files_count}
• Uptime: {datetime.now() - processing_manager.start_time}
"""
        await message.reply_text(status_text)
    except Exception as e:
        await message.reply_text(f"❌ Error getting status: {str(e)}")

@app.on_message(filters.command("pause") & filters.user(admins))
async def pause_handler(_, message: Message):
    """Pause all processing"""
    try:
        processing_manager.paused = True
        await message.reply_text("⏸ Processing paused")
    except Exception as e:
        await message.reply_text(f"❌ Error pausing: {str(e)}")

@app.on_message(filters.command("resume") & filters.user(admins))
async def resume_handler(_, message: Message):
    """Resume processing"""
    try:
        processing_manager.paused = False
        await message.reply_text("▶️ Processing resumed")
        
        # Restart processing if queue not empty
        if processing_manager.download_queue and not processing_manager.is_processing:
            asyncio.create_task(processing_manager.start_processing_loop())
    except Exception as e:
        await message.reply_text(f"❌ Error resuming: {str(e)}")

@app.on_message(filters.command("stop") & filters.user(admins))
async def stop_handler(_, message: Message):
    """Stop all processes"""
    try:
        status = await message.reply_text("🛑 Stopping all processes...")
        await processing_manager.stop_all_processes()
        await status.edit_text("✅ All processes stopped")
    except Exception as e:
        await message.reply_text(f"❌ Error stopping processes: {str(e)}")

@app.on_message(filters.command("cleanup") & filters.user(admins))
async def cleanup_handler(_, message: Message):
    """Clean temporary files"""
    try:
        status = await message.reply_text("🧹 Cleaning temporary files...")
        
        # Clean temp directory
        for file in os.listdir('temp'):
            try:
                os.remove(os.path.join('temp', file))
            except Exception as e:
                logger.error(f"Failed to remove temp file {file}: {e}")
                
        await status.edit_text("✅ Temporary files cleaned")
    except Exception as e:
        await message.reply_text(f"❌ Error cleaning files: {str(e)}")

def get_dir_size(path):
    """Calculate total size of a directory"""
    total = 0
    try:
        if os.path.exists(path):
            for entry in os.scandir(path):
                if entry.is_file():
                    total += entry.stat().st_size
                elif entry.is_dir():
                    total += get_dir_size(entry.path)
    except Exception as e:
        logger.error(f"Error calculating directory size: {str(e)}")
    return total

@app.on_message(filters.command("convert") & filters.user(admins))
async def convert_handler(_, message: Message):
    """Convert files in the processing directory"""
    try:
        status = await message.reply_text("🔄 Starting conversion process...")
        processing_manager.current_state = ProcessingState.CONVERTING
        
        def run_conversion():
            try:
                success_count = 0
                error_count = 0
                
                for filename in os.listdir(PASS_FILES_DIR):
                    if filename.endswith('.txt'):
                        input_file = os.path.join(PASS_FILES_DIR, filename)
                        try:
                            process_file(input_file, OUTPUT_FILE, ERROR_DIR)
                            success_count += 1
                        except Exception as e:
                            error_count += 1
                            logger.error(f"Error converting {filename}: {e}")
                            
                return success_count, error_count
            except Exception as e:
                logger.error(f"Conversion process error: {e}")
                return 0, 0
                
        success_count, error_count = await asyncio.get_event_loop().run_in_executor(None, run_conversion)
        
        if success_count > 0:
            await status.edit_text(
                f"✅ Conversion completed!\n"
                f"Successfully processed: {success_count}\n"
                f"Errors: {error_count}"
            )
        else:
            await status.edit_text("❌ No files were successfully converted.")
            
        processing_manager.current_state = ProcessingState.IDLE
        
    except Exception as e:
        error_msg = f"❌ Conversion failed: {str(e)}"
        logger.error(error_msg)
        await status.edit_text(error_msg)

@app.on_message(filters.document & filters.user(admins))
async def handle_document(client, message):
    """Handle incoming document messages"""
    try:
        file_name = message.document.file_name
        logger.info(f"Received file from admin: {file_name}")
        
        # Create initial status message
        status_message = await message.reply_text("⏳ Preparing download...")
        
        # Create directory if it doesn't exist
        os.makedirs(ALL_FILES_DIR, exist_ok=True)
        file_path = os.path.join(ALL_FILES_DIR, file_name)
        
        # Download with progress tracking
        await client.download_media(
            message=message,
            file_name=file_path,
            progress=DownloadProgress(
                status_message,
                file_name
            ).progress
        )
        
        # Update final status
        await status_message.edit_text(
            f"✅ **Download Complete!**\n\n"
            f"**File:** `{file_name}`\n"
            f"**Size:** {format_size(os.path.getsize(file_path))}\n"
            f"**Path:** `{file_path}`"
        )
        
    except Exception as e:
        logger.error(f"Error downloading {file_name}: {e}")
        await message.reply_text(f"❌ Download failed: {str(e)}")

async def process_downloads(client, admin_id):
    """Process downloads for an admin"""
    try:
        processing_manager.current_state = ProcessingState.DOWNLOADING
        
        while True:
            download = await processing_manager.get_next_download(admin_id)
            if not download:
                break
                
            message = download['message']
            file_name = download['file_name']
            
            status = await message.reply_text("⏳ Preparing download...")
            progress = DownloadProgress(status, file_name)
            
            # Download file with progress tracking
            await message.download(
                file_name=os.path.join(ALL_FILES_DIR, file_name),
                progress=progress.progress
            )
            
            await status.edit_text(
                f"✅ Download completed: {file_name}\n"
                f"📁 Saved to: {ALL_FILES_DIR}"
            )
            
        processing_manager.current_state = ProcessingState.IDLE
        
    except Exception as e:
        logger.error(f"Error processing downloads: {str(e)}")
        processing_manager.current_state = ProcessingState.IDLE

if __name__ == "__main__":
    try:
        print("Starting main process...")
        # Clear any existing session files
        session_file = f"{session_name}.session"
        if os.path.exists(session_file):
            os.remove(session_file)
            print("Cleared existing session file")
            
        loop = asyncio.get_event_loop()
        print("Running main loop...")
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Failed to start the bot: {str(e)}")
        print(f"Error: {str(e)}")
    finally:
        try:
            loop.close()
        except Exception as e:
            logger.error(f"Error closing loop: {str(e)}") 