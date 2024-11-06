from collections import defaultdict
import asyncio
from enum import Enum
import logging

class OperationType(Enum):
    DOWNLOAD = "download"
    EXTRACT = "extract"
    CONVERT = "convert"

class QueueManager:
    def __init__(self):
        self.queues = defaultdict(asyncio.Queue)  # Admin ID -> Queue
        self.active_operations = defaultdict(dict)  # Admin ID -> {operation_type: status}
        self.operation_locks = defaultdict(asyncio.Lock)  # Admin ID -> Lock
        
    async def add_to_queue(self, admin_id: int, operation_type: OperationType, data: dict):
        """Add operation to admin-specific queue"""
        await self.queues[admin_id].put((operation_type, data))
        
    async def get_next_operation(self, admin_id: int):
        """Get next operation from admin's queue"""
        return await self.queues[admin_id].get()
        
    async def start_operation(self, admin_id: int, operation_type: OperationType):
        """Mark operation as started for an admin"""
        async with self.operation_locks[admin_id]:
            self.active_operations[admin_id][operation_type] = {
                'status': 'running',
                'progress': 0,
                'start_time': asyncio.get_event_loop().time()
            }
            
    async def update_progress(self, admin_id: int, operation_type: OperationType, progress: int):
        """Update operation progress"""
        if admin_id in self.active_operations:
            self.active_operations[admin_id][operation_type]['progress'] = progress
            
    async def complete_operation(self, admin_id: int, operation_type: OperationType):
        """Mark operation as completed"""
        async with self.operation_locks[admin_id]:
            if admin_id in self.active_operations:
                del self.active_operations[admin_id][operation_type] 