
import os
import sys
# Mock API Key if missing (but it should be in .env)
# os.environ["GEMINI_API_KEY"] = "test"

try:
    print("Importing Agent...")
    from agent import InfraAgent
    
    print("Instantiating Agent...")
    agent = InfraAgent()
    
    print("Calling stream_terraform_gen...")
    gen = agent.stream_terraform_gen("test", "deploy")
    
    print("Iterating Generator...")
    for chunk in gen:
        print(f"CHUNK: {chunk.strip()}")
        
    print("Done.")
except Exception as e:
    print("CRASHED!")
    import traceback
    traceback.print_exc()
