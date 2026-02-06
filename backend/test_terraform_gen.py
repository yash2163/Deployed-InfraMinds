#!/usr/bin/env python3
"""
Debug script to test terraform generation in isolation
"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

from agent import InfraAgent

print("Initializing agent...")
agent = InfraAgent()

# Load the current implementation graph
print(f"Implementation graph exists: {agent.implementation_graph is not None}")
if agent.implementation_graph:
    print(f"  Resources: {len(agent.implementation_graph.resources)}")
    print(f"  Graph phase: {agent.implementation_graph.graph_phase}")
    
    # Check the size of the serialized graph
    state_json = agent.implementation_graph.model_dump_json()
    print(f"  Serialized size: {len(state_json)} characters")
    print(f"  Estimated tokens: ~{len(state_json) // 4}")  # Rough estimate
    
    # Try to generate terraform
    print("\nAttempting terraform generation...")
    try:
        gen = agent.stream_terraform_gen("test", "deploy")
        for i, chunk in enumerate(gen):
            print(f"Chunk {i}: {chunk[:100]}...")
            if i > 5:  # Stop after a few chunks
                print("(stopping after 5 chunks)")
                break
        print("SUCCESS!")
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
else:
    print("No implementation graph found. Try running /agent/approve first.")
