import networkx as nx
import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
from typing import List, Dict
from schemas import GraphState, Resource, Edge, PlanDiff, IntentAnalysis, BlastAnalysis, CodeReview, ConfirmationRequired, ConfirmationReason, SessionState

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

    def think(self, user_prompt: str) -> IntentAnalysis:
        """
        Analyzes the user's intent and generates a high-level plan.
        """
        current_state = self.export_state().model_dump_json()
        
        prompt = f"""
        You are InfraMinds, an Autonomous Cloud Architect.
        
        Current Infrastructure State (JSON):
        {current_state}
        
        User Request: "{user_prompt}"
        
        Task:
        1. Analyze the user's intent.
        2. Identify if this is a "Safe Query" or a "Mutation" (change).
        3. If it's a mutation, identify potential Risks (Blast Radius).
        4. Suggest specific actions (e.g., "Add RD", "Delete VPC").
        
        Output purely in JSON matching this schema:
        {{
            "summary": "Brief summary of what the user wants.",
            "risks": ["Risk 1", "Risk 2"],
            "suggested_actions": ["Action 1", "Action 2"]
        }}
        """
        
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

    def plan_changes(self, user_prompt: str) -> PlanDiff:
        """
        Generates the concrete graph changes (Diff) with AUTO-CORRECTION.
        """
        current_state = self.export_state().model_dump_json()
        
        base_prompt = f"""
        You are InfraMinds. Generate the specific graph changes to fulfill the user request.
        
        Current State:
        {current_state}
        
        User Request: "{user_prompt}"
        
        Rules:
        - AWS Resources only:
          - Networking: aws_vpc, aws_subnet, aws_internet_gateway, aws_nat_gateway, aws_eip, aws_route_table, aws_route_table_association
          - Compute: aws_instance, aws_launch_template, aws_autoscaling_group
          - Database: aws_db_instance, aws_db_subnet_group
          - Load Balancing: aws_lb, aws_lb_target_group, aws_lb_listener
          - Security: aws_security_group, aws_security_group_rule
        - Edge Direction is STRICT: Parent -> Child.
        - Example: VPC -> Subnet -> Instance. 
        - Example: ALB -> Target Group -> Instance OR ASG.
        - Example: Launch Template -> ASG.
        - Example: ALB -> Target Group -> Instance.
        - NEVER do Instance -> Subnet.
        - If deleting, be precise with IDs.
        
        Security Constraints (CRITICAL):
        - DO NOT allow Open SSH (Port 22) from 0.0.0.0/0. This is a Policy Violation.
        - For "Public Access", use HTTP (80) or HTTPS (443).
        - For "Public Access", use HTTP (80) or HTTPS (443).
        - If SSH is needed, restrict to a specific IP or omit ingress.
        
        Cardinality Rules (CRITICAL):
        - STRICTLY follow the user's requested quantity.
        - If user says "an instance" or "a database", generate EXACTLY ONE.
        - Do NOT assume High Availability (2+ instances) unless explicitly requested.
        - If user explicitly requests "High Availability", "HA", or "Production", default to Multi-AZ resources (2 subnets per tier, 1 NAT Gateway PER AZ for redundancy).
        - Do NOT generate duplicate resources with different suffixes (e.g. web_1, web_2) unless asked.
        
        Output JSON matching PlanDiff schema:
        {{
            "add_resources": [ {{ "id": "...", "type": "...", "properties": {{...}} }} ],
            "remove_resources": ["id1", "id2"],
            "add_edges": [ {{ "source": "...", "target": "...", "relation": "..." }} ],
            "remove_edges": [],
            "reasoning": "Explanation of changes..."
        }}
        """
        
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
                
                # Verify
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

    def generate_terraform_agentic(self, user_prompt: str) -> PipelineResult:
        """
        Stage 1 (Draft): Generates HCL + Python Test Script.
        IMPROVED: Recursive Self-Healing (Think -> Critque -> Refine -> Test -> Retry).
        """
        # 0. Sync Graph State (Best Effort)
        try:
             plan = self.plan_changes(user_prompt)
             if not plan.logs or not any("FAILED" in log for log in plan.logs):
                 self.apply_diff(plan)
        except Exception as e:
             print(f"CRITICAL GRAPH SYNC ERROR: {e}")
             import traceback
             traceback.print_exc()

        # 1. Draft Code using current state context
        current_state = self.export_state().model_dump_json()
        
        prompt = f"""
        You are a Senior DevOps Engineer. 
        Task: Write Terraform HCL code and a Python Verification Script.
        
        --- INPUTS ---
        1. User Request: "{user_prompt}"
        2. Graph State (Current Blueprint): 
        {current_state}
        
        --- CRITICAL INSTRUCTIONS ---
        1. **Gap Filling:** The Graph State might be incomplete or stale. **TRUST THE USER REQUEST ABOVE ALL.**
        2. If the user asked for "EC2" and "DB" but the Graph only has "VPC", **YOU MUST GENERATE THE EC2 AND DB HCL**.
        3. **Completeness:** Ensure all necessary "glue" is present:
           - Security Groups must have ingress/egress rules.
           - **CRITICAL:** Terraform Security Groups typically strip default Egress. You MUST explicitly add an `egress` block allowing all traffic (`0.0.0.0/0`, protocol "-1") unless restricted.
           - Instances must be attached to Subnets.
           - DBs must have Subnet Groups.
        4. **Refinement:** If the Graph shows a 'connects_to' edge between Web and DB, implement this as a Security Group Rule allowing traffic on port 3306.
        5. **HA Support**: Use `aws_lb`, `aws_launch_template`, `aws_autoscaling_group` if requested.
        6. **Secrets**: NEVER hardcode passwords. Use `variable` with `sensitive = true` or `random_password` resource. If you verify a hardcoded password like "please_change_this_password", you MUST fix it to use a variable.
        7. **Cardinality**: STRICTLY follow the user's requested quantity. If "an instance", generate ONE. Do not assume HA.
        8. **RDS Multi-AZ**: `aws_db_subnet_group` MUST reference subnets in at least TWO different AZs. Create a new private subnet in a different AZ if needed.
        9. **Web Servers**: If the user asks for a web server, you MUST include `user_data` (base64 encoded if needed, or raw heredoc) to install Apache/Nginx.
        10. **ASG Health Check**: If ASG is attached to an LB, set `health_check_type = "ELB"`.
        11. **HA Networking**: If requesting "High Availability", ensure you create 1 NAT Gateway PER Availability Zone (e.g. nat_a in us-east-1a, nat_b in us-east-1b) and separate Route Tables for each private subnet. Avoid Single Points of Failure.
        
        --- OUTPUT REQUIREMENTS ---
        Return JSON with:
        - "hcl_code": The complete main.tf content. Use AWS provider.
        - "test_script": A python script using boto3 (endpoint_url='http://localhost:4566') to verify resources exist.
        """
        
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
        return PipelineResult(
            success=False,
            hcl_code=current_hcl,
            stages=total_stages_history,
            final_message=f"Failed after {max_outer_retries} recursive attempts."
        )