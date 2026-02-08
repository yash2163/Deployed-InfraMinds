import json
import os

# DEMO MODE CONFIGURATION
# Load demo graph from the export file
current_dir = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(current_dir, 'graph_state.json')

try:
    with open(json_path, 'r') as f:
        graph_data = json.load(f)
except FileNotFoundError:
    graph_data = {"resources": [], "edges": []}
    print(f"Warning: {json_path} not found.")

DEMO_GRAPH = {
    "project_id": "demo_project",
    "graph_phase": "implementation",
    "resources": graph_data.get("resources", []),
    "edges": graph_data.get("edges", [])
}

DEMO_PROMPT = "Create a production-grade AWS architecture featuring a VPC with public, private, and firewall subnets across 2 AZs. Include an Internet Gateway, NAT Gateways for private egress, an AWS Network Firewall for deep packet inspection, an Application Load Balancer, a multi-AZ compute tier (EC2), a multi-AZ RDS PostgreSQL database, and an ElastiCache Redis cluster for session management."

DEMO_TERRAFORM = """terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }
}

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "mock_access_key"
  secret_key                  = "mock_secret_key"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

variable "db_password" {
  description = "Password for the RDS database"
  type        = string
  sensitive   = true
}

variable "db_username" {
  description = "Username for the RDS database"
  type        = string
  default     = "postgresadmin"
}

# --- NETWORKING --- 

resource "aws_vpc" "vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "Main VPC"
  }
}

resource "aws_subnet" "public_subnet_a" {
  vpc_id                  = aws_vpc.vpc.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "us-east-1a"
  map_public_ip_on_launch = true

  tags = {
    Name = "Public Subnet AZ-a"
  }
}

resource "aws_subnet" "public_subnet_b" {
  vpc_id                  = aws_vpc.vpc.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = "us-east-1b"
  map_public_ip_on_launch = true

  tags = {
    Name = "Public Subnet AZ-b"
  }
}

resource "aws_subnet" "private_subnet_a" {
  vpc_id            = aws_vpc.vpc.id
  cidr_block        = "10.0.101.0/24"
  availability_zone = "us-east-1a"

  tags = {
    Name = "Private Subnet AZ-a"
  }
}

resource "aws_subnet" "private_subnet_b" {
  vpc_id            = aws_vpc.vpc.id
  cidr_block        = "10.0.102.0/24"
  availability_zone = "us-east-1b"

  tags = {
    Name = "Private Subnet AZ-b"
  }
}

resource "aws_subnet" "firewall_subnet_a" {
  vpc_id            = aws_vpc.vpc.id
  cidr_block        = "10.0.3.0/24"
  availability_zone = "us-east-1a"

  tags = {
    Name = "Firewall Subnet AZ-a"
  }
}

resource "aws_subnet" "firewall_subnet_b" {
  vpc_id            = aws_vpc.vpc.id
  cidr_block        = "10.0.4.0/24"
  availability_zone = "us-east-1b"

  tags = {
    Name = "Firewall Subnet AZ-b"
  }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.vpc.id

  tags = {
    Name = "Main IGW"
  }
}

resource "aws_eip" "nat_eip" {
  domain = "vpc"
  tags = {
    Name = "NAT Gateway EIP AZ-a"
  }
}

resource "aws_nat_gateway" "nat_gateway" {
  allocation_id = aws_eip.nat_eip.id
  subnet_id     = aws_subnet.public_subnet_a.id
  depends_on    = [aws_internet_gateway.igw]

  tags = {
    Name = "NAT Gateway AZ-a"
  }
}

resource "aws_eip" "nat_eip_b" {
  domain = "vpc"
  tags = {
    Name = "NAT Gateway EIP AZ-b"
  }
}

resource "aws_nat_gateway" "nat_gateway_b" {
  allocation_id = aws_eip.nat_eip_b.id
  subnet_id     = aws_subnet.public_subnet_b.id
  depends_on    = [aws_internet_gateway.igw]

  tags = {
    Name = "NAT Gateway AZ-b"
  }
}

# --- ROUTING --- 

resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.vpc.id

  tags = {
    Name = "Public Route Table"
  }
}

resource "aws_route" "public_route" {
  route_table_id         = aws_route_table.public_rt.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.igw.id
}

resource "aws_route_table_association" "public_rt_assoc_a" {
  subnet_id      = aws_subnet.public_subnet_a.id
  route_table_id = aws_route_table.public_rt.id
}

resource "aws_route_table_association" "public_rt_assoc_b" {
  subnet_id      = aws_subnet.public_subnet_b.id
  route_table_id = aws_route_table.public_rt.id
}

resource "aws_route_table" "private_rt" {
  vpc_id = aws_vpc.vpc.id

  tags = {
    Name = "Private Route Table AZ-a"
  }
}

resource "aws_route" "private_route" {
  route_table_id         = aws_route_table.private_rt.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.nat_gateway.id
}

resource "aws_route_table_association" "private_rt_assoc_a" {
  subnet_id      = aws_subnet.private_subnet_a.id
  route_table_id = aws_route_table.private_rt.id
}

resource "aws_route_table" "private_rt_b" {
  vpc_id = aws_vpc.vpc.id

  tags = {
    Name = "Private Route Table AZ-b"
  }
}

resource "aws_route" "private_route_b" {
  route_table_id         = aws_route_table.private_rt_b.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.nat_gateway_b.id
}

resource "aws_route_table_association" "private_rt_assoc_b" {
  subnet_id      = aws_subnet.private_subnet_b.id
  route_table_id = aws_route_table.private_rt_b.id
}

resource "aws_route_table" "firewall_rt" {
  vpc_id = aws_vpc.vpc.id

  tags = {
    Name = "Firewall Route Table"
  }
}

resource "aws_route" "firewall_route" {
  route_table_id         = aws_route_table.firewall_rt.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.igw.id
}

resource "aws_route_table_association" "firewall_rt_assoc_a" {
  subnet_id      = aws_subnet.firewall_subnet_a.id
  route_table_id = aws_route_table.firewall_rt.id
}

resource "aws_route_table_association" "firewall_rt_assoc_b" {
  subnet_id      = aws_subnet.firewall_subnet_b.id
  route_table_id = aws_route_table.firewall_rt.id
}

resource "aws_route_table" "igw_rt" {
  vpc_id = aws_vpc.vpc.id

  tags = {
    Name = "IGW Ingress Route Table"
  }
}

resource "aws_route_table_association" "igw_rt_assoc" {
  gateway_id     = aws_internet_gateway.igw.id
  route_table_id = aws_route_table.igw_rt.id
}

# --- NETWORK FIREWALL --- 

resource "aws_networkfirewall_firewall_policy" "firewall_policy" {
  name = "AllowAllPolicy"

  firewall_policy {
    stateless_default_actions          = ["aws:pass"]
    stateless_fragment_default_actions = ["aws:pass"]
  }
}

resource "aws_networkfirewall_firewall" "firewall" {
  name                = "main-firewall"
  firewall_policy_arn = aws_networkfirewall_firewall_policy.firewall_policy.arn
  vpc_id              = aws_vpc.vpc.id
  delete_protection   = false

  subnet_mapping {
    subnet_id = aws_subnet.firewall_subnet_a.id
  }

  subnet_mapping {
    subnet_id = aws_subnet.firewall_subnet_b.id
  }

  tags = {
    Name = "FIREWALL"
  }
}

# --- FIREWALL INGRESS ROUTING --- 
# Note: This relies on the AZ order being consistent. A more robust solution might use custom data sources.

resource "aws_route" "igw_route_a" {
  route_table_id         = aws_route_table.igw_rt.id
  destination_cidr_block = aws_subnet.public_subnet_a.cidr_block
  vpc_endpoint_id        = one([for state in aws_networkfirewall_firewall.firewall.firewall_status.0.sync_states : state.endpoint_id if state.availability_zone == "us-east-1a"])
}

resource "aws_route" "igw_route_b" {
  route_table_id         = aws_route_table.igw_rt.id
  destination_cidr_block = aws_subnet.public_subnet_b.cidr_block
  vpc_endpoint_id        = one([for state in aws_networkfirewall_firewall.firewall.firewall_status.0.sync_states : state.endpoint_id if state.availability_zone == "us-east-1b"])
}

# --- SECURITY GROUPS --- 

resource "aws_security_group" "lb_sg" {
  name        = "load-balancer-sg"
  description = "Allow public HTTP traffic"
  vpc_id      = aws_vpc.vpc.id

  tags = {
    Name = "Load Balancer SG"
  }
}

resource "aws_security_group" "app_sg" {
  name        = "app-server-sg"
  description = "Allow traffic from LB and allow outbound to DB/Cache"
  vpc_id      = aws_vpc.vpc.id

  tags = {
    Name = "App Server SG"
  }
}

resource "aws_security_group" "db_sg" {
  name        = "database-sg"
  description = "Allow traffic from App Servers"
  vpc_id      = aws_vpc.vpc.id

  tags = {
    Name = "Database SG"
  }
}

resource "aws_security_group" "cache_sg" {
  name        = "cache-sg"
  description = "Allow traffic from App Servers"
  vpc_id      = aws_vpc.vpc.id

  tags = {
    Name = "Cache SG"
  }
}

# --- SECURITY GROUP RULES --- 

# LB Rules
resource "aws_security_group_rule" "lb_sg_ingress_http" {
  type              = "ingress"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.lb_sg.id
}

resource "aws_security_group_rule" "lb_sg_egress_all" {
  type                     = "egress"
  from_port                = 8080
  to_port                  = 8080
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.app_sg.id
  security_group_id        = aws_security_group.lb_sg.id
}

# App Rules
resource "aws_security_group_rule" "app_sg_ingress_lb" {
  type                     = "ingress"
  from_port                = 8080
  to_port                  = 8080
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.lb_sg.id
  security_group_id        = aws_security_group.app_sg.id
}

resource "aws_security_group_rule" "app_sg_egress_all" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.app_sg.id
}

# DB Rules
resource "aws_security_group_rule" "db_sg_ingress_app" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.app_sg.id
  security_group_id        = aws_security_group.db_sg.id
}

resource "aws_security_group_rule" "db_sg_egress_all" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.db_sg.id
}

# Cache Rules
resource "aws_security_group_rule" "cache_sg_ingress_app" {
  type                     = "ingress"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.app_sg.id
  security_group_id        = aws_security_group.cache_sg.id
}

resource "aws_security_group_rule" "cache_sg_egress_all" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.cache_sg.id
}

# --- IAM --- 

data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2_iam_role" {
  name               = "ec2_ssm_role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ec2_ssm_policy_attachment" {
  role       = aws_iam_role.ec2_iam_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ec2_instance_profile" {
  name = "ec2_ssm_instance_profile"
  role = aws_iam_role.ec2_iam_role.name
}


# --- COMPUTE & LB --- 

resource "aws_lb" "load_balancer" {
  name               = "main-app-lb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.lb_sg.id]
  subnets            = [aws_subnet.public_subnet_a.id, aws_subnet.public_subnet_b.id]

  tags = {
    Name = "LOAD BALANCER"
  }
}

resource "aws_lb_target_group" "app_tg" {
  name     = "app-server-tg"
  port     = 8080
  protocol = "HTTP"
  vpc_id   = aws_vpc.vpc.id

  health_check {
    protocol = "HTTP"
    path     = "/health"
  }
}

resource "aws_lb_listener" "lb_listener" {
  load_balancer_arn = aws_lb.load_balancer.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app_tg.arn
  }
}

resource "aws_instance" "app_server_1" {
  instance_type          = "t3.medium"
  ami                    = "ami-0c55b159cbfafe1f0" # Amazon Linux 2
  subnet_id              = aws_subnet.private_subnet_a.id
  vpc_security_group_ids = [aws_security_group.app_sg.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_instance_profile.name

  root_block_device {
    encrypted = true
  }

  tags = {
    Name = "APP SERVER 1"
  }
}

resource "aws_instance" "app_server_2" {
  instance_type          = "t3.medium"
  ami                    = "ami-0c55b159cbfafe1f0" # Amazon Linux 2
  subnet_id              = aws_subnet.private_subnet_b.id
  vpc_security_group_ids = [aws_security_group.app_sg.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_instance_profile.name

  root_block_device {
    encrypted = true
  }

  tags = {
    Name = "APP SERVER 2"
  }
}

resource "aws_lb_target_group_attachment" "app_tg_attachment_1" {
  target_group_arn = aws_lb_target_group.app_tg.arn
  target_id        = aws_instance.app_server_1.id
  port             = 8080
}

resource "aws_lb_target_group_attachment" "app_tg_attachment_2" {
  target_group_arn = aws_lb_target_group.app_tg.arn
  target_id        = aws_instance.app_server_2.id
  port             = 8080
}

# --- DATA TIER --- 

resource "aws_db_subnet_group" "db_subnet_group" {
  name       = "main-db-subnet-group"
  subnet_ids = [aws_subnet.private_subnet_a.id, aws_subnet.private_subnet_b.id]

  tags = {
    Name = "Database Subnet Group"
  }
}

resource "aws_db_instance" "database" {
  identifier             = "main-db-instance"
  engine                 = "postgres"
  instance_class         = "db.t3.small"
  allocated_storage      = 20
  storage_encrypted      = true
  multi_az               = true
  publicly_accessible    = false
  db_subnet_group_name   = aws_db_subnet_group.db_subnet_group.name
  vpc_security_group_ids = [aws_security_group.db_sg.id]
  username               = var.db_username
  password               = var.db_password
  skip_final_snapshot    = true

  tags = {
    Name = "DATABASE"
  }
}

resource "aws_elasticache_subnet_group" "cache_subnet_group" {
  name       = "main-cache-subnet-group"
  subnet_ids = [aws_subnet.private_subnet_a.id, aws_subnet.private_subnet_b.id]
}

resource "aws_elasticache_replication_group" "cache" {
  replication_group_id          = "main-cache-replication-group"
  description                   = "Main cache cluster"
  engine                        = "redis"
  node_type                     = "cache.t3.small"
  at_rest_encryption_enabled    = true
  transit_encryption_enabled    = true
  automatic_failover_enabled    = true
  num_cache_clusters            = 2
  subnet_group_name             = aws_elasticache_subnet_group.cache_subnet_group.name
  security_group_ids            = [aws_security_group.cache_sg.id]
  
  tags = {
    Name = "CACHE"
  }
}"""


