from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
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

@app.post("/agent/think", response_model=IntentAnalysis)
def agent_think(req: PromptRequest):
    """
    Phase 3: Real Intelligence (Gemini 1.5 Pro).
    """
    analysis = agent.think(req.prompt)
    return analysis

@app.post("/agent/plan", response_model=PlanDiff)
def agent_plan(req: PromptRequest):
    """
    Generates the diff plan to be visualized (Ghost Nodes).
    """
    return agent.plan_changes(req.prompt)

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
    plan = agent.plan_changes(req.prompt)
    
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
def agent_deploy(request: PromptRequest):
    """
    Two-stage deployment with confirmation checkpoints.
    
    Stage 1: User types request → Generate graph → Wait for CONFIRM
    Stage 2: User types CONFIRM → Generate code → Run validate/plan → Wait for CONFIRM
    Stage 3: User types CONFIRM → Deploy to LocalStack (apply + verify)
    """
    user_input = request.prompt.strip()
    
    # Check if this is a confirmation
    if user_input.upper() == "CONFIRM":
        if agent.session.phase == "graph_pending":
            # Phase 2: Generate code from approved graph
            try:
                code_data = agent.generate_terraform_from_graph()
                agent.session.generated_code = code_data["hcl_code"]
                agent.session.test_script = code_data["test_script"]
                
                # Run validate + plan (NOT apply yet)
                from schemas import PipelineStage
                stages = []
                
                # Validate
                val_stage = agent.pipeline._run_stage("validate", agent.session.generated_code)
                stages.append(val_stage)
                
                if val_stage.status == "success":
                    # Plan
                    plan_stage = agent.pipeline._run_stage("plan", agent.session.generated_code)
                    stages.append(plan_stage)
                    
                    agent.session.phase = "code_pending"
                    
                    return {
                        "success": True,
                        "hcl_code": agent.session.generated_code,
                        "stages": stages,
                        "session_phase": "code_pending",
                        "final_message": "✅ Code generated and validated. Review the Terraform code above. Type CONFIRM to deploy to LocalStack."
                    }
                else:
                    return {
                        "success": False,
                        "hcl_code": agent.session.generated_code,
                        "stages": stages,
                        "final_message": "❌ Generated code failed validation. Please report this issue."
                    }
            except Exception as e:
                return {
                    "success": False,
                    "hcl_code": "",
                    "stages": [],
                    "final_message": f"Error generating code: {str(e)}"
                }
                
        elif agent.session.phase == "code_pending":
            # Phase 3: Deploy to LocalStack
            agent.session.phase = "deploying"
            result = agent.pipeline.run_pipeline(agent.session.generated_code, agent.session.test_script)
            agent.session.phase = "idle"  # Reset after deployment
            return result
        else:
            return {
                "success": False,
                "hcl_code": "",
                "stages": [],
                "final_message": "No pending confirmation. Please start with a deployment request first."
            }
    else:
        # Legacy: Direct deployment (backward compatibility)
        result = agent.generate_terraform_agentic(user_input)
        return result
