from typing import List, Dict, Optional, Literal, Any, Union
from pydantic import BaseModel, Field

class Resource(BaseModel):
    id: str = Field(..., description="Unique identifier for the resource (e.g., 'vpc-main')")
    type: str = Field(..., description="AWS Resource type (e.g., 'aws_vpc', 'aws_instance')")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Configuration parameters")
    status: Literal["planned", "active", "deleted"] = "planned"

class Edge(BaseModel):
    source: str = Field(..., description="Source Resource ID")
    target: str = Field(..., description="Target Resource ID")
    relation: str = Field(..., description="Type of relationship (e.g., 'contains', 'depends_on', 'connects_to')")

class GraphState(BaseModel):
    resources: List[Resource] = Field(default_factory=list)
    edges: List[Edge] = Field(default_factory=list)

class IntentAnalysis(BaseModel):
    summary: str = Field(..., description="Summary of the user's architectural intent")
    risks: List[str] = Field(default_factory=list, description="Potential risks identified")
    suggested_actions: List[str] = Field(default_factory=list, description="High-level actions to take")

class PlanDiff(BaseModel):
    """Represents a set of changes to apply to the graph."""
    add_resources: List[Resource] = []
    remove_resources: List[str] = Field(default_factory=list, description="List of Resource IDs to remove")
    add_edges: List[Edge] = []
    remove_edges: List[Dict[str, str]] = [] # List of {source, target} dicts
    reasoning: str = Field(..., description="Why these changes are being made")
    logs: List[str] = Field(default_factory=list, description="Agent's internal thought process and retry logs")

class BlastAnalysis(BaseModel):
    target_node: str
    impact_level: Literal["Low", "Medium", "High", "Critical"]
    affected_count: int
    explanation: str = Field(..., description="Detailed AI explanation of why these nodes are affected")
    mitigation_strategy: str = Field(..., description="How to safely handle this deletion")
