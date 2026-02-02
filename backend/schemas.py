from typing import List, Dict, Optional, Literal, Any, Union
import uuid
from pydantic import BaseModel, Field

class Resource(BaseModel):
    id: str = Field(..., description="Unique identifier for the resource (e.g., 'vpc-main')")
    type: str = Field(..., description="AWS Resource type (e.g., 'aws_vpc', 'aws_instance')")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Configuration parameters")
    # --- NEW FIELD ---
    parent_id: Optional[str] = Field(default=None, description="ID of the container resource (e.g., VPC or Subnet ID)")
    # -----------------
    status: str = "planned"  # Flexible to handle LLM output variance (graph_phase is the source of truth)
    
    # Add metadata for UI (to persist positions if needed)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="UI positioning data")

class Edge(BaseModel):
    source: str = Field(..., description="Source Resource ID")
    target: str = Field(..., description="Target Resource ID")
    relation: str = Field(default="connects_to", description="Type of relationship (e.g., 'contains', 'depends_on', 'connects_to')")

class GraphState(BaseModel):
    graph_phase: Literal["intent", "reasoned", "implementation"] = "implementation"
    graph_version: str = Field(default_factory=lambda: str(uuid.uuid4()))
    resources: List[Resource] = Field(default_factory=list)
    edges: List[Edge] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata like cost, version info")
    reasoning: Optional[str] = Field(default=None, description="Explanation of the graph state or recent modifications")

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
    affected_node_ids: List[str] = Field(default_factory=list, description="List of downstream resource IDs affected")
    explanation: str = Field(..., description="Detailed AI explanation of why these nodes are affected")
    mitigation_strategy: str = Field(..., description="How to safely handle this deletion")

class CodeReview(BaseModel):
    score: int = Field(..., description="Quality score 0-100")
    critical_issues: List[str] = Field(default_factory=list, description="List of blocking issues (Security, Logic)")
    suggestions: List[str] = Field(default_factory=list, description="Suggestions for improvement")
    approved: bool = Field(..., description="Whether the code is ready for deployment")

class PipelineStage(BaseModel):
    name: str 
    status: str 
    logs: List[str]
    error: Optional[str] = None

class PipelineResult(BaseModel):
    success: bool
    hcl_code: str
    stages: List[PipelineStage]
    final_message: str
    resource_statuses: Dict[str, str] = Field(default_factory=dict, description="Map of Resource ID to verification status (success/failed)")

class ConfirmationReason(BaseModel):
    """Represents a reason why user confirmation is needed"""
    resource: Optional[str] = None
    type: Optional[str] = None
    reason: str
    severity: Literal["low", "medium", "high", "critical"]

class ConfirmationRequired(BaseModel):
    """Indicates if and why user confirmation is needed"""
    required: bool
    reasons: List[ConfirmationReason] = Field(default_factory=list)
    message: str = ""

class SessionState(BaseModel):
    """Tracks the current deployment workflow state"""
    phase: Literal["idle", "intent_review", "reasoned_review", "graph_pending", "code_pending", "deploying"] = "idle"
    pending_plan: Optional[PlanDiff] = None
    pending_graph: Optional['GraphState'] = None # Used for interactive refinement (Diff -> Confirm)
    generated_code: Optional[str] = None
    test_script: Optional[str] = None
