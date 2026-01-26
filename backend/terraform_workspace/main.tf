provider "aws" {
  region = "us-east-1"
  # For localstack, configuration is usually handled outside the provider block
  # (e.g., via environment variables or endpoint_url in CLI config)
  # to keep the HCL cloud-agnostic.
}

# Fetch existing VPC and Subnet based on context
data "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

data "aws_subnet" "public" {
  vpc_id     = data.aws_vpc.main.id
  cidr_block = "10.0.1.0/24"
}

# Find latest Amazon Linux 2 AMI for the EC2 instance
data "aws_ami" "amazon_linux_2" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Create an Internet Gateway for the public subnet
resource "aws_internet_gateway" "igw" {
  vpc_id = data.aws_vpc.main.id

  tags = {
    Name = "main-igw"
  }
}

# Create a route table for the public subnet to route traffic to the IGW
resource "aws_route_table" "public_rt" {
  vpc_id = data.aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = {
    Name = "public-rt"
  }
}

# Associate the route table with the existing public subnet
resource "aws_route_table_association" "public_assoc" {
  subnet_id      = data.aws_subnet.public.id
  route_table_id = aws_route_table.public_rt.id
}

# Create the new private subnet
resource "aws_subnet" "private" {
  vpc_id            = data.aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "us-east-1a" # Specify AZ for consistency

  tags = {
    Name = "private-subnet"
  }
}

# Create a DB Subnet Group for the RDS instance
resource "aws_db_subnet_group" "db_subnet_group" {
  name       = "main-db-subnet-group"
  subnet_ids = [aws_subnet.private.id]

  tags = {
    Name = "My DB Subnet Group"
  }
}

# Web Server Security Group
resource "aws_security_group" "sg_web" {
  name        = "sg-web"
  description = "Allow public inbound HTTP and SSH traffic"
  vpc_id      = data.aws_vpc.main.id

  ingress {
    description = "SSH from public"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP from public"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "sg-web"
  }
}

# Database Security Group
resource "aws_security_group" "sg_db" {
  name        = "sg-db"
  description = "Allow inbound traffic from the web security group"
  vpc_id      = data.aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from web SG"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.sg_web.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "sg-db"
  }
}

# EC2 Instance in the public subnet
resource "aws_instance" "web" {
  ami                         = data.aws_ami.amazon_linux_2.id
  instance_type               = "t2.micro"
  subnet_id                   = data.aws_subnet.public.id
  associate_public_ip_address = true
  vpc_security_group_ids      = [aws_security_group.sg_web.id]

  tags = {
    Name = "web-instance"
  }
}

# RDS Postgres Instance in the private subnet
resource "aws_db_instance" "db_private" {
  identifier             = "db-private"
  engine                 = "postgres"
  engine_version         = "14.6"
  instance_class         = "db.t2.micro"
  allocated_storage      = 20
  # Note: In a real environment, use a secret management tool.
  username               = "myuser"
  password               = "mypassword123"
  db_subnet_group_name   = aws_db_subnet_group.db_subnet_group.name
  vpc_security_group_ids = [aws_security_group.sg_db.id]
  publicly_accessible    = false
  skip_final_snapshot    = true

  tags = {
    Name = "private-db"
  }
}
