def get_vision_prompt() -> str:
    return """
    You are an Expert Cloud Architect with advanced Spatial Reasoning.
    
    Task: Convert the Whiteboard Sketch into a Hierarchical Intent Graph.
    
    --- THOUGHT PROCESS (Output this first) ---
    1. **Identify Containers**: Only create container nodes for **Infrastructure Boundaries** (VPC, Subnets, Security Groups).
       - **IGNORE** logical/conceptual groupings (e.g., "User Layer", "Data Tier", "Legend"). Do NOT create nodes for these.
    2. **Identify Components**: Look for icons inside those boxes.
    3. **Establish Hierarchy**: If 'Web-Server' is inside 'Public-Subnet', its `parent_id` is 'Public-Subnet'.

    --- OUTPUT JSON FORMAT ---
    {
        "thoughts": "I see a large box labeled 'VPC' containing two smaller boxes...",
        "graph_phase": "intent",
        "add_resources": [
            { 
                "id": "vpc-main", 
                "type": "network_container", 
                "properties": { "label": "VPC" } 
            },
            { 
                "id": "subnet-public", 
                "type": "network_zone", 
                "parent_id": "vpc-main",  <-- CRITICAL: Linking to parent
                "properties": { "label": "Public Subnet" },
                "status": "proposed"
            },
            { 
                "id": "web-server", 
                "type": "compute_service", 
                "parent_id": "subnet-public", <-- CRITICAL: Linking to parent
                "properties": { "label": "EC2" },
                "status": "proposed"
            }
        ],
        "add_edges": [] 
    }
    
    Rule: Only use 'connects_to' edges for logical connections (arrows). Do NOT use edges for containment (parent_id handles that).
    """
