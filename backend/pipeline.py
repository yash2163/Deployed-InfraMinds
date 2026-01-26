import os
import subprocess
import json
import time
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel

# Configuration for Simulation Mode
# If True, bypasses real CLI calls and uses mocked responses/errors
# Set to False to run actual 'terraform' and 'localstack' commands
SIMULATION_MODE = True

from schemas import PipelineResult, PipelineStage

# Configuration for Simulation Mode
# If True, bypassed real CLI calls and uses mocked responses/errors
# Set to False to run actual 'terraform' and 'localstack' commands
SIMULATION_MODE = True


class PipelineManager:
    def __init__(self, agent_model, work_dir: str = "/tmp/infra_minds_workspace"):
        self.agent_model = agent_model
        # Use absolute path in /tmp to avoid triggering uvicorn reload
        self.work_dir = os.path.abspath(work_dir)
        
        if not os.path.exists(self.work_dir):
            os.makedirs(self.work_dir)

    def run_pipeline(self, hcl_code: str, test_script: str) -> PipelineResult:
        """
        Executes the 5-stage Self-Healing Pipeline.
        """
        stages_history = []
        current_hcl = hcl_code
        max_retries = 3
        
        # --- Stage 1: Setup ---
        self._write_files(current_hcl, test_script)
        
        # --- Retry Loop for Validation/Plan/Apply ---
        for attempt in range(max_retries):
            # 1. Validate
            val_stage = self._run_stage("validate", current_hcl)
            stages_history.append(val_stage)
            if val_stage.status == "failed":
                print(f"Attempt {attempt+1}: Validation Failed. Fixing...")
                current_hcl = self._fix_code(current_hcl, val_stage.error, "terraform validate")
                self._write_files(current_hcl, test_script)
                continue # Retry loop

            # 2. Plan (Mocked logic for now in simulation, real otherwise)
            plan_stage = self._run_stage("plan", current_hcl)
            stages_history.append(plan_stage)
            if plan_stage.status == "failed":
                current_hcl = self._fix_code(current_hcl, plan_stage.error, "terraform plan")
                self._write_files(current_hcl, test_script)
                continue

            # 3. Apply
            apply_stage = self._run_stage("apply", current_hcl)
            stages_history.append(apply_stage)
            if apply_stage.status == "failed":
                current_hcl = self._fix_code(current_hcl, apply_stage.error, "terraform apply")
                self._write_files(current_hcl, test_script)
                continue
                
            # 4. Verify (Test Script)
            verify_stage = self._run_stage("verify", test_script, is_python=True)
            stages_history.append(verify_stage)
            if verify_stage.status == "success":
                return PipelineResult(
                    success=True,
                    hcl_code=current_hcl,
                    stages=stages_history,
                    final_message="Infrastructure Deployed and Verified Successfully!"
                )
            else:
                # Verification failed (runtime logic error?)
                # In a real scenario, we might also feed this back. 
                # For this demo, we'll mark as partial success or fail.
                return PipelineResult(
                    success=False,
                    hcl_code=current_hcl,
                    stages=stages_history,
                    final_message="Deployment succeeded, but Verification script failed."
                )

        return PipelineResult(
            success=False,
            hcl_code=current_hcl,
            stages=stages_history,
            final_message="Pipeline failed after maximum retries."
        )

    def _run_stage(self, stage_name: str, content: str, is_python: bool = False) -> PipelineStage:
        """
        Runs a command (real or simulated) and returns the stage result.
        """
        logs = [f"Starting {stage_name}..."]
        
        if SIMULATION_MODE:
            return self._simulate_execution(stage_name, content)
        
        # REAL EXECUTION
        cmd = []
        if stage_name == "validate":
            cmd = ["terraform", "validate"]
        elif stage_name == "plan":
            cmd = ["tflocal", "plan"]
        elif stage_name == "apply":
            cmd = ["tflocal", "apply", "-auto-approve"]
        elif stage_name == "verify":
            cmd = ["python3", "test_infra.py"]
        
        try:
            # Init if needed
            if stage_name == "validate" and not os.path.exists(os.path.join(self.work_dir, ".terraform")):
                 subprocess.run(["tflocal", "init"], cwd=self.work_dir, capture_output=True)

            result = subprocess.run(
                cmd, 
                cwd=self.work_dir, 
                capture_output=True, 
                text=True,
                timeout=120
            )
            
            logs.append(result.stdout)
            if result.returncode == 0:
                logs.append(f"{stage_name} passed.")
                return PipelineStage(name=stage_name, status="success", logs=logs)
            else:
                logs.append(f"ERROR: {result.stderr}")
                return PipelineStage(name=stage_name, status="failed", logs=logs, error=result.stderr)
                
        except Exception as e:
            return PipelineStage(name=stage_name, status="failed", logs=logs, error=str(e))

    def _simulate_execution(self, stage_name: str, content: str) -> PipelineStage:
        """
        Simulates errors for the demo to show off self-correction.
        """
        time.sleep(1.5) # Fake latency
        
        # Simulation Scenario:
        # 1. First 'validate' call fails with a syntax error (if we want to force a fix).
        #    BUT, since we want to show the agent *reacting*, we can randomly fail 
        #    OR check if the content contains a specific "bug" trigger.
        #    For now, let's make it deterministic based on a global counter or content hash?
        #    Let's keep it simple: The *first* time we run this method, it fails.
        
        # Actually, simpler: The Agent GENERATED the code. If the code is perfect, it passes.
        # If we want to force the demo, we should inject a bug in the *Draft* stage.
        
        # For now, let's assume 'validate' passes, 'plan' passes.
        # 'verify' might fail if we want.
        
        if "simulated_error" in content:
             return PipelineStage(
                name=stage_name, 
                status="failed", 
                logs=["Simulating failure..."], 
                error="Error: invalid resource type 'aws_s3_bucket_fake' on line 12."
            )

        return PipelineStage(name=stage_name, status="success", logs=[f"Simulated {stage_name} output... OK."])

    def _fix_code(self, code: str, error: str, context: str) -> str:
        """
        Uses Gemini to fix the code based on the error message.
        """
        prompt = f"""
        You are an expert Terraform Debugger.
        
        CONTEXT: Running '{context}'
        USER CODE:
        ```hcl
        {code}
        ```
        
        ERROR OUTPUT:
        {error}
        
        TASK:
        1. Analyze the error.
        2. Fix the HCL code to resolve the error.
        3. Return ONLY the fixed HCL code. No markdown formatting, just the code.
        """
        
        response = self.agent_model.generate_content(prompt)
        fixed_code = response.text.replace("```hcl", "").replace("```", "").strip()
        return fixed_code

    def _write_files(self, hcl: str, python: str):
        with open(os.path.join(self.work_dir, "main.tf"), "w") as f:
            f.write(hcl)
        with open(os.path.join(self.work_dir, "test_infra.py"), "w") as f:
            f.write(python)
