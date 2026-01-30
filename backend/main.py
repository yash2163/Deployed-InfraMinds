from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import json
import asyncio
from agent import InfraAgent
from schemas import GraphState, PlanDiff, IntentAnalysis, BlastAnalysis, PipelineResult

app = FastAPI(title="InfraMinds Agent Core")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singleton Agent instance
agent = InfraAgent()

@app.get("/")
def read_root():
    return {"status": "InfraMinds Agent Active", "node_count": agent.graph.number_of_nodes()}

@app.get("/graph", response_model=GraphState)
def get_graph():
    """Returns the current living state graph."""
    return agent.export_state()

@app.post("/graph/reset")
def reset_graph():
    """Clears the graph state."""
    agent.graph.clear()
    return {"message": "Graph reset"}

class SimulationRequest(BaseModel):
    target_node_id: str

@app.post("/simulate/blast_radius")
def simulate_blast(req: SimulationRequest):
    """Returns the list of nodes affected by removing the target node."""
    impact = agent.simulate_blast_radius(req.target_node_id)
    return {
        "target": req.target_node_id,
        "impact_count": len(impact),
        "affected_nodes": impact
    }

class PromptRequest(BaseModel):
    prompt: str
    execution_mode: str = "deploy" # "deploy" (Free Tier) or "draft" (Full AWS)

@app.post("/agent/think")
async def agent_think(request: PromptRequest):
    """
    Analyzes intent. Returns a stream of thought logs + final JSON.
    """
    return StreamingResponse(
        agent.think_stream(request.prompt, request.execution_mode),
        media_type="application/x-ndjson"
    )

@app.post("/agent/generate_pipeline", response_model=PipelineResult)
def run_pipeline(req: PromptRequest):
    """
    Runs the full self-healing pipeline: Draft -> Critique -> Refine -> Test -> Deploy.
    """
    # Force state synchronization for consistency
    result = agent.generate_terraform_agentic(req.prompt, req.execution_mode)
    return result

@app.post("/agent/plan")
async def agent_plan(request: PromptRequest):
    # Keep plan synchronous for now as it's policy based and fast enough,
    # or upgrade later. The user asked for "Thinking" stream primarily.
    # Let's check Agent.plan_changes - it has a loop!
    # For now, keep as is.
    try:
        plan = agent.plan_changes(request.prompt, request.execution_mode)
        return plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/agent/apply")
def agent_apply(diff: PlanDiff):
    """
    Commits the plan to the graph (Action).
    """
    agent.apply_diff(diff)
    return {"status": "applied", "new_node_count": agent.graph.number_of_nodes()}

@app.post("/agent/plan_graph")
def agent_plan_graph(req: PromptRequest):
    """
    Phase 1 of two-stage deployment: Generate and apply graph plan only.
    Returns plan + confirmation requirements.
    """
    plan = agent.plan_changes(req.prompt, req.execution_mode)
    
    # Apply if passed policy checks
    if not plan.logs or not any("FAILED" in log for log in plan.logs):
        agent.apply_diff(plan)
        agent.session.pending_plan = plan
        agent.session.phase = "graph_pending"
    
    confirmation = agent.needs_user_confirmation(plan)
    
    return {
        "plan": plan,
        "graph_state": agent.export_state(),
        "confirmation": confirmation,
        "session_phase": agent.session.phase
    }

class ExplainRequest(BaseModel):
    target_node_id: str
    affected_nodes: List[str]

@app.post("/simulate/explain", response_model=BlastAnalysis)
def simulate_explain(req: ExplainRequest):
    """
    Phase 3.5: Hybrid Blast Radius.
    Uses LLM to explain the impact of the graph traversal.
    """
    return agent.explain_impact(req.target_node_id, req.affected_nodes)

@app.post("/agent/deploy")
async def agent_deploy(request: PromptRequest):
    """
    Generates and Deploys Code. Returns a stream of stages/logs + final result.
    """
    return StreamingResponse(
        agent.generate_terraform_agentic_stream(request.prompt, request.execution_mode),
        media_type="application/x-ndjson"
    )

