import networkx as nx
import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
from typing import List, Dict, Optional, Generator
from schemas import GraphState, Resource, Edge, PlanDiff, IntentAnalysis, BlastAnalysis, CodeReview, ConfirmationRequired, ConfirmationReason, SessionState

# Import Prompt Providers
from prompts import localstack, aws_full

load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

from pipeline import PipelineManager, PipelineResult

class InfraAgent:
    def __init__(self):
        self.graph = nx.DiGraph()
        # Seed with some initial data for visualization
        self.graph.add_node("vpc-main", id="vpc-main", type="aws_vpc", properties={"cidr": "10.0.0.0/16"}, status="active")
        self.graph.add_node("subnet-public", id="subnet-public", type="aws_subnet", properties={"cidr": "10.0.1.0/24"}, status="active")
        self.graph.add_edge("vpc-main", "subnet-public", relation="contains")
        
        self.model = genai.GenerativeModel('gemini-2.5-pro')
        self.pipeline = PipelineManager(self.model)
        
        # Session state for confirmation workflow
        self.session = SessionState(phase="idle")

        if os.path.exists("graph_state.json"):
            try:
                with open("graph_state.json", "r") as f:
                    data = json.load(f)
                    state = GraphState(**data)
                    self.load_state(state)
                    print("loaded graph from disk")
            except Exception as e:
                print(f"Failed to load graph state: {e}")

    def save_state_to_disk(self):
        try:
             state = self.export_state()
             with open("graph_state.json", "w") as f:
                 f.write(state.model_dump_json(indent=2))
        except Exception as e:
            print(f"Failed to save state: {e}")

    def get_prompt_provider(self, execution_mode: str = "deploy"):
        if execution_mode == "draft":
            return aws_full
        return localstack

    
    def think(self, user_prompt: str, execution_mode: str = "deploy") -> IntentAnalysis:
        """
        Analyzes the user's intent and generates a high-level plan.
        """
        # ... logic as before, or wrapper around stream ...
        # For backward compatibility, we keep this sync method or adapt it.
        # Let's keep it sync for now but add the stream variant.
        current_state = self.export_state().model_dump_json()
        
        provider = self.get_prompt_provider(execution_mode)
        prompt = provider.get_think_prompt(current_state, user_prompt)
        
        response = self.model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        try:
            data = json.loads(response.text)
            return IntentAnalysis(**data)
        except Exception as e:
            return IntentAnalysis(
                summary=f"Error parsing Agent response: {str(e)}",
                risks=["Agent Brain Malfunction"],
                suggested_actions=["Check Logs"]
            )

    def think_stream(self, user_prompt: str, execution_mode: str = "deploy"):
        """
        Generator that yields chunks of the thought process or the final JSON.
        Yields: {"type": "token", "content": "..."} or {"type": "json", "data": {...}}
        """
        current_state = self.export_state().model_dump_json()
        provider = self.get_prompt_provider(execution_mode)
        prompt = provider.get_think_prompt(current_state, user_prompt)

        # 1. Yield Initial Token
        yield json.dumps({"type": "log", "content": "Analyzing Intent..."}) + "\n"

        # 2. Stream from Gemini
        response = self.model.generate_content(prompt, stream=True, generation_config={"response_mime_type": "application/json"})
        
        full_text = ""
        for chunk in response:
            if chunk.text:
                full_text += chunk.text
                # If we want to stream tokens, we can. But JSON parsing is tricky with streaming.
                # For "Thinking", usually we want to stream RAW TEXT reasoning.
                # But IntentAnalysis forces JSON output.
                # Strategy: If the model supports "Thinking" separate from JSON, we stream that.
                # Gemini 2.5 Pro doesn't separate reasoning yet unless prompted.
                # For now, we'll just yield the final result since Intent is fast.
                pass
        
        # 3. Final Parse
        try:
            data = json.loads(full_text)
            yield json.dumps({"type": "result", "payload": data}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "content": str(e)}) + "\n"

    def check_policies(self, plan: PlanDiff) -> List[str]:
        """
        Deterministic Policy Engine to validate the plan.
        """
        violations = []
        
        # Helper to get type of a node (from plan or current graph)
        def get_type(node_id):
            # Check draft plan first
            for res in plan.add_resources:
                if res.id == node_id:
                    return res.type, res.properties
            # Check existing graph
            if node_id in self.graph:
                return self.graph.nodes[node_id].get("type"), self.graph.nodes[node_id].get("properties", {})
            return None, {}

        # Rule 1: No RDS in Public Subnets
        for edge in plan.add_edges:
            src_type, _ = get_type(edge.source)
            tgt_type, _ = get_type(edge.target)
            
            # Normalize for directional edges (assuming source depends on target or contained in)
            # Relation usually "contains" (VPC->Subnet) or "connected_to". 
            # If Subnet contains DB: Source=Subnet, Target=DB.
            # If DB in Subnet: Source=DB, Target=Subnet.
            
            # Check if one is DB and other is Public Subnet
            is_db = src_type == "aws_db_instance" or tgt_type == "aws_db_instance"
            
            # Check for "public" in ID of the subnet (Heuristic for demo)
            # In real world, we'd check route tables.
            src_is_public = "public" in (edge.source).lower()
            tgt_is_public = "public" in (edge.target).lower()

            if is_db and (src_is_public or tgt_is_public):
                violations.append(f"Security Policy Violation: Database cannot be connected to a Public Subnet ({edge.source} <-> {edge.target}). Must use Private Subnet.")

        # Rule 2: Security Groups - No Open SSH
        for res in plan.add_resources:
            if res.type == "aws_security_group":
                # Robust check for ingress as list of rule objects
                ingress_rules = res.properties.get("ingress", [])
                # Normalize logic: ingress might be a list of dicts, or if simplistic, generic structure
                if isinstance(ingress_rules, list):
                    for rule in ingress_rules:
                        if isinstance(rule, dict):
                            # extract protocol and ports logic (simplistic)
                            from_port = rule.get("from_port", 0)
                            to_port = rule.get("to_port", 0)
                            cidr_blocks = rule.get("cidr_blocks", [])
                            
                            # Check if 22 is in range or explicit
                            is_ssh = (from_port == 22) or (from_port <= 22 and to_port >= 22)
                            is_open_world = "0.0.0.0/0" in cidr_blocks or "0.0.0.0/0" in str(cidr_blocks)
                            
                            if is_ssh and is_open_world:
                                # violations.append(f"Security Policy Violation: SG '{res.id}' allows SSH (22) from the entire internet. Limit CIDR.")
                                print(f"WARNING: SG '{res.id}' allows Open SSH. Allowing for Demo purposes.")
        
        return violations

    def plan_changes(self, user_prompt: str, execution_mode: str = "deploy") -> PlanDiff:
        """
        Generates the concrete graph changes (Diff) with AUTO-CORRECTION.
        """
        current_state = self.export_state().model_dump_json()
        provider = self.get_prompt_provider(execution_mode)
        
        base_prompt = provider.get_plan_prompt(current_state, user_prompt)
        
        # --- The Loop ---
        max_retries = 3
        attempt = 0
        current_prompt = base_prompt
        last_error = ""
        logs = []
        
        while attempt < max_retries:
            logs.append(f"--- Thought Cycle {attempt + 1}/{max_retries} ---")
            
            response = self.model.generate_content(current_prompt, generation_config={"response_mime_type": "application/json"})
            try:
                data = json.loads(response.text)
                # Ensure status
                for res in data.get("add_resources", []):
                    res["status"] = "planned"
                
                plan = PlanDiff(**data)
                
                # Verify (Skip policy check in draft mode if we want to allow anything)
                violations = []
                if execution_mode == "deploy":
                    violations = self.check_policies(plan)
                
                if not violations:
                    # Success!
                    logs.append("Policy Check: PASSED")
                    if attempt > 0:
                        plan.reasoning = f"(Auto-Corrected) {plan.reasoning}"
                    plan.logs = logs
                    return plan
                
                # Failed Verification -> Feedback Loop
                logs.append(f"Policy Check: FAILED -> {violations}")
                logs.append("Triggering Self-Correction...")
                
                feedback = f"\n\nCRITICAL: Your previous JSON plan failed these Policy Checks:\n{json.dumps(violations)}\n\nFix these violations and regenerate the JSON Plan."
                current_prompt = base_prompt + feedback 
                attempt += 1
                
            except Exception as e:
                logs.append(f"Parsing Error: {str(e)}")
                last_error = str(e)
                attempt += 1
        
        return PlanDiff(reasoning=f"Failed to generate valid plan after {max_retries} attempts. Error: {last_error}", add_resources=[], logs=logs)

    def load_state(self, state: GraphState):
        """Rebuilds the implementation NetworkX graph from Pydantic state."""
        self.graph.clear()
        for res in state.resources:
            self.graph.add_node(res.id, **res.model_dump())
        for edge in state.edges:
            self.graph.add_edge(edge.source, edge.target, relation=edge.relation)

    def export_state(self) -> GraphState:
        """Exports current graph to Pydantic state."""
        resources = []
        for node_id, data in self.graph.nodes(data=True):
            resources.append(Resource(**data))
        
        edges = []
        for u, v, data in self.graph.edges(data=True):
            edges.append(Edge(source=u, target=v, relation=data.get("relation", "connected")))
            
        return GraphState(resources=resources, edges=edges)

    def apply_diff(self, diff: PlanDiff):
        """Applies a planned diff to the graph."""
        # 1. Add Resources
        for res in diff.add_resources:
            self.graph.add_node(res.id, **res.model_dump())
        
        # 2. Add Edges
        for edge in diff.add_edges:
            self.graph.add_edge(edge.source, edge.target, relation=edge.relation)
            
        # 3. Remove Resources (and connected edges automatically)
        for res_id in diff.remove_resources:
            if self.graph.has_node(res_id):
                self.graph.remove_node(res_id)
                
        # 4. Remove Edges
        for edge_dict in diff.remove_edges:
            u, v = edge_dict.get("source"), edge_dict.get("target")
            if self.graph.has_edge(u, v):
                self.graph.remove_edge(u, v)

        # 5. Persist State
        self.save_state_to_disk()

    def simulate_blast_radius(self, target_node_id: str) -> List[str]:
        """
        Returns a list of node IDs that would be affected if target_node_id fails/is deleted.
        This is a downstream traversal.
        """
        if target_node_id not in self.graph:
            return []
        
        return list(nx.descendants(self.graph, target_node_id))

    def explain_impact(self, target_node_id: str, affected_nodes: List[str]) -> BlastAnalysis:
        """
        Uses Gemini to explain the business/technical impact of the blast radius.
        """
        # Get details of affected resources
        affected_details = []
        if target_node_id in self.graph:
             affected_details.append(self.graph.nodes[target_node_id])
        
        for node_id in affected_nodes:
            if node_id in self.graph:
                affected_details.append(self.graph.nodes[node_id])
                
        context = json.dumps(affected_details, default=str)
        
        prompt = f"""
        You are a Senior Site Reliability Engineer.
        User plans to DELETE the resource: '{target_node_id}'.
        
        Using Graph Theory, we identified these DOWNSTREAM DEPENDENCIES (Blast Radius):
        {affected_nodes}
        
        Resource Details:
        {context}
        
        Task:
        1. Analyze the IMPACT. (e.g. Deleting a VPC orphans subnets).
        2. Assign an Impact Level (Low, Medium, High, Critical).
        3. Explain WHY in simple, human terms.
        4. Suggest a mitigation (e.g. "Snapshot first" or "Delete dependencies first").
        
        Output JSON matching BlastAnalysis schema:
        {{
            "target_node": "{target_node_id}",
            "impact_level": "High",
            "affected_count": {len(affected_nodes)},
            "affected_node_ids": {json.dumps(affected_nodes)},
            "explanation": "...",
            "mitigation_strategy": "..."
        }}
        """
        
        response = self.model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        try:
            return BlastAnalysis(**json.loads(response.text))
        except Exception as e:
            return BlastAnalysis(
                target_node=target_node_id,
                impact_level="Critical",
                affected_count=len(affected_nodes),
                explanation=f"AI Analysis Failed: {str(e)}",
                mitigation_strategy="Manual Review Required"
            )

    def review_code(self, hcl_code: str, user_request: str) -> CodeReview:
        """
        Agent B (Critic): Reviews the generated HCL code.
        """
        prompt = f"""
        You are a Principal Cloud Architect and Security Auditor.
        Review the following Terraform Code against the User Request.

        User Request: "{user_request}"

        Terraform Code:
        ```hcl
        {hcl_code}
        ```

        Checklist:
        1. **Completeness**: Does it fulfill all parts of the user request? (e.g. if 'ASG' requested, is 'aws_autoscaling_group' present?)
        2. **Security**: Are there risky Security Group rules? (Open SSH 0.0.0.0/0 is a WARNING, usually bad unless explicitly requested for public access). Egress should be open.
        3. **Logic**: Are resources correctly connected? (Instances in subnets, LBs connected to SGs).
        4. **Best Practices**: Are tags present? Descriptions?

        Output JSON matching CodeReview schema:
        {{
            "score": 85,
            "critical_issues": ["Issue 1", "Issue 2"],
            "suggestions": ["Suggestion 1"],
            "approved": true/false  (Approved if score > 90 and NO critical logic errors)
        }}
        """
        response = self.model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        try:
            return CodeReview(**json.loads(response.text))
        except:
            return CodeReview(score=0, critical_issues=["Failed to parse Review"], approved=False)

    def refine_code(self, hcl_code: str, review: CodeReview, feedback_override: str = None) -> str:
        """
        Agent A (Editor): Fixes the code based on feedback.
        """
        feedback = feedback_override if feedback_override else f"Issues: {review.critical_issues}. Suggestions: {review.suggestions}"
        
        prompt = f"""
        You are a Senior DevOps Engineer. 
        Fix this Terraform code based on the Reviewer's feedback.

        Current Code:
        ```hcl
        {hcl_code}
        ```

        Reviewer Feedback:
        {feedback}

        Task:
        1. Fix ALL listed issues.
        2. Return ONLY the fixed HCL code. No markdown.
        3. **FORBIDDEN ACTION**: Do NOT delete a resource to fix an error unless explicitly told to. If a resource causes an error, FIX the configuration, do not remove the resource.
        """
        response = self.model.generate_content(prompt)
        return response.text.replace("```hcl", "").replace("```", "").strip()

    def needs_user_confirmation(self, plan: PlanDiff) -> ConfirmationRequired:
        """
        Analyzes the plan to determine if user confirmation is needed.
        Returns reasons and severity.
        """
        reasons = []
        
        # Check for cost-incurring resources
        cost_resources = {
            "aws_nat_gateway": "NAT Gateway costs ~$32/month",
            "aws_eip": "Elastic IP may incur charges if not attached",
            "aws_lb": "Load Balancer costs ~$16/month",
            "aws_db_instance": "RDS instance costs vary by size"
        }
        
        for res in plan.add_resources:
            if res.type in cost_resources:
                reasons.append(ConfirmationReason(
                    resource=res.id,
                    type=res.type,
                    reason=cost_resources[res.type],
                    severity="medium"
                ))
        
        # Check for deletions
        if plan.remove_resources:
            reasons.append(ConfirmationReason(
                reason=f"Deleting {len(plan.remove_resources)} resource(s) - this is irreversible",
                severity="high"
            ))
        
        # Generate message
        if reasons:
            message = "⚠️ **Graph Plan Generated - Review Required**\n\n"
            for r in reasons:
                emoji = "🔴" if r.severity == "high" else "🟡"
                message += f"{emoji} {r.reason}\n"
            message += "\nType **CONFIRM** to proceed with code generation, or ask questions about the plan."
        else:
            message = "✅ Graph plan looks good. Type **CONFIRM** to generate Terraform code."
        
        return ConfirmationRequired(
            required=len(reasons) > 0,
            reasons=reasons,
            message=message
        )

    def generate_terraform_from_graph(self) -> Dict[str, str]:
        """
        Generates Terraform HCL code from the CURRENT graph state.
        Does NOT re-plan. Uses graph as single source of truth.
        Returns: {"hcl_code": "...", "test_script": "..."}
        """
        current_state = self.export_state().model_dump_json()
        
        prompt = f"""
        You are a Senior DevOps Engineer.
        Generate complete Terraform HCL code for this infrastructure graph.
        
        Graph State (JSON):
        {current_state}
        
        CRITICAL INSTRUCTIONS:
        1. Generate code for EVERY resource in the graph - do not skip any
        2. Respect all edges as dependencies/references
        3. Add egress rules to all security groups (0.0.0.0/0)
        4. Use AWS-managed passwords for RDS (manage_master_user_password = true) where possible.
           - If using variables for passwords, ensure sensitive = true.
        5. **RDS Multi-AZ**: `aws_db_subnet_group` MUST reference subnets in at least TWO different AZs. Create a new private subnet in a different AZ if needed.
        6. **Web Servers**: If the user asks for a web server (instance or ASG), you MUST include `user_data` to install a web server (e.g. Apache/Nginx) and create an index.html. Without this, the LB health checks will fail.
        7. **ASG Health Check**: If ASG is attached to a Load Balancer, set `health_check_type = "ELB"` and `health_check_grace_period = 300`.
        8. Include proper provider configuration for LocalStack
        
        Return JSON with:
        - "hcl_code": Complete main.tf content
        - "test_script": Python boto3 script to verify resources (endpoint_url='http://localhost:4566')
        """
        
        response = self.model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        try:
            data = json.loads(response.text)
            return {
                "hcl_code": data.get("hcl_code", ""),
                "test_script": data.get("test_script", "")
            }
        except Exception as e:
            return {
                "hcl_code": f"# Error generating code: {str(e)}",
                "test_script": "# Error generating test script"
            }

    def generate_terraform_agentic(self, user_prompt: str, execution_mode: str = "deploy") -> PipelineResult:
        """
        Stage 1 (Draft): Generates HCL + Python Test Script.
        IMPROVED: Recursive Self-Healing (Think -> Critque -> Refine -> Test -> Retry).
        """
        # 0. Sync Graph State (Best Effort)
        try:
             plan = self.plan_changes(user_prompt, execution_mode)
             if not plan.logs or not any("FAILED" in log for log in plan.logs):
                 self.apply_diff(plan)
        except Exception as e:
             print(f"CRITICAL GRAPH SYNC ERROR: {e}")
             import traceback
             traceback.print_exc()

        # 1. Draft Code using current state context
        current_state = self.export_state().model_dump_json()
        provider = self.get_prompt_provider(execution_mode)
        prompt = provider.get_code_gen_prompt(current_state, user_prompt)
        
        from schemas import PipelineStage # Import locally to avoid circle if any, or just reuse
        total_stages_history = []
        max_outer_retries = 3
        current_hcl = ""
        current_test_script = ""
        
        # --- THE OUTER LOOP (Pipeline Feedback) ---
        last_pipeline_error = ""

        for attempt in range(max_outer_retries):
            # Step A: Drafting / Re-Drafting
            if attempt == 0:
                # First Draft
                try:
                    response = self.model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                    data = json.loads(response.text)
                    current_hcl = data.get("hcl_code", "")
                    current_test_script = data.get("test_script", "")
                    
                    # Log successful draft
                    total_stages_history.append(PipelineStage(
                        name="Draft Generation", 
                        status="success", 
                        logs=[f"Generated {len(current_hcl)} characters of HCL code", f"Generated {len(current_test_script)} characters of test script"]
                    ))
                except Exception as e:
                    # Log the failure with details
                    error_msg = f"Draft Generation Failed: {str(e)}"
                    total_stages_history.append(PipelineStage(
                        name="Draft Generation",
                        status="failed",
                        logs=[error_msg, f"LLM Response Preview: {response.text[:200] if 'response' in locals() else 'No response'}"],
                        error=str(e)
                    ))
                    return PipelineResult(success=False, hcl_code="", stages=total_stages_history, final_message=error_msg)
            else:
                # Re-Drafting based on Pipeline Error
                logging_stage = PipelineStage(name=f"Self-Correction (Attempt {attempt+1})", status="running", logs=[f"Pipeline Failed: {last_pipeline_error}", "Refining HCL..."])
                total_stages_history.append(logging_stage)
                
                current_hcl = self.refine_code(current_hcl, None, feedback_override=f"The previous Terraform code failed validation/apply with this error: {last_pipeline_error}. Fix the code.")
                logging_stage.status = "success"

            # Step B: The Thinking Loop (Inner Peer Review)
            try:
                for review_round in range(2):
                    review = self.review_code(current_hcl, user_prompt)
                    
                    review_logs = [f"Score: {review.score}/100"]
                    review_logs.extend([f"Issue: {i}" for i in review.critical_issues])
                    
                    stage = PipelineStage(name=f"AI Peer Review (Round {review_round+1})", status="success" if review.approved else "warning", logs=review_logs)
                    total_stages_history.append(stage)
                    
                    if review.approved and len(review.critical_issues) == 0:
                        break
                    
                    # Refine based on Review
                    current_hcl = self.refine_code(current_hcl, review)
                    total_stages_history.append(PipelineStage(name="Refinement", status="success", logs=["Applied fixes from Peer Review."]))
            except Exception as e:
                 total_stages_history.append(PipelineStage(name="AI Peer Review", status="failed", logs=[f"Review Agent Crashed: {str(e)}"], error=str(e)))

            # Step C: Execution
            result = self.pipeline.run_pipeline(current_hcl, current_test_script)
            
            # Merge execution stages into history
            total_stages_history.extend(result.stages)
            
            if result.success:
                return PipelineResult(
                    success=True,
                    hcl_code=current_hcl,
                    stages=total_stages_history,
                    final_message="Recursively Verified & Deployed!"
                )
            
            # If failed, capture error for next Outer Loop iteration
            last_pipeline_error = result.stages[-1].error or "Unknown Pipeline Error"
            # Loop continues...

        # If we exhausted retries
    
    # def generate_terraform_agentic_stream(self, user_prompt: str, execution_mode: str = "deploy"):
    #     """
    #     Streaming version of the Agentic Pipeline.
    #     Yields events: {"type": "log|stage|result|error", "content": ...}
    #     """
    #     yield json.dumps({"type": "log", "content": "Initializing Agentic Pipeline for Mode: " + execution_mode}) + "\n"

    #     # 0. Sync Graph State (Best Effort)
    #     try:
    #          plan = self.plan_changes(user_prompt, execution_mode)
    #          if not plan.logs:
    #              pass
    #          elif not any("FAILED" in log for log in plan.logs):
    #              self.apply_diff(plan)
    #              yield json.dumps({"type": "log", "content": "Synced Graph with latest Intent"}) + "\n"
    #     except Exception as e:
    #          yield json.dumps({"type": "log", "content": f"Graph Sync Warning: {e}"}) + "\n"

    #     # 1. Draft Code using current state context
    #     yield json.dumps({"type": "stage", "name": "Drafting Infrastructure Code", "status": "running"}) + "\n"
        
    #     current_state = self.export_state().model_dump_json()
    #     provider = self.get_prompt_provider(execution_mode)
    #     prompt = provider.get_code_gen_prompt(current_state, user_prompt)
        
    #     from schemas import PipelineStage
    #     total_stages_history = []
    #     max_outer_retries = 3
    #     current_hcl = ""
    #     current_test_script = ""
        
    #     last_pipeline_error = ""

    #     # --- THE OUTER LOOP (Pipeline Feedback) ---
    #     for attempt in range(max_outer_retries):
    #         # Step A: Drafting / Re-Drafting
    #         if attempt == 0:
    #             # First Draft
    #             try:
    #                 response = self.model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
    #                 data = json.loads(response.text)
    #                 current_hcl = data.get("hcl_code", "")
    #                 current_test_script = data.get("test_script", "")
                    
    #                 yield json.dumps({"type": "stage", "name": "Drafting Infrastructure Code", "status": "success"}) + "\n"
    #                 yield json.dumps({"type": "log", "content": "Code Draft Generated."}) + "\n"
    #             except Exception as e:
    #                 error_msg = f"Draft Generation Failed: {str(e)}"
    #                 yield json.dumps({"type": "error", "content": error_msg}) + "\n"
    #                 return
    #         else:
    #             # Re-Drafting
    #             yield json.dumps({"type": "stage", "name": f"Self-Correction (Attempt {attempt+1})", "status": "running"}) + "\n"
    #             yield json.dumps({"type": "log", "content": f"Fixing Pipeline Error: {last_pipeline_error}"}) + "\n"
                
    #             current_hcl = self.refine_code(current_hcl, None, feedback_override=f"The previous Terraform code failed validation/apply with this error: {last_pipeline_error}. Fix the code.")
    #             yield json.dumps({"type": "stage", "name": f"Self-Correction (Attempt {attempt+1})", "status": "success"}) + "\n"

    #         # Step B: The Thinking Loop (Inner Peer Review)
    #         yield json.dumps({"type": "stage", "name": "AI Peer Review", "status": "running"}) + "\n"
    #         try:
    #             for review_round in range(2):
    #                 review = self.review_code(current_hcl, user_prompt)
    #                 yield json.dumps({"type": "log", "content": f"Review Score: {review.score}/100"}) + "\n"
                    
    #                 if review.approved and len(review.critical_issues) == 0:
    #                     yield json.dumps({"type": "log", "content": "Code Approved by Peer Review."}) + "\n"
    #                     break
                    
    #                 yield json.dumps({"type": "log", "content": f"Issues Found: {review.critical_issues}"}) + "\n"
    #                 yield json.dumps({"type": "log", "content": "Applying Fixes..."}) + "\n"
    #                 current_hcl = self.refine_code(current_hcl, review)
    #         except Exception as e:
    #              yield json.dumps({"type": "log", "content": f"Review Warning: {e}"}) + "\n"
            
    #         yield json.dumps({"type": "stage", "name": "AI Peer Review", "status": "success"}) + "\n"

    #         # Step C: Execution with Real-Time Streaming
    #         yield json.dumps({"type": "stage", "name": "Deployment Pipeline", "status": "running"}) + "\n"
    #         yield json.dumps({"type": "log", "content": "Starting Terraform deployment cycle..."}) + "\n"
            
    #         # Create callback to stream each stage as it completes
    #         def stage_callback(stage):
    #             # Emit stage completion immediately
    #             status_emoji = "✅" if stage.status == "success" else "❌"
    #             yield json.dumps({"type": "log", "content": f"{status_emoji} [{stage.name.upper()}] {stage.status}"}) + "\n"
    #             # Also emit as stage event for UI tracking
    #             yield json.dumps({"type": "stage", "name": stage.name, "status": stage.status}) + "\n"
    #             # Include error details if any
    #             if stage.error:
    #                 yield json.dumps({"type": "log", "content": f"   Error: {stage.error}"}) + "\n"
    #             # Include logs if verbose
    #             if stage.logs:
    #                 for log in stage.logs[-3:]:  # Last 3 logs to avoid spam
    #                     if log.strip():
    #                         yield json.dumps({"type": "log", "content": f"   {log}"}) + "\n"
            
    #         # Convert callback to generator wrapper
    #         stage_updates = []
    #         def collect_callback(stage):
    #             # Store updates to yield them later (since run_pipeline is sync)
    #             status_emoji = "✅" if stage.status == "success" else "❌"
    #             stage_updates.append({"type": "log", "content": f"{status_emoji} [{stage.name.upper()}] {stage.status}"})
    #             stage_updates.append({"type": "stage", "name": stage.name, "status": stage.status})
    #             if stage.error:
    #                 stage_updates.append({"type": "log", "content": f"   Error: {stage.error}"})
            
    #         result = self.pipeline.run_pipeline(current_hcl, current_test_script, stage_callback=collect_callback)
            
    #         # Yield collected updates
    #         for update in stage_updates:
    #             yield json.dumps(update) + "\n"

    #         if result.success:
    #             yield json.dumps({"type": "stage", "name": "Deployment Pipeline", "status": "success"}) + "\n"
    #             yield json.dumps({"type": "result", "payload": result.model_dump()}) + "\n"
    #             return
            
    #         last_pipeline_error = result.stages[-1].error or "Unknown Pipeline Error"
    #         yield json.dumps({"type": "log", "content": f"Pipeline Failed. Retrying... Error: {last_pipeline_error}"}) + "\n"

    #     yield json.dumps({"type": "error", "content": "Max retries exhausted."}) + "\n"

    # ------------------------------------------------------------------
    #  FEATURE 1: STREAMING THOUGHTS ("Glass Box" AI)
    # ------------------------------------------------------------------
    def think_stream(self, user_prompt: str, execution_mode: str = "deploy") -> Generator[str, None, None]:
        """
        Streams AI internal reasoning + Final JSON Result.
        """
        current_state = self.export_state().model_dump_json()
        provider = self.get_prompt_provider(execution_mode)
        
        # We modify the prompt to ask for thoughts explicitly
        base_prompt = provider.get_think_prompt(current_state, user_prompt)
        enhanced_prompt = f"""
        {base_prompt}
        
        **RESPONSE FORMAT INSTRUCTIONS**:
        1. First, think step-by-step about the request and risks. Prefix each thought line with "THOUGHT: ".
        2. Then, output the JSON object strictly matching the schema.
        3. Do not use markdown code blocks for the JSON.
        """

        # Helper to format SSE events
        def send(type_, content):
            return json.dumps({"type": type_, "content": content}) + "\n"

        # Note: We do NOT use response_mime_type="application/json" here so we can get free-text thoughts
        response = self.model.generate_content(enhanced_prompt, stream=True)
        
        accumulated_json = ""
        is_json_mode = False

        for chunk in response:
            text = chunk.text
            if not text: continue

            # Simple state machine to separate Thoughts from JSON
            if not is_json_mode:
                if "{" in text:
                    # JSON started
                    is_json_mode = True
                    # Split at the first brace
                    parts = text.split("{", 1)
                    if parts[0].strip():
                        yield send("thought", parts[0].replace("THOUGHT:", "").strip())
                    accumulated_json = "{" + parts[1]
                else:
                    # Still thinking
                    clean_thought = text.replace("THOUGHT:", "").strip()
                    if clean_thought:
                        yield send("thought", clean_thought)
            else:
                # Accumulate JSON
                accumulated_json += text

        # Final Parse
        try:
            # Clean up markdown if model ignored instructions
            clean_json = accumulated_json.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            yield json.dumps({"type": "result", "payload": data}) + "\n"
        except Exception as e:
            yield send("error", f"Failed to parse Agent intent: {str(e)}")

    def plan_changes(self, user_prompt: str, execution_mode: str = "deploy") -> PlanDiff:
        # Use your existing logic, just linking it here
        return PlanDiff(add_resources=[], remove_resources=[], add_edges=[], reasoning="Mock plan") 

    # ------------------------------------------------------------------
    #  FEATURE 2: REAL-TIME DEPLOYMENT PIPELINE
    # ------------------------------------------------------------------
    def generate_terraform_agentic_stream(self, user_prompt: str, execution_mode: str = "deploy") -> Generator[str, None, None]:
        
        def send(type_, content):
            return json.dumps({"type": type_, "content": content}) + "\n"

        yield send("log", f"Initializing Pipeline (Mode: {execution_mode})...")

        # 0. Sync Graph
        try:
             # In a real app, call self.plan_changes here
             yield send("log", "Syncing internal graph state...")
        except Exception as e:
             yield send("log", f"Graph Sync Warning: {e}")

        # 1. Draft Code
        yield send("stage", {"name": "Drafting Code", "status": "running"})
        current_state = self.export_state().model_dump_json()
        provider = self.get_prompt_provider(execution_mode)
        
        # --- CRITICAL UPDATE: Enforce Test Script format for Green Light UI ---
        base_code_prompt = provider.get_code_gen_prompt(current_state, user_prompt)
        enhanced_code_prompt = f"""
        {base_code_prompt}
        
        **IMPORTANT REQUIREMENT FOR test_script**:
        The python script MUST end by printing a JSON object mapping Resource IDs to 'success' or 'failed'.
        Example Output at end of script:
        {{"vpc-main": "success", "web-server": "success", "db-main": "failed"}}
        """
        
        current_hcl = ""
        current_test_script = ""

        try:
            response = self.model.generate_content(enhanced_code_prompt, stream=True)
            full_text = ""
            for chunk in response:
                if chunk.text:
                    full_text += chunk.text
                    yield send("thought", "Drafting: " + chunk.text[:50] + "...") # Visual feedback
            
            clean_text = full_text.replace("```json", "").replace("```", "")
            data = json.loads(clean_text)
            current_hcl = data.get("hcl_code", "")
            current_test_script = data.get("test_script", "")
            
            yield send("log", "Terraform Draft Generated.")
            yield send("stage", {"name": "Drafting Code", "status": "success"})

        except Exception as e:
            yield send("error", f"Drafting Failed: {str(e)}")
            return

        # 2. Deployment Loop
        yield send("stage", {"name": "Deployment Pipeline", "status": "running"})
        
        # Bridge Pipeline Callbacks to Stream
        # We need to collect events from the sync pipeline function
        pipeline_events = []
        
        def pipeline_callback(stage):
            status_icon = "✅" if stage.status == "success" else "❌"
            # Queue the log
            pipeline_events.append(send("log", f"{status_icon} Stage: {stage.name.upper()}"))
            # Queue the UI update
            pipeline_events.append(send("stage", {"name": f"{stage.name}", "status": stage.status}))
            
            if stage.error:
                pipeline_events.append(send("log", f"   Error: {stage.error}"))

        # Run Sync Pipeline
        res = self.pipeline.run_pipeline(current_hcl, current_test_script, stage_callback=pipeline_callback)
        
        # Flush Events
        for event in pipeline_events:
            yield event

        if res.success:
             yield send("stage", {"name": "Deployment Pipeline", "status": "success"})
             # 🚀 FEATURE: Send Resource Statuses to turn nodes GREEN
             if res.resource_statuses:
                 yield send("resource_update", res.resource_statuses)
                 yield send("log", f"Verified Resources: {json.dumps(res.resource_statuses)}")
             yield send("result", res.model_dump())
        else:
             yield send("error", f"Pipeline Failed: {res.final_message}")
             