DEMO_IMAGE_PATH = "test-2.jpg"

DEMO_LOGS = [
    "Initializing InfraMinds Cloud Engine...",
    "Loading verified architecture pattern...",
    "Validating resource constraints...",
    "Generating Terraform configuration...",
    "Running terraform init...",
    "Initializing modules...",
    "Initializing provider plugins...",
    "- registry.terraform.io/hashicorp/aws v5.30.0...",
    "Terraform has been successfully initialized!",
    "Plan: 14 to add, 0 to change, 0 to destroy.",
    "aws_vpc.main: Creating...",
    "aws_vpc.main: Creation complete after 3s [id=vpc-0abc123456789]",
    "aws_subnet.public_1: Creating...",
    "aws_subnet.public_2: Creating...",
    "aws_subnet.private_1: Creating...",
    "aws_subnet.private_2: Creating...",
    "aws_subnet.public_1: Creation complete after 2s [id=subnet-111]",
    "aws_subnet.public_2: Creation complete after 2s [id=subnet-222]",
    "aws_subnet.private_1: Creation complete after 2s [id=subnet-333]",
    "aws_subnet.private_2: Creation complete after 2s [id=subnet-444]",
    "aws_internet_gateway.gw: Creating...",
    "aws_internet_gateway.gw: Creation complete after 1s [id=igw-0abc]",
    "aws_security_group.web_sg: Creating...",
    "aws_security_group.db_sg: Creating...",
    "aws_security_group.web_sg: Creation complete after 2s [id=sg-web]",
    "aws_security_group.db_sg: Creation complete after 2s [id=sg-db]",
    "aws_db_instance.default: Creating...",
    "aws_lb.web_lb: Creating...",
    "aws_lb.web_lb: Creation complete after 4s [id=arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/web-lb/50dc6c495c0c9188]",
    "aws_launch_template.web_lt: Creating...",
    "aws_launch_template.web_lt: Creation complete after 1s [id=lt-0abc123]",
    "aws_autoscaling_group.web_asg: Creating...",
    "aws_autoscaling_group.web_asg: Creation complete after 3s [id=web-asg]",
    "aws_db_instance.default: Creation complete after 8s [id=mydb]",
    "Apply complete! Resources: 14 added, 0 changed, 0 destroyed."
]

