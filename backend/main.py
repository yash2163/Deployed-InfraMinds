from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import json
import asyncio
from agent import InfraAgent
from schemas import GraphState, PlanDiff, IntentAnalysis, BlastAnalysis, PipelineResult
from cost import CostEstimator, CostReport
from layout_agent import generate_layout_plan
from demo_data import DEMO_GRAPH, DEMO_TERRAFORM, DEMO_LOGS, DEMO_PROMPT, DEMO_IMAGE_PATH

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
cost_estimator = CostEstimator()

# DEMO MODE CONFIGURATION
DEMO_MODE = True # Set to True for the Hackathon/Demo Deployment


class PromptRequest(BaseModel):
    prompt: str
    execution_mode: str = "deploy"

@app.post("/agent/deploy")
async def agent_deploy(request: PromptRequest):
    """
    Streaming Endpoint for Real-Time UI Updates.
    """
    if DEMO_MODE:
        async def mock_stream():
            for log in DEMO_LOGS:
                yield json.dumps({"type": "log", "content": log}) + "\n"
                await asyncio.sleep(0.3) # Simulate processing time
            
            # Send the final Terraform code as a result
            yield json.dumps({"type": "result", "payload": {"hcl_code": DEMO_TERRAFORM}}) + "\n"
            
        return StreamingResponse(mock_stream(), media_type="application/x-ndjson")

    return StreamingResponse(
        agent.stream_terraform_gen(request.prompt, request.execution_mode),
        media_type="application/x-ndjson"
    )


@app.post("/agent/plan_stream")
async def agent_plan_stream(request: PromptRequest):
    if DEMO_MODE:
        raise HTTPException(status_code=403, detail="Action disabled in Demo Mode.")
    """
    Streaming Endpoint for Phase 1 (Planning).
    """
    return StreamingResponse(
        agent.plan_graph_stream(request.prompt, request.execution_mode),
        media_type="application/x-ndjson"
    )

@app.get("/")
def read_root():
    return {"status": "InfraMinds Agent Active", "node_count": agent.graph.number_of_nodes()}

@app.get("/graph", response_model=GraphState)
def get_graph():
    """Returns the current living state graph."""
    return agent.export_state()

@app.post("/graph/reset")
def reset_graph():
    """Clears the graph state and session history."""
    agent.hard_reset()
    return {"message": "Graph and Session HARD RESET complete"}
    return {"message": "Graph and Session reset"}

@app.get("/cost", response_model=CostReport)
def get_cost(phase: str = "implementation"):
    """Returns the estimated cost of the current infrastructure."""
    
    # Return hardcoded demo cost values
    from demo_data import DEMO_COST
    return CostReport(**DEMO_COST)

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
    if DEMO_MODE:
        raise HTTPException(status_code=403, detail="Action disabled in Demo Mode.")
    """
    Analyzes intent. Returns a stream of thought logs + final JSON.
    """
    return StreamingResponse(
        agent.think_stream(request.prompt, request.execution_mode),
        media_type="application/x-ndjson"
    )

@app.post("/agent/generate_pipeline", response_model=PipelineResult)
def run_pipeline(req: PromptRequest):
    if DEMO_MODE:
        raise HTTPException(status_code=403, detail="Action disabled in Demo Mode.")
    """
    Runs the full self-healing pipeline: Draft -> Critique -> Refine -> Test -> Deploy.
    """
    # Force state synchronization for consistency
    result = agent.generate_terraform_agentic(req.prompt, req.execution_mode)
    return result

@app.post("/agent/plan")
async def agent_plan(request: PromptRequest):
    if DEMO_MODE:
        raise HTTPException(status_code=403, detail="Action disabled in Demo Mode.")
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
    if DEMO_MODE:
        raise HTTPException(status_code=403, detail="Action disabled in Demo Mode.")
    """
    Commits the plan to the graph (Action).
    """
    agent.apply_diff(diff)
    return {"status": "applied", "new_node_count": agent.graph.number_of_nodes()}

