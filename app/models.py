from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class GroupSchedule(BaseModel):
    status: Literal["ON", "OFF"]
    outages: List[str] = Field(default_factory=list)


class PowerStatus(BaseModel):
    city: str
    operator: str
    type: str
    message: Optional[str] = None
    intervals: Optional[List[dict]] = None
    groups: Optional[Dict[str, GroupSchedule]] = None
    date: Optional[str] = None
    updatedAt: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
