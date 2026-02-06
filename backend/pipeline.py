import os
import subprocess
import json
import time
from typing import Dict, List, Optional, Tuple, Callable
from pydantic import BaseModel
from schemas import PipelineResult, PipelineStage

# Configuration
SIMULATION_MODE = False

class PipelineManager:
    def __init__(self, agent_client, model_name: str, work_dir: str = "/tmp/infra_minds_workspace"):
        self.agent_client = agent_client
        self.model_name = model_name
        self.work_dir = os.path.abspath(work_dir)
        if not os.path.exists(self.work_dir):
            os.makedirs(self.work_dir)

    def run_pipeline(self, hcl_code: str, test_script: str, execution_mode: str = "deploy", simulate_apply: bool = False, stage_callback: Callable[[PipelineStage], None] = None) -> PipelineResult:
        """
        Executes the 5-stage Self-Healing Pipeline.
        stage_callback: Function called after each stage completes.
        """
        stages_history = []
        current_hcl = hcl_code
        max_retries = 3
        
        # --- Stage 1: Setup ---
        self._write_files(current_hcl, test_script)
        
        # --- Retry Loop ---
        for attempt in range(max_retries):
            # 1. Validate
            val_stage = self._run_stage("validate", current_hcl)
            stages_history.append(val_stage)
            if stage_callback: stage_callback(val_stage)
            
            if val_stage.status == "failed":
                if stage_callback:
                    stage_callback(PipelineStage(name="Self-Correction", status="fixing", logs=[f"⚠️ Validation Failed. Agent is analyzing error and patching code..."]))
                current_hcl = self._fix_code(current_hcl, val_stage.error, "terraform validate", callback=stage_callback)
                self._write_files(current_hcl, test_script)
                continue 

            # --- DRAFT MODE: STOP AFTER VALIDATE ---
            if execution_mode == "draft":
                # Validation passed - now simulate the rest
                if not simulate_apply:
                     return PipelineResult(
                        success=True,
                        hcl_code=current_hcl,
                        stages=stages_history,
                        final_message="Draft Validation Complete. (Stopped before Plan)",
                        resource_statuses={}
                    )
                else:
                    # SIMULATE PLAN, APPLY & VERIFY (Fake logs for demo)
                    # 2. Simulated Plan
                    sim_plan = self._simulate_execution("plan", current_hcl, stage_callback)
                    stages_history.append(sim_plan)
                    # Callback already handled inside _simulate_execution if passed
                    
                    # 3. Simulated Apply
                    sim_apply = self._simulate_execution("apply", current_hcl, stage_callback)
                    stages_history.append(sim_apply)
                    
                    # 4. Simulated Verify
                    sim_verify = self._simulate_execution("verify", current_hcl, stage_callback)
                    stages_history.append(sim_verify)
                    
                    return PipelineResult(
                        success=True,
                        hcl_code=current_hcl,
                        stages=stages_history,
                        final_message="Draft Deployment Simulated Successfully!",
                        resource_statuses={"vpc-main": "success", "simulated-node": "success"}
                    )

            # --- REAL MODE: Continue with actual tflocal plan ---
            # 2. Plan
            plan_stage = self._run_stage("plan", current_hcl) 
            stages_history.append(plan_stage)
            if stage_callback: stage_callback(plan_stage)

            # 3. Apply
            apply_stage = self._run_stage("apply", current_hcl)
            stages_history.append(apply_stage)
            if stage_callback: stage_callback(apply_stage)
            
            if apply_stage.status == "failed":
                if stage_callback:
                    stage_callback(PipelineStage(name="Self-Correction", status="fixing", logs=[f"⚠️ Apply Failed. Agent is analyzing error and patching code..."]))
                current_hcl = self._fix_code(current_hcl, apply_stage.error, "terraform apply", callback=stage_callback)
                self._write_files(current_hcl, test_script)
                continue
                
            # 4. Verify (Test Script)
            verify_stage = self._run_stage("verify", test_script, is_python=True)
            stages_history.append(verify_stage)
            if stage_callback: stage_callback(verify_stage)
            
            # Extract Resource Statuses (for Visualizer Green Light)
            resource_statuses = {}
            if verify_stage.logs:
                full_log = "\n".join(verify_stage.logs)
                # Parse the last JSON-like line in logs (our test scripts print a status dict)
                lines = full_log.strip().split('\n')
                for line in reversed(lines):
                    try:
                        if line.strip().startswith('{') and line.strip().endswith('}'):
                            resource_statuses = json.loads(line)
                            break
                    except:
                        continue

            # Check for verification failures even if script exited successfully
            if verify_stage.status == "success" and resource_statuses:
                failed_resources = [rid for rid, status in resource_statuses.items() if status != "success"]
                if failed_resources:
                    verify_stage.status = "failed"
                    verify_stage.error = f"Verification failed for: {', '.join(failed_resources)}"
                    # Update the log to reflect this failure
                    if stage_callback:
                        # Re-emit the failure status
                        verify_stage.logs.append(f"❌ Verification Logic Failed: {len(failed_resources)} resources missing.")
                        stage_callback(verify_stage)

            if verify_stage.status == "success":
                return PipelineResult(
                    success=True,
                    hcl_code=current_hcl,
                    stages=stages_history,
                    final_message="Infrastructure Deployed and Verified Successfully!",
                    resource_statuses=resource_statuses
                )
            else:
                # Even if verification fails, we return what passed/failed
                return PipelineResult(
                    success=False,
                    hcl_code=current_hcl,
                    stages=stages_history,
                    final_message="Deployment succeeded, but Verification script failed.",
                    resource_statuses=resource_statuses
                )

        return PipelineResult(
            success=False,
            hcl_code=current_hcl,
            stages=stages_history,
            final_message="Pipeline failed after maximum retries.",
            resource_statuses={}
        )

    def _run_stage(self, stage_name: str, content: str, is_python: bool = False, stage_callback=None) -> PipelineStage:
        logs = [f"Starting {stage_name}..."]
        
        if SIMULATION_MODE:
            return self._simulate_execution(stage_name, content, stage_callback)
        
        # REAL EXECUTION COMMANDS
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
            # Terraform Init Check
            if stage_name == "validate":
                 # Always clean lock file AND state files to prevent version conflicts
                 # (Especially when downgrading from v6 state to v5 provider)
                 import shutil
                 for f in [".terraform.lock.hcl", "terraform.tfstate", "terraform.tfstate.backup", "localstack_providers_override.tf"]:
                     path = os.path.join(self.work_dir, f)
                     if os.path.exists(path):
                         os.remove(path)
                 
                 # Remove entire .terraform directory to ensure clean init
                 terraform_dir = os.path.join(self.work_dir, ".terraform")
                 if os.path.exists(terraform_dir):
                     shutil.rmtree(terraform_dir)
                 
                 # Force init to ensure providers match clean config
                 init_result = subprocess.run(["tflocal", "init", "-upgrade"], cwd=self.work_dir, capture_output=True, text=True)
                 if init_result.returncode != 0:
                     print(f"DEBUG: Terraform Init Failed (Code {init_result.returncode}):\nSTDOUT: {init_result.stdout}\nSTDERR: {init_result.stderr}")

            result = subprocess.run(
                cmd, 
                cwd=self.work_dir, 
                capture_output=True, 
                text=True,
                timeout=300
            )
            
            # Clean Logs (remove excessive whitespace)
            clean_logs = [l.strip() for l in result.stdout.split('\n') if l.strip()]
            if result.stderr:
                clean_logs.append(f"STDERR: {result.stderr}")

            status = "success" if result.returncode == 0 else "failed"
            
            # --- POLICY CHECK (Self-Correction Trigger) ---
            if stage_name == "validate" and status == "success":
                policy_error = self._check_policy(content)
                if policy_error:
                    status = "failed"
                    clean_logs.append(f"❌ POLICY ERROR: {policy_error}")
                    return PipelineStage(name=stage_name, status="failed", logs=clean_logs, error=policy_error)

            return PipelineStage(name=stage_name, status=status, logs=clean_logs, error=result.stderr if status=="failed" else None)
                
        except Exception as e:
            return PipelineStage(name=stage_name, status="failed", logs=[str(e)], error=str(e))

    def _check_policy(self, hcl_code: str) -> Optional[str]:
        """
        Scans HCL for forbidden patterns (e.g., inline ingress/egress rules).
        Returns an error string if violations are found, None otherwise.
        """
        import re
        
        # Regex to find resource blocks
        resource_pattern = re.compile(r'resource\s+"aws_security_group"\s+"([^"]+)"\s+\{(.*?)\}', re.DOTALL)
        
        for match in resource_pattern.finditer(hcl_code):
            sg_name = match.group(1)
            sg_body = match.group(2)
            
            # Check for inline ingress
            if re.search(r'\bingress\s*\{', sg_body):
                return f"Inline 'ingress' block found in security group '{sg_name}'. Use 'aws_security_group_rule' resource instead."
                
            # Check for inline egress
            if re.search(r'\begress\s*\{', sg_body):
                return f"Inline 'egress' block found in security group '{sg_name}'. Use 'aws_security_group_rule' resource instead."
            
        return None

    def _simulate_execution(self, stage_name: str, content: str, stage_callback=None) -> PipelineStage:
        """Generates realistic-looking fake logs for Draft Mode."""
        import re
        import random
        
        logs = []
        
        if stage_name == "apply":
            # Extract resources from HCL
            resources = []
            if "resource" in content:
                for match in re.finditer(r'resource\s+"([^"]+)"\s+"([^"]+)"', content):
                    r_type = match.group(1)
                    r_name = match.group(2)
                    resources.append(f"{r_type}.{r_name}")
            else:
                # Fallback if content isn't HCL (e.g. description string)
                # But we updated the calls to pass HCL!
                # Just in case, add some generic ones
                resources = ["aws_vpc.main_vpc", "aws_subnet.public_subnet_1", "aws_instance.web_server"]

            # Initial Plan Output (Mimic Terraform)
            logs.append("Terraform used the selected providers to generate the following execution")
            logs.append("plan. Resource actions are indicated with the following symbols:")
            logs.append("  + create")
            logs.append("")
            logs.append("Terraform will perform the following actions:")
            logs.append("")
            
            for r in resources:
                parts = r.split('.')
                r_type = parts[0]
                r_name = parts[1] if len(parts) > 1 else "main"
                
                logs.append(f"  # {r} will be created")
                logs.append(f"  + resource \"{r_type}\" \"{r_name}\" {{")
                logs.append("      + id = (known after apply)")
                logs.append("      + ...")
                logs.append("    }")
                logs.append("")
                
            logs.append(f"Plan: {len(resources)} to add, 0 to change, 0 to destroy.")
            if stage_callback: stage_callback(PipelineStage(name="apply", status="running", logs=list(logs)))
            
            time.sleep(1.0)
            
            # Creation Loop
            active_creations = []
            for i, r in enumerate(resources):
                # Start creating
                logs.append(f"{r}: Creating...")
                if stage_callback: stage_callback(PipelineStage(name="apply", status="running", logs=list(logs)))
                time.sleep(0.5)
                
                # Check previous creations (simulate "Still creating...")
                if i > 0 and i % 2 == 0:
                    prev = resources[i-1]
                    logs.append(f"{prev}: Still creating... [10s elapsed]")
                    if stage_callback: stage_callback(PipelineStage(name="apply", status="running", logs=list(logs)))
                    time.sleep(0.5)
                
                # Finish creating
                resource_id = f"{r.split('.')[1]}-{random.randint(10000,99999)}"
                logs.append(f"{r}: Creation complete after {random.randint(2,8)}s [id={resource_id}]")
                if stage_callback: stage_callback(PipelineStage(name="apply", status="running", logs=list(logs)))
                
            logs.append("")
            logs.append(f"Apply complete! Resources: {len(resources)} added, 0 changed, 0 destroyed.")
            if stage_callback: stage_callback(PipelineStage(name="apply", status="success", logs=list(logs)))

        elif stage_name == "verify":
             logs = [
                 "Running verification tests...",
                 "✅ Infrastructure layout validation passed.",
             ]
             # Parse HCL to generate realistic checks
             resources = []
             if "resource" in content:
                 for match in re.finditer(r'resource\s+"([^"]+)"\s+"([^"]+)"', content):
                     r_type = match.group(1)
                     r_name = match.group(2)
                     resources.append(f"{r_type}.{r_name}")
                     
                     if "instance" in r_type:
                         logs.append(f"✅ Instance [{r_name}] is running.")
                     elif "vpc" in r_type:
                         logs.append(f"✅ VPC [{r_name}] exists.")
                     elif "bucket" in r_type:
                         logs.append(f"✅ S3 Bucket [{r_name}] available.")
                     elif "security_group" in r_type:
                          logs.append(f"✅ Security Group [{r_name}] created.")
            
             logs.append("✅ Connectivity check: HTTP 200 OK.")
             
             # Generate success map for visualizer
             success_map = {r.split('.')[1]: "success" for r in resources}
             logs.append(json.dumps(success_map))
             if stage_callback: stage_callback(PipelineStage(name="verify", status="success", logs=list(logs)))

        else:
            logs = [f"Simulated {stage_name} complete."]
            if stage_callback: stage_callback(PipelineStage(name=stage_name, status="success", logs=list(logs)))

        return PipelineStage(name=stage_name, status="success", logs=logs)

    def _fix_code(self, code: str, error: str, context: str, callback=None) -> str:
        """
        Asks LLM to fix Terraform code with enhanced reasoning visibility.
        
        Args:
            callback: Optional function to emit reasoning events during fix
        """
        prompt = f"""
        You are an expert Terraform Debugger with X-ray vision into infrastructure code.
        
        CONTEXT: {context}
        ERROR OUTPUT:
        {error}
        
        CURRENT CODE:
        {code}
        
        INSTRUCTIONS:
        1. First, analyze the error and explain the root cause in 1-2 sentences
        2. Then, describe your proposed fix strategy
        3. Finally, return the complete fixed HCL code
        
        FORMAT YOUR RESPONSE AS:
        ANALYSIS: [Your error analysis]
        FIX STRATEGY: [Your fix approach]
        FIXED CODE:
        ```hcl
        [Complete fixed code here]
        ```
        """
        api_attempts = 0
        max_api_attempts = 5
        while api_attempts < max_api_attempts:
            try:
                response = self.agent_client.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )
                full_response = response.text
                
                # Parse and emit reasoning if callback provided
                if callback:
                    # Extract ANALYSIS
                    if "ANALYSIS:" in full_response:
                        analysis_end = full_response.find("FIX STRATEGY:")
                        if analysis_end == -1:
                            analysis_end = full_response.find("FIXED CODE:")
                        analysis = full_response[full_response.find("ANALYSIS:") + 9:analysis_end].strip()
                        if analysis:
                            callback(PipelineStage(
                                name="Self-Healing Analysis",
                                status="thinking",
                                logs=[f"🔍 Error Analysis: {analysis}"]
                            ))
                    
                    # Extract FIX STRATEGY
                    if "FIX STRATEGY:" in full_response:
                        strategy_start = full_response.find("FIX STRATEGY:") + 13
                        strategy_end = full_response.find("FIXED CODE:")
                        if strategy_end == -1:
                            strategy_end = full_response.find("```hcl")
                        strategy = full_response[strategy_start:strategy_end].strip()
                        if strategy:
                            callback(PipelineStage(
                                name="Self-Healing Strategy",
                                status="thinking",
                                logs=[f"💡 Proposed Fix: {strategy}"]
                            ))
                
                # Extract fixed code
                if "```hcl" in full_response:
                    code_start = full_response.find("```hcl") + 6
                    code_end = full_response.find("```", code_start)
                    fixed_code = full_response[code_start:code_end].strip()
                    
                    if callback:
                        callback(PipelineStage(
                            name="Self-Healing Patch",
                            status="thinking",
                            logs=["🔧 Applying code patch..."]
                        ))
                    
                    return fixed_code
                else:
                    # Fallback: return cleaned response
                    return full_response.replace("```hcl", "").replace("```", "").strip()
                    
            except Exception as e:
                error_str = str(e)
                if "503" in error_str or "429" in error_str:
                    api_attempts += 1
                    print(f"DEBUG: API Busy during Fix (Attempt {api_attempts}). Retrying...")
                    time.sleep(5)
                else:
                    return code # Return original if fatal error

    def _write_files(self, hcl: str, python: str):
        with open(os.path.join(self.work_dir, "main.tf"), "w") as f: f.write(hcl)
        with open(os.path.join(self.work_dir, "test_infra.py"), "w") as f: f.write(python)




        