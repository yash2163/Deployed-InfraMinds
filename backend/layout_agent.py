import json
from google import genai
from google.genai import types
import os

def get_layout_prompt(graph_state):
    # Pre-process graph to count node types for context hints if needed
    # But for now, we trust the LLM to filter.
    
    return f"""
    You are a Senior AWS Solutions Architect & Data Visualization Expert.
    Task: specific 'x', 'y', 'width', 'height', 'parentId', and 'hidden' status for every node to create a Presentation-Quality Architecture Diagram.

    Input Graph: {json.dumps(graph_state, indent=2)}

    --- 1. FILTERING RULES (CRITICAL) ---
    **VISUAL NOISE REDUCTION:** A professional diagram DOES NOT show low-level config resources.
    - **Mark as "hidden": true** for: 
      `aws_security_group_rule`, `aws_route_table_association`, `aws_iam_policy`, `aws_iam_role_policy`, `aws_network_acl`, `aws_network_acl_rule`.
    - **Keep Visible:** VPC, Subnets, Instances, Balancers, Databases, Buckets, CloudFront, Gateways, Endpoints.

    --- 2. ZONING STRATEGY (The "Layer Cake") ---
    Imagine a canvas of 2000x1500. Use a **Grid System**.
    
    **ZONE A: THE EDGE (Top: Y=0 to Y=150)**
    - Place `aws_cloudfront_distribution`, `aws_route53_zone`, `aws_waf_web_acl` here.
    - Center them horizontally.

    **ZONE B: THE VPC CONTAINER (Middle: Y=200)**
    - Draw a large container for `aws_vpc` (e.g., Width: 1200, Height: 1000, X: 400).
    
    **ZONE C: SUBNET TIERS (Inside VPC)**
    - **Tier 1 (Public):** Top of VPC. Place `aws_nat_gateway`, `aws_internet_gateway`, `aws_lb` (ALB/NLB).
    - **Tier 2 (Compute):** Middle of VPC. Place `aws_ecs_service`, `aws_instance`, `aws_lambda_function`.
    - **Tier 3 (Data):** Bottom of VPC. Place `aws_rds_cluster`, `aws_elasticache_cluster`, `aws_dynamodb_table`.
    
    --- 3. ALIGNMENT RULES ---
    - **Subnets:** Make them wide horizontal bands spanning the VPC width.
    - **Resources:** Place them INSIDE their respective Subnet/VPC parent.
    - **Security Groups:** Place them visibly NEAR the resource they protect (e.g., +50px X, +50px Y relative to the resource), OR hide them if they clutter the view.

    --- OUTPUT FORMAT ---
    Return ONLY JSON. All coordinates must be integers.
    {{
      "node-id": {{ "x": 100, "y": 100, "width": 180, "height": 60, "parentId": "parent-id", "hidden": false }}
    }}
    """

async def generate_layout_plan(graph_state: dict):
    # 1. INITIALIZE CLIENT
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    
    # 2. PREPARE DATA
    simplified_graph = {
        "resources": [
            {"id": r["id"], "type": r["type"], "parent_id": r.get("parent_id")} 
            for r in graph_state.get("resources", [])
        ]
    }

    prompt = get_layout_prompt(simplified_graph)
    
    # 3. CALL GEMINI (ASYNC)
    # Use 'client.aio' to access the async version of the model
    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            )
        )
        
        text = response.text
        if not text:
            print("Layout generation returned empty response (safety block?)")
            return {}
        
        # 4. CLEAN & PARSE
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
            
        layout_map = json.loads(text.strip())
        return layout_map

    except Exception as e:
        print(f"Error parsing layout response: {e}")
        # print(f"Raw response: {response.text}") # Be careful logging raw objects if they fail
        return {}