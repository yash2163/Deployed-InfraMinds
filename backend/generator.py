import networkx as nx
from typing import Dict, List, Any

class TerraformGenerator:
    def __init__(self, graph: nx.DiGraph):
        self.graph = graph

    def generate(self) -> Dict[str, str]:
        """
        Generates Terraform code from the graph.
        Returns a dict: {"main.tf": "..."}
        """
        hcl_blocks = []
        
        # 0. Global Lookups
        vpc_id = self._find_global_vpc()
        vpc_node_id = vpc_id.split('.')[1] if '.' in vpc_id else "vpc-main" 
        
        # 1. Provider Block
        hcl_blocks.append("""provider "aws" {
  region = "us-east-1"
  # Simulated for LocalStack
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  access_key                  = "test"
  secret_key                  = "test"
}""")

        # 1.1 Networking Infrastructure (IGW & Route Tables)
        # We auto-generate these if a VPC exists, to make it functional.
        if vpc_id != '"unknown-vpc-id"':
             hcl_blocks.append(f"""# --- Networking Backbone ---
resource "aws_internet_gateway" "igw" {{
  vpc_id = {vpc_id}
  tags = {{ Name = "main-igw" }}
}}

resource "aws_route_table" "public_rt" {{
  vpc_id = {vpc_id}
  route {{
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }}
  tags = {{ Name = "public-rt" }}
}}""")

        # 2. Iterate Resources
        private_subnets = []
        public_subnets = []
        
        for node_id in self.graph.nodes():
            node = self.graph.nodes[node_id]
            res_type = node.get("type", "unknown")
            props = node.get("properties", {})
            
            if res_type == "aws_vpc":
                hcl_blocks.append(self._gen_vpc(node_id, props))
            elif res_type == "aws_subnet":
                block = self._gen_subnet(node_id, props, vpc_id)
                hcl_blocks.append(block)
                
                # Auto-associate public subnets
                if "public" in node_id:
                     public_subnets.append(node_id)
                     hcl_blocks.append(f"""resource "aws_route_table_association" "assoc_{node_id}" {{
  subnet_id      = aws_subnet.{node_id}.id
  route_table_id = aws_route_table.public_rt.id
}}""")
                else:
                     private_subnets.append(node_id)
                     
            elif res_type == "aws_instance":
                hcl_blocks.append(self._gen_instance(node_id, props))
            elif res_type == "aws_security_group":
                hcl_blocks.append(self._gen_sg(node_id, props, vpc_id))
            elif res_type == "aws_db_instance":
                pass 
            else:
                hcl_blocks.append(f"# Unsupported resource: {node_id} ({res_type})")

        # 3. Handle DBs and Subnet Groups (HA Requirement)
        db_nodes = [n for n, d in self.graph.nodes(data=True) if d.get("type") == "aws_db_instance"]
        if db_nodes:
            # RDS Needs at least 2 subnets in different AZs.
            # If we only have 1 private subnet, we must mock a second one for Terraform validation.
            target_subnets = private_subnets if private_subnets else public_subnets
            
            # Mocking the HA requirement if deficient
            if len(target_subnets) < 2 and vpc_id != '"unknown-vpc-id"':
                 mock_subnet_id = "subnet-private-db-ha-mock"
                 hcl_blocks.append(f"""# Mock Subnet for RDS High Availability (Different AZ)
resource "aws_subnet" "{mock_subnet_id}" {{
  vpc_id            = {vpc_id}
  cidr_block        = "10.0.99.0/24"
  availability_zone = "us-east-1b"
  tags = {{ Name = "{mock_subnet_id}" }}
}}""")
                 target_subnets.append(mock_subnet_id)

            # Create Subnet Group Block
            # Filter subnets: existing ones reference aws_subnet.X.id
            subnet_ids_ref = []
            for s in target_subnets:
                 # Check if it was a graph node or our mock
                 if s in self.graph.nodes:
                     subnet_ids_ref.append(f"aws_subnet.{s}.id")
                 else:
                     subnet_ids_ref.append(f"aws_subnet.{s}.id") # Our mock uses same logic

            subnet_group_name = "db-subnet-group-main"
            
            hcl_blocks.append(f"""resource "aws_db_subnet_group" "{subnet_group_name}" {{
  name       = "{subnet_group_name}"
  subnet_ids = [{', '.join(subnet_ids_ref)}]
  tags = {{
    Name = "Generated DB Subnet Group"
  }}
}}""")
            
            # Generate the DB Instances referencing this group
            for db_id in db_nodes:
                props = self.graph.nodes[db_id].get("properties", {})
                hcl_blocks.append(self._gen_db(db_id, props, subnet_group_name))

                hcl_blocks.append(self._gen_db(db_id, props, subnet_group_name))

        # 4. Handle Unsupported Resources (ALB/ASG)
        for node_id, node in self.graph.nodes(data=True):
             res_type = node.get("type", "unknown")
             props = node.get("properties", {})
             if res_type == "aws_lb":
                 hcl_blocks.append(self._gen_alb(node_id, props, public_subnets))
             elif res_type == "aws_launch_template":
                 hcl_blocks.append(self._gen_launch_template(node_id, props))
             elif res_type == "aws_autoscaling_group":
                 hcl_blocks.append(self._gen_asg(node_id, props, private_subnets))

        return {"main.tf": "\n\n".join(hcl_blocks)}

    def _gen_alb(self, node_id: str, props: Dict[str, Any], subnets: List[str]) -> str:
        sg_refs = self._find_connected_sgs(node_id)
        sg_block = f"security_groups = [{', '.join(sg_refs)}]" if sg_refs else ""
        
        subnet_refs = [f"aws_subnet.{s}.id" for s in subnets]
        subnet_block = f"subnets = [{', '.join(subnet_refs)}]"
        
        return f"""resource "aws_lb" "{node_id}" {{
  name               = "{node_id}"
  internal           = false
  load_balancer_type = "application"
  {sg_block}
  {subnet_block}
  tags = {{ Name = "{node_id}" }}
}}"""

    def _gen_launch_template(self, node_id: str, props: Dict[str, Any]) -> str:
        ami = props.get("ami", "ami-0c55b159cbfafe1f0")
        instance_type = props.get("instance_type", "t2.micro")
        sg_refs = self._find_connected_sgs(node_id)
        
        return f"""resource "aws_launch_template" "{node_id}" {{
  name_prefix   = "{node_id}"
  image_id      = "{ami}"
  instance_type = "{instance_type}"
  
  vpc_security_group_ids = [{', '.join(sg_refs)}]
  
  tag_specifications {{
    resource_type = "instance"
    tags = {{ Name = "{node_id}-instance" }}
  }}
}}"""

    def _gen_asg(self, node_id: str, props: Dict[str, Any], subnets: List[str]) -> str:
        # Find attached Launch Template (Parent)
        lt_ref = self._get_parent_id(node_id, "aws_launch_template")
        if not lt_ref:
             # Fallback: Look for ANY LT in graph if strict parent relationship missing
             lts = [n for n in self.graph.nodes if self.graph.nodes[n].get("type") == "aws_launch_template"]
             if lts: lt_ref = f"aws_launch_template.{lts[0]}.id"
             else: lt_ref = '"unknown-lt"'

        min_size = props.get("min_size", 1)
        max_size = props.get("max_size", 3)
        
        subnet_refs = [f"aws_subnet.{s}.id" for s in subnets]
        vpc_zone_id = f"vpc_zone_identifier = [{', '.join(subnet_refs)}]"
        
        return f"""resource "aws_autoscaling_group" "{node_id}" {{
  desired_capacity    = {min_size}
  max_size            = {max_size}
  min_size            = {min_size}
  {vpc_zone_id}
  
  launch_template {{
    id      = {lt_ref}
    version = "$Latest"
  }}
  
  tag {{
    key                 = "Name"
    value               = "{node_id}-asg"
    propagate_at_launch = true
  }}
}}"""

    def _find_global_vpc(self) -> str:
        """Finds a VPC node to use as default context."""
        for node_id, data in self.graph.nodes(data=True):
            if data.get("type") == "aws_vpc":
                return f"aws_vpc.{node_id}.id"
        return '"unknown-vpc-id"'

    def _get_parent_id(self, node_id: str, parent_type: str) -> str:
        """Finds the ID of a parent resource."""
        for u, v, data in self.graph.in_edges(node_id, data=True):
            if self.graph.nodes[u].get("type") == parent_type:
                return f"{parent_type}.{u}.id"
        return None  # Return None if not found, to imply fallback

    def _find_connected_sgs(self, node_id: str) -> List[str]:
        """Finds Security Groups connected to this node."""
        sgs = []
        # Check explicit edges: SG -> Instance (Attached to) OR Instance -> SG (Uses)
        # We check both directions for robustness in this simple graph model
        for u, v, data in self.graph.edges(node_id, data=True):
            if self.graph.nodes[v].get("type") == "aws_security_group":
                sgs.append(f"aws_security_group.{v}.id")
        
        for u, v, data in self.graph.in_edges(node_id, data=True):
            if self.graph.nodes[u].get("type") == "aws_security_group":
                sgs.append(f"aws_security_group.{u}.id")
        return list(set(sgs))

    def _gen_vpc(self, node_id: str, props: Dict[str, Any]) -> str:
        cidr = props.get("cidr_block", props.get("cidr", "10.0.0.0/16"))
        return f"""resource "aws_vpc" "{node_id}" {{
  cidr_block = "{cidr}"
  tags = {{
    Name = "{node_id}"
  }}
}}"""

    def _gen_subnet(self, node_id: str, props: Dict[str, Any], default_vpc_id: str) -> str:
        cidr = props.get("cidr_block", props.get("cidr", "10.0.1.0/24"))
        
        # Determine VPC
        vpc_ref = self._get_parent_id(node_id, "aws_vpc") or default_vpc_id
        
        # Logic for Public IP
        map_public = "true" if "public" in node_id else "false"
        
        # Logic for AZ (Simple Hash)
        az_suffix = "a" if hash(node_id) % 2 == 0 else "b"
        az = f"us-east-1{az_suffix}"

        return f"""resource "aws_subnet" "{node_id}" {{
  vpc_id                  = {vpc_ref}
  cidr_block              = "{cidr}"
  map_public_ip_on_launch = {map_public}
  availability_zone       = "{az}"
  tags = {{
    Name = "{node_id}"
  }}
}}"""

    def _gen_instance(self, node_id: str, props: Dict[str, Any]) -> str:
        ami = props.get("ami", "ami-0c55b159cbfafe1f0")
        instance_type = props.get("instance_type", "t2.micro")
        
        subnet_ref = self._get_parent_id(node_id, "aws_subnet") or '"unknown-subnet"'
        
        # Find SGs
        sg_refs = self._find_connected_sgs(node_id)
        sg_block = f"vpc_security_group_ids = [{', '.join(sg_refs)}]" if sg_refs else ""
        
        return f"""resource "aws_instance" "{node_id}" {{
  ami           = "{ami}"
  instance_type = "{instance_type}"
  subnet_id     = {subnet_ref}
  {sg_block}
  tags = {{
    Name = "{node_id}"
  }}
}}"""

    def _gen_sg(self, node_id: str, props: Dict[str, Any], default_vpc_id: str) -> str:
        description = props.get("description", "Managed by InfraMinds")
        vpc_ref = self._get_parent_id(node_id, "aws_vpc") or default_vpc_id
        
        # Ingress
        ingress_blocks = ""
        ingress_rules = props.get("ingress", [])
        
        # Demo Default: If no rules and it's "sg-web", open port 80
        if not ingress_rules and "web" in node_id:
             ingress_rules = [{"from_port": 80, "to_port": 80, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]}]
        
        if isinstance(ingress_rules, list):
            for rule in ingress_rules:
                if isinstance(rule, dict):
                    # Check if rule.cidr_blocks implies an SG reference
                    # (In our simple graph, we might store SG ID in a special field or infer it)
                    # For this demo, let's look for a special key 'source_security_group_id' 
                    # OR we can infer it if we see 'sg-' in cidr... unlikely.
                    
                    # BETTER APPROACH: The Agent (LLM) should populate 'source_security_group_id' in properties.
                    # But since the LLM output is variable, let's just make the generator smart.
                    
                    # If the property has 'security_groups', use it.
                    sg_ref_list = rule.get("security_groups", [])
                    sg_refs_str = ""
                    if sg_ref_list:
                         # Assume these are raw IDs like 'sg-web', need to convert to TF ref 'aws_security_group.sg-web.id'
                         refs = [f"aws_security_group.{s}.id" for s in sg_ref_list]
                         sg_refs_str = f"security_groups = [{', '.join(refs)}]"
                    
                    cidr_list = rule.get("cidr_blocks", [])
                    # If empty CIDR and empty SG, default to 0.0.0.0/0 for demo connectivity OR handle explicit logic?
                    # The user issue was Empty CIDR.
                    
                    # If this is a DB SG (heuristic: "db" in name) and we have no CIDR/SG, 
                    # let's try to find an upstream SG (e.g. "sg-web") and allow it.
                    if "db" in node_id and not cidr_list and not sg_ref_list:
                         # Attempt to find "web" SG in graph
                         web_sgs = [n for n in self.graph.nodes if "web" in n and self.graph.nodes[n].get("type") == "aws_security_group"]
                         if web_sgs:
                             refs = [f"aws_security_group.{s}.id" for s in web_sgs]
                             sg_refs_str = f"security_groups = [{', '.join(refs)}]"

                    cidr_str = f"cidr_blocks = {json.dumps(cidr_list)}" if cidr_list else ""

                    ingress_blocks += f"""
  ingress {{
    from_port   = {rule.get('from_port', 0)}
    to_port     = {rule.get('to_port', 0)}
    protocol    = "{rule.get('protocol', 'tcp')}"
    {cidr_str}
    {sg_refs_str}
  }}"""

        return f"""resource "aws_security_group" "{node_id}" {{
  name        = "{node_id}"
  description = "{description}"
  vpc_id      = {vpc_ref}
{ingress_blocks}
}}"""

    def _gen_db(self, node_id: str, props: Dict[str, Any], subnet_group_name: str) -> str:
        engine = props.get("engine", "mysql")
        instance_class = props.get("instance_class", "db.t3.micro")
        user = props.get("username", "admin")
        pw = props.get("password", "secret123")
        
        sg_refs = self._find_connected_sgs(node_id)
        sg_block = f"vpc_security_group_ids = [{', '.join(sg_refs)}]" if sg_refs else ""
        
        return f"""resource "aws_db_instance" "{node_id}" {{
  allocated_storage      = 10
  engine                 = "{engine}"
  instance_class         = "{instance_class}"
  username               = "{user}"
  password               = "{pw}"
  skip_final_snapshot    = true
  db_subnet_group_name   = aws_db_subnet_group.{subnet_group_name}.name
  {sg_block}
  tags = {{
    Name = "{node_id}"
  }}
}}"""

import json