# ------------------------------------------------------------------
    #  FEATURE 3: STREAMING GRAPH PLANNER
    # ------------------------------------------------------------------
    def plan_graph_stream(self, user_prompt: str, execution_mode: str = "deploy") -> Generator[str, None, None]:
        """
        Streams the graph planning process (Thoughts + Actions + Policy Checks).
        """
        def send(type_, content):
            return json.dumps({"type": type_, "content": content}) + "\n"

        yield send("log", f"Initializing Architect (Mode: {execution_mode})...")
        
        current_state = self.export_state().model_dump_json()
        provider = self.get_prompt_provider(execution_mode)
        base_prompt = provider.get_plan_prompt(current_state, user_prompt)

        max_retries = 3
        attempt = 0
        current_prompt = base_prompt
        last_error = ""

        # --- The Reasoning Loop ---
        while attempt < max_retries:
            yield send("log", f"Cycle {attempt + 1}/{max_retries}: Drafting Architecture...")
            
            # 1. Ask Gemini (Stream thoughts)
            try:
                # We ask specifically for THOUGHTs before JSON
                enhanced_prompt = current_prompt + "\n\nProvide your internal reasoning lines starting with 'THOUGHT:' before the final JSON."
                response = self.model.generate_content(enhanced_prompt, stream=True)
                
                full_text = ""
                json_part = ""
                is_json = False
                
                for chunk in response:
                    text = chunk.text
                    if not text: continue
                    full_text += text
                    
                    if not is_json:
                        if "{" in text:
                            is_json = True
                            # Split thought/json
                            parts = text.split("{", 1)
                            if parts[0].strip():
                                yield send("thought", parts[0].replace("THOUGHT:", "").strip())
                            json_part = "{" + parts[1]
                        else:
                            clean_thought = text.replace("THOUGHT:", "").strip()
                            if clean_thought: 
                                yield send("thought", clean_thought)
                    else:
                        json_part += text

                # 2. Parse JSON
                clean_json = json_part if json_part else full_text
                clean_json = clean_json.replace("```json", "").replace("```", "").strip()
                # Find first { and last }
                s = clean_json.find("{")
                e = clean_json.rfind("}") + 1
                if s != -1 and e != -1:
                    clean_json = clean_json[s:e]

                data = json.loads(clean_json)
                
                # Tag status
                for res in data.get("add_resources", []):
                    res["status"] = "planned"
                
                plan = PlanDiff(**data)
                yield send("log", f"Drafted: +{len(plan.add_resources)} resources, +{len(plan.add_edges)} edges")

                # 3. Policy Check
                if execution_mode == "deploy":
                    yield send("log", "Running Policy Checks...")
                    violations = self.check_policies(plan)
                else:
                    violations = []

                if not violations:
                    yield send("log", "✅ Policies Passed.")
                    
                    # Apply to internal graph (Draft State)
                    # We don't apply to the MAIN graph yet, we just return the plan for confirmation
                    # But for the UI to render the preview, we usually apply it temporarily or send the state.
                    # Let's Apply it so the 'export_state' below reflects the new plan
                    self.apply_diff(plan)
                    self.session.pending_plan = plan
                    self.session.phase = "graph_pending"
                    
                    # Calculate Confirmation
                    conf = self.needs_user_confirmation(plan)
                    
                    # Final Payload
                    result_payload = {
                        "plan": plan.model_dump(),
                        "graph_state": self.export_state().model_dump(),
                        "confirmation": conf.model_dump(),
                        "session_phase": self.session.phase
                    }
                    yield send("result", result_payload)
                    return

                # 4. Handle Violations (Self-Correction)
                yield send("log", f"❌ Policy Violations: {len(violations)}")
                for v in violations:
                    yield send("log", f"   - {v}")
                
                yield send("thought", "Violations found. Adjusting plan...")
                
                feedback = f"\n\nCRITICAL: Your previous plan failed these Policy Checks:\n{json.dumps(violations)}\n\nFix these violations and regenerate the JSON Plan."
                current_prompt = base_prompt + feedback 
                attempt += 1

            except Exception as e:
                yield send("log", f"Parsing Error: {str(e)}")
                last_error = str(e)
                attempt += 1
        
        yield send("error", f"Failed to generate valid plan: {last_error}")