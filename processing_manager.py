from enum import Enum
from collections import defaultdict
import asyncio
import logging
from typing import Dict, Set, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class ProcessingState(Enum):
    IDLE = "idle"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    CONVERTING = "converting"

class ProcessingManager:
    def __init__(self):
        self.download_queues: Dict[int, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.active_downloads: Dict[int, Set[str]] = defaultdict(set)
        self.current_state = ProcessingState.IDLE
        self.processing_lock = asyncio.Lock()
        self._status_message = None
        
    async def add_to_download_queue(self, admin_id: int, message, file_name: str) -> bool:
        """Add a file to admin's download queue"""
        try:
            if file_name in self.active_downloads[admin_id]:
                logger.warning(f"File {file_name} already in download queue for admin {admin_id}")
                return False
                
            await self.download_queues[admin_id].put({
                'message': message,
                'file_name': file_name,
                'timestamp': datetime.now()
            })
            
            self.active_downloads[admin_id].add(file_name)
            logger.info(f"Added {file_name} to download queue for admin {admin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding to download queue: {str(e)}")
            return False
            
    async def get_next_download(self, admin_id: int) -> Optional[dict]:
        """Get next download from admin's queue"""
        try:
            if self.download_queues[admin_id].empty():
                return None
                
            download = await self.download_queues[admin_id].get()
            self.active_downloads[admin_id].remove(download['file_name'])
            return download
            
        except Exception as e:
            logger.error(f"Error getting next download: {str(e)}")
            return None
            
    async def clear_queue(self, admin_id: int):
        """Clear download queue for an admin"""
        try:
            while not self.download_queues[admin_id].empty():
                await self.download_queues[admin_id].get()
            self.active_downloads[admin_id].clear()
            
        except Exception as e:
            logger.error(f"Error clearing queue: {str(e)}")
            
    def get_queue_size(self, admin_id: int) -> int:
        """Get size of admin's download queue"""
        return self.download_queues[admin_id].qsize()
        
    async def set_status_message(self, message):
        """Set status message for progress updates"""
        self._status_message = message
        
    async def update_status(self, text: str):
        """Update status message"""
        if self._status_message:
            try:
                await self._status_message.edit_text(text)
            except Exception as e:
                logger.error(f"Error updating status: {str(e)}") 