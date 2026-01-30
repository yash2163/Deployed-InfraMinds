
import asyncio
import os
import sys
import logging
from agent import InfraAgent
from pipeline import PipelineManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_streaming_flow():
    """
    Simulates the full agent flow:
    1. Plan Graph
    2. Generate Code (checking for provider errors)
    3. Run Pipeline (Validate -> Plan -> Apply -> Verify)
    """
    
    # 1. Setup
    print("--- 1. Initializing Agent ---")
    agent = InfraAgent()
    
    # Sample Request
    user_prompt = "Create an EC2 instance connected to an S3 bucket in us-east-1."
    print(f"User Request: {user_prompt}")
    
    print("\n--- 2. Planning Graph ---")
    # We'll just skip the streaming part for the graph and assume a valid graph state
    # But to be thorough, let's run the actual generation method if possible, or just mock the state
    # For speed, let's call the actual method but consume the stream
    
    print("Generating Plan...")
    plan_stream = agent.plan_graph_stream(user_prompt)
    for chunk in plan_stream:
        # Just consume
        pass
        
    print("Plan Generated. Current Graph State nodes:", agent.graph.number_of_nodes())
    
    # 3. Deployment (The Critical Part)
    print("\n--- 3. Deploying (Generating Terraform & Running Pipeline) ---")
    deploy_stream = agent.generate_terraform_agentic_stream(user_prompt)
    
    generated_hcl = ""
    pipeline_success = False
    
    try:
        for chunk in deploy_stream:
            # content is a JSON string because 'send' wraps it
            # We need to parse it to see clean logs
            import json
            if chunk.strip():
                try:
                    data = json.loads(chunk)
                    type_ = data.get("type")
                    content = data.get("content")
                    
                    if type_ == "log":
                        print(f"[LOG] {content}")
                    elif type_ == "error":
                        print(f"❌ [ERROR] {content}")
                    elif type_ == "result":
                        print("✅ [RESULT] Pipeline Finished Successfully")
                        pipeline_success = True
                    elif type_ == "stage":
                        print(f"ℹ️ [STAGE] {content['name']}: {content['status']}")
                        
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        print(f"❌ Exception during stream: {e}")
        
    # 4. Verify Generated Code (Post-Mortem)
    print("\n--- 4. Post-Execution Code verification ---")
    workspace = "/tmp/infra_minds_workspace"
    main_tf = os.path.join(workspace, "main.tf")
    
    if os.path.exists(main_tf):
        with open(main_tf, "r") as f:
            code = f.read()
            
        print(f"Checking {main_tf} for forbidden arguments...")
        errors = []
        if "s3_force_path_style" in code:
            errors.append("❌ FAIL: Found 's3_force_path_style'")
        if "s3_use_path_style" in code:
            errors.append("❌ FAIL: Found 's3_use_path_style'")
            
        if not errors:
            print("✅ SUCCESS: No deprecated arguments found in main.tf")
        else:
            for e in errors:
                print(e)
    else:
        print("❌ FAIL: main.tf was not found!")

    if pipeline_success:
        print("\n✅ VERIFICATION COMPLETE: The entire flow passed.")
    else:
        print("\n❌ VERIFICATION FAILED: The pipeline did not complete successfully.")

if __name__ == "__main__":
    if os.path.exists(".env"):
        from dotenv import load_dotenv
        load_dotenv()
    
    # Run the async test
    asyncio.run(test_streaming_flow())
