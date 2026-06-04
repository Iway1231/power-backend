# app/models.py

from pydantic import BaseModel
from typing import Dict, List, Optional, Literal


# ==================================================
# GROUP SCHEDULE (🔥 БЕЗ `on`)
# ==================================================

class GroupSchedule(BaseModel):
    status: Literal["ON", "OFF"]
    outages: List[str]


# ==================================================
# MAIN RESPONSE MODEL
# ==================================================

class PowerStatus(BaseModel):
    city: str
    operator: str

    type: str
    message: Optional[str] = None

    # для текстових статусів
    intervals: Optional[List[str]] = None

    # 🔥 ГОЛОВНЕ — groups -> GroupSchedule
    groups: Optional[Dict[str, GroupSchedule]] = None

    date: Optional[str] = None
    updatedAt: Optional[str] = None

    # 🔒 ЗАВЖДИ float
    confidence: float = 1.0
