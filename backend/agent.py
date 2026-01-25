import networkx as nx
import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
from typing import List, Dict
from schemas import GraphState, Resource, Edge, PlanDiff, IntentAnalysis, BlastAnalysis

load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class InfraAgent:
    def __init__(self):
        self.graph = nx.DiGraph()
        # Seed with some initial data for visualization
        self.graph.add_node("vpc-main", id="vpc-main", type="aws_vpc", properties={"cidr": "10.0.0.0/16"}, status="active")
        self.graph.add_node("subnet-public", id="subnet-public", type="aws_subnet", properties={"cidr": "10.0.1.0/24"}, status="active")
        self.graph.add_edge("vpc-main", "subnet-public", relation="contains")
        
        self.model = genai.GenerativeModel('gemini-2.5-pro')

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
                                violations.append(f"Security Policy Violation: SG '{res.id}' allows SSH (22) from the entire internet. Limit CIDR.")
        
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
        - AWS Resources only (aws_vpc, aws_subnet, aws_instance, aws_security_group, aws_db_instance, aws_lb).
        - Edge Direction is STRICT: Parent -> Child.
        - Example: VPC -> Subnet -> Instance. 
        - Example: ALB -> Target Group -> Instance.
        - NEVER do Instance -> Subnet.
        - If deleting, be precise with IDs.
        
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