# Hardcoded cost estimates for demo mode
DEMO_COST = {
    "total_monthly_cost": 487.32,
    "breakdown": [
        {
            "resource_id": "aws_db_instance.main",
            "resource_type": "aws_db_instance (RDS MySQL)",
            "estimated_cost": 156.80,
            "explanation": "db.t3.medium instance running 24/7 with 100GB storage"
        },
        {
            "resource_id": "aws_lb.web_lb",
            "resource_type": "aws_lb (Application Load Balancer)",
            "estimated_cost": 22.50,
            "explanation": "ALB with standard processing and data transfer"
        },
        {
            "resource_id": "aws_autoscaling_group.web_asg",
            "resource_type": "aws_instance (EC2 Auto Scaling)",
            "estimated_cost": 145.60,
            "explanation": "2x t3.medium instances for web tier (estimated average)"
        },
        {
            "resource_id": "aws_nat_gateway.main",
            "resource_type": "aws_nat_gateway",
            "estimated_cost": 97.92,
            "explanation": "NAT Gateway with 1TB data processing per month"
        },
        {
            "resource_id": "aws_ebs_volume.web_storage",
            "resource_type": "aws_ebs_volume",
            "estimated_cost": 40.00,
            "explanation": "EBS volumes for EC2 instances (400GB total gp3)"
        },
        {
            "resource_id": "aws_vpc.main",
            "resource_type": "aws_vpc (Networking)",
            "estimated_cost": 12.50,
            "explanation": "VPC endpoints and data transfer costs"
        },
        {
            "resource_id": "aws_cloudwatch.monitoring",
            "resource_type": "aws_cloudwatch (Monitoring)",
            "estimated_cost": 12.00,
            "explanation": "CloudWatch metrics, logs, and alarms"
        }
    ]
}
