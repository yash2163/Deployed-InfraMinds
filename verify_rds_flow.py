import requests
import json
import time

API_URL = "http://localhost:8000"

def run_verification():
    print("--- Starting RDS Multi-AZ & Confirmation Flow Verification ---")
    
    # 1. Reset Graph
    print("\n1. Resetting Graph...")
    requests.post(f"{API_URL}/graph/reset")
    
    # 2. Request RDS (which requires Multi-AZ)
    # maximizing the chance it needs to fixing by specifically asking for subnets in one AZ
    prompt = "Create a VPC and a public subnet in us-east-1a. Then add an RDS MySQL database."
    print(f"\n2. Sending Prompt: '{prompt}'")
    
    resp = requests.post(f"{API_URL}/agent/plan_graph", json={"prompt": prompt})
    if resp.status_code != 200:
        print(f"FAILED: /agent/plan_graph returned {resp.status_code}")
        print(resp.text)
        return
        
    data = resp.json()
    plan = data.get("plan", {})
    confirmation = data.get("confirmation", {})
    
    print("\n3. Analyzing Graph Plan...")
    # Check if a second subnet was planned? 
    # The agent might add it in the graph plan OR in the code generation phase.
    # My instructions were in BOTH. Ideally it appears in the graph.
    
    added_resources = plan.get("add_resources", [])
    subnets = [r for r in added_resources if r["type"] == "aws_subnet"]
    print(f"Planned Subnets: {len(subnets)}")
    for s in subnets:
        print(f" - {s['id']}: {s.get('properties', {}).get('availability_zone', 'Unknown AZ')}")
        
    if confirmation.get("required"):
        print(f"\nConfirmation Required: {confirmation.get('reasons')}")
    else:
        print("\nNo Confirmation Required (Unexpected for RDS/NAT)")

    # 3. Confirm Graph (Stage 1)
    print("\n4. Confirming Graph (Stage 1)...")
    resp = requests.post(f"{API_URL}/agent/deploy", json={"prompt": "CONFIRM"})
    if resp.status_code != 200:
        print(f"FAILED: /agent/deploy (Graph) returned {resp.status_code}")
        return

    data = resp.json()
    phase = data.get("session_phase")
    print(f"Session Phase: {phase}")
    
    if phase != "code_pending":
        print("FAILED: Expected phase 'code_pending'")
        return
        
    hcl = data.get("hcl_code", "")
    print(f"\nGenerated Terraform Code Length: {len(hcl)} chars")
    
    # 4. Verify Code Content (Stage 2)
    print("\n5. Verifying Terraform Content for RDS Multi-AZ...")
    
    if "aws_db_subnet_group" not in hcl:
        print("FAILED: No aws_db_subnet_group found in HCL")
    else:
        print("SUCCESS: aws_db_subnet_group found.")
        
    # Check if we have subnets in different AZs in the code
    # This is a heuristic check
    if 'availability_zone = "us-east-1b"' in hcl or 'availability_zone = "us-east-1c"' in hcl:
         print("SUCCESS: Found reference to second AZ (us-east-1b/c) in HCL.")
    else:
         print("WARNING: Did not explicitly see 'us-east-1b' in HCL. Check if logic worked.")
         print(hcl)

    # 5. Confirm Code (Stage 3 - Deploy)
    # We won't actually deploy to avoid LocalStack overhead if not running, 
    # but we can check if endpoint accepts it.
    print("\n6. Confirming Code (Stage 3)...")
    # resp = requests.post(f"{API_URL}/agent/deploy", json={"prompt": "CONFIRM"})
    # print(f"Deployment Response: {resp.status_code}")

if __name__ == "__main__":
    run_verification()
