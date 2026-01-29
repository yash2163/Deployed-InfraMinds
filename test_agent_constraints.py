import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from backend.agent import InfraAgent

agent = InfraAgent()

print("--- Testing Agent Logic (Free Tier Constraints) ---")
print("User Request: 'Add an Application Load Balancer for High Availability'")

# Mocking a simple existing state if needed, or just relying on empty/current state
# agent.graph.add_node("web", type="aws_instance", id="web-1") 

plan = agent.plan_changes("Add an Application Load Balancer for High Availability")

print("\n--- Plan Result ---")
print(f"Added Resources: {[r.type for r in plan.add_resources]}")
print(f"Reasoning: {plan.reasoning}")

# Check if prohibited resources are present
prohibited = ["aws_lb", "aws_lb_target_group", "aws_lb_listener"]
found_prohibited = [r.type for r in plan.add_resources if r.type in prohibited]

if found_prohibited:
    print(f"\n❌ FAIL: Agent proposed prohibited resources: {found_prohibited}")
    sys.exit(1)
elif "not supported" in plan.reasoning.lower() or "free tier" in plan.reasoning.lower():
    print(f"\n✅ PASS: Agent correctly avoided ALB and explained why.")
    sys.exit(0)
else:
    print(f"\n⚠️ WARNING: Agent avoided ALB but reasoning might be unclear. Please review.")
    sys.exit(0)
