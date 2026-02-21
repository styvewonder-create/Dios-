"""
Typed output schemas for each domain entity returned inside IngestResponse.
Each schema corresponds to one domain table fan-out.
"""
from typing import Literal, Optional, Union
from pydantic import BaseModel, ConfigDict


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: Literal["task"] = "task"
    id: int
    title: str
    status: str
    day: str
    due_date: Optional[str] = None
    project_id: Optional[int] = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: Literal["transaction"] = "transaction"
    id: int
    amount: str
    currency: str
    tx_type: str
    category: Optional[str] = None
    description: Optional[str] = None
    day: str


class FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: Literal["fact"] = "fact"
    id: int
    content: str
    category: Optional[str] = None
    day: str


class MetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: Literal["metric"] = "metric"
    id: int
    name: str
    value: str
    unit: Optional[str] = None
    day: str


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: Literal["project"] = "project"
    id: int
    name: str
    status: str
    start_date: Optional[str] = None


# Discriminated union — FastAPI serializes this with the correct subtype
RoutedEntityOut = Union[TaskOut, TransactionOut, FactOut, MetricOut, ProjectOut]
