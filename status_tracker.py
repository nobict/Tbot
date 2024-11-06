from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import asyncio

@dataclass
class OperationStatus:
    operation_type: str
    start_time: datetime
    progress: int = 0
    status: str = "running"
    error: Optional[str] = None
    
class StatusTracker:
    def __init__(self):
        self._operations = {}
        self._lock = asyncio.Lock()
        
    async def start_operation(self, admin_id: int, operation_type: str):
        async with self._lock:
            self._operations[(admin_id, operation_type)] = OperationStatus(
                operation_type=operation_type,
                start_time=datetime.now()
            )
            
    async def update_progress(self, admin_id: int, operation_type: str, progress: int):
        async with self._lock:
            if (admin_id, operation_type) in self._operations:
                self._operations[(admin_id, operation_type)].progress = progress
                
    async def get_status(self, admin_id: int):
        """Get status of all operations for an admin"""
        return {
            op_type: status 
            for (aid, op_type), status in self._operations.items()
            if aid == admin_id
        } 