@app.post("/agent/plan_graph")
def agent_plan_graph(req: PromptRequest):
    if DEMO_MODE:
        raise HTTPException(status_code=403, detail="Action disabled in Demo Mode.")
    """
    Phase 1 of two-stage deployment: Generate and apply graph plan only.
    Returns plan + confirmation requirements.
    """
    plan = agent.plan_changes(req.prompt, req.execution_mode)
    
    # Do NOT apply immediately. Store as pending.
    if not plan.logs or not any("FAILED" in log for log in plan.logs):
        agent.session.pending_plan = plan
        agent.session.phase = "graph_pending"
        
        # Add "proposed" status to resources for visualization
        for res in plan.add_resources:
            res.status = "proposed"
            # Temporarily add to graph for visualization? 
            # Better approach: Return the plan, and Frontend overlays it.
            # OR: Add to graph with status="proposed" and filter out during generation if rejected.
            # Let's add to graph but marked as proposed.
            agent.graph.add_node(res.id, **res.model_dump())
            
        for edge in plan.add_edges:
            # We need to track proposed edges too
            agent.graph.add_edge(edge.source, edge.target, relation=edge.relation, status="proposed")
    
    confirmation = agent.needs_user_confirmation(plan)
    
    return {
        "plan": plan,
        "graph_state": agent.export_state(),
        "confirmation": confirmation,
        "session_phase": agent.session.phase
    }

@app.get("/agent/health")
def agent_health():
    return {"status": "ok", "version": "debug_v1", "demo_mode": DEMO_MODE}

@app.get("/agent/demo_data")
def get_demo_data():
    """Returns the static data for the guided demo."""
    return {
        "graph": DEMO_GRAPH,
        "terraform": DEMO_TERRAFORM,
        "logs": DEMO_LOGS,
        "prompt": DEMO_PROMPT,
        "image": DEMO_IMAGE_PATH
    }

@app.post("/agent/approve")
def agent_approve():
    if DEMO_MODE:
        raise HTTPException(status_code=403, detail="Action disabled in Demo Mode.")
    """
    Commits the pending plan to the active graph.
    """
    if not agent.session.pending_plan:
        return {"status": "no_pending_plan", "message": "No plan waiting for approval."}
    
    # 1. Update statuses from 'proposed' to 'active' (or 'planned')
    # Actually, apply_diff handles adding, but we already added them as 'proposed'.
    # We just need to confirm them.
    
    plan = agent.session.pending_plan
    
    # Commit Proposed Resources
    for res in plan.add_resources:
        if agent.graph.has_node(res.id):
            agent.graph.nodes[res.id]["status"] = "active"  # Mark as active after approval
            
    # Commit Proposed Edges
    for edge in plan.add_edges:
        if agent.graph.has_edge(edge.source, edge.target):
             nx_edge = agent.graph[edge.source][edge.target]
             if isinstance(nx_edge, dict):
                 nx_edge.pop("status", None) # Remove 'proposed' status
    
    # Handle Removals (delayed until approval)
    for res_id in plan.remove_resources:
        if agent.graph.has_node(res_id):
            agent.graph.remove_node(res_id)
            
    agent.session.pending_plan = None
    agent.session.phase = "idle"
    agent.save_state_to_disk()
    
    return {"status": "approved", "message": "Plan approved. Ready to deploy."}

@app.post("/agent/reject")
def agent_reject():
    if DEMO_MODE:
        raise HTTPException(status_code=403, detail="Action disabled in Demo Mode.")
    """
    Rejects the pending plan and reverts 'proposed' changes.
    """
    if not agent.session.pending_plan:
        return {"status": "no_pending_plan", "message": "No plan waiting for approval."}
        
    plan = agent.session.pending_plan
    
    # Revert Proposed Resources
    for res in plan.add_resources:
        if agent.graph.has_node(res.id) and agent.graph.nodes[res.id].get("status") == "proposed":
            agent.graph.remove_node(res.id)
            
    # Revert Proposed Edges
    for edge in plan.add_edges:
        if agent.graph.has_edge(edge.source, edge.target):
             # Check if it was proposed. Since edges don't have IDs, this is tricky.
             # Heuristic: If we are rejecting, we just remove the edges added in the plan.
             agent.graph.remove_edge(edge.source, edge.target)

    agent.session.pending_plan = None
    agent.session.phase = "idle"
    
    return {"status": "rejected", "message": "Plan rejected. Graph reverted."}

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

@app.post("/agent/modify")
async def agent_modify(request: PromptRequest):
    if DEMO_MODE:
        raise HTTPException(status_code=403, detail="Action disabled in Demo Mode.")
    """
    CRITICAL: Interactive Refinement.
    Modifies the CURRENT graph phase based on user feedback.
    """
    if agent.session.phase == "idle":
        raise HTTPException(400, "No active session to modify.")
        
    return StreamingResponse(
        agent.modify_graph_stream(request.prompt),
        media_type="application/x-ndjson"
    )

class ConfirmRequest(BaseModel):
    accept: bool

@app.post("/graph/confirm_change")
async def confirm_change(req: ConfirmRequest):
    if DEMO_MODE:
        raise HTTPException(status_code=403, detail="Action disabled in Demo Mode.")
    """
    Phase 2.5: Interactive Confirmation.
    Accepts or Discards the pending graph modification.
    """
    if not agent.session.pending_graph:
         raise HTTPException(400, "No pending modification to confirm.")

    return StreamingResponse(
        agent.confirm_modification_stream(req.accept),
        media_type="application/x-ndjson"
    )

@app.get("/agent/session")
def get_session():
    """Restores session state for frontend recovery."""
    return {
        "phase": agent.session.phase,
        "intent_graph": agent.intent_graph.model_dump() if agent.intent_graph else None,
        "reasoned_graph": agent.reasoned_graph.model_dump() if agent.reasoned_graph else None,
        "implementation_graph": agent.export_state().model_dump() if agent.graph.number_of_nodes() > 0 else None, # NetworkX is truth for implementation
        "history": agent.history
    }

@app.post("/agent/visualize")
async def agent_visualize(file: UploadFile = File(...)):
    if DEMO_MODE:
        raise HTTPException(status_code=403, detail="Action disabled in Demo Mode.")
    """
    Unified Entry: Image -> Intent.
    """
    contents = await file.read()
    return StreamingResponse(
        agent.generate_intent_stream(contents),
        media_type="application/x-ndjson"
    )

@app.post("/agent/approve/intent")
async def approve_intent(request: PromptRequest):
    if DEMO_MODE:
        raise HTTPException(status_code=403, detail="Action disabled in Demo Mode.")
    """Triggers Phase 2: Unified Reasoned Expansion (Intent -> Policies -> Verify -> Architecture)."""
    if not agent.intent_graph:
        raise HTTPException(400, "No Intent Graph to approve.")
    
    return StreamingResponse(
        agent.stream_expanded_architecture(execution_mode=request.execution_mode),
        media_type="application/x-ndjson"
    )



@app.post("/agent/layout")
async def agent_layout(req: PromptRequest):
    if DEMO_MODE:
        raise HTTPException(status_code=403, detail="Action disabled in Demo Mode.")
    """
    Experimental: Uses Gemini to calculate a 'LucidChart-Style' Layout Plan.
    Returns: JSON Map of { node_id: { x, y, width, height, parentId } }
    """
    # 1. Get current graph state
    current_state = agent.export_state().model_dump()
    
    # 2. Ask Gemini for layout coordinates
    layout_map = await generate_layout_plan(current_state)
    
    return layout_map

