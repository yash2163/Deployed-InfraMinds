import boto3
import os

# --- Configuration ---
LOCALSTACK_ENDPOINT = os.environ.get("LOCALSTACK_ENDPOINT", 'http://localhost:4566')
AWS_REGION = 'us-east-1'

# --- Boto3 Clients ---
# Use dummy credentials for localstack
os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'

boto_config = {
    'region_name': AWS_REGION,
    'endpoint_url': LOCALSTACK_ENDPOINT,
}

ec2_client = boto3.client('ec2', **boto_config)
rds_client = boto3.client('rds', **boto_config)

def get_instance_by_tag(tag_value):
    """Finds a running instance by its Name tag."""
    response = ec2_client.describe_instances(
        Filters=[
            {'Name': 'tag:Name', 'Values': [tag_value]},
            {'Name': 'instance-state-name', 'Values': ['running']}
        ]
    )
    instances = [instance for reservation in response['Reservations'] for instance in reservation['Instances']]
    return instances[0] if instances else None

def get_resource_by_tag(client, describe_call, response_key, tag_key, tag_value):
    """Generic function to find a resource by a specific tag."""
    paginator = client.get_paginator(describe_call)
    pages = paginator.paginate(Filters=[{'Name': f'tag:{tag_key}', 'Values': [tag_value]}])
    resources = [resource for page in pages for resource in page[response_key]]
    return resources[0] if resources else None

def verify_infrastructure():
    """
    Main function to run all verification checks.
    Raises an Exception if any check fails.
    """
    print("--- Starting Infrastructure Verification ---")

    # 1. Verify VPC
    vpc = get_resource_by_tag(ec2_client, 'describe_vpcs', 'Vpcs', 'Name', 'vpc-main')
    assert vpc, "VPC with Name tag 'vpc-main' not found."
    assert vpc['CidrBlock'] == '10.0.0.0/16', f"VPC CIDR is not '10.0.0.0/16', got {vpc['CidrBlock']}"
    vpc_id = vpc['VpcId']
    print("✅ VPC 'vpc-main' exists with correct CIDR.")

    # 2. Verify Subnets
    public_subnet = get_resource_by_tag(ec2_client, 'describe_subnets', 'Subnets', 'Name', 'subnet-public')
    assert public_subnet, "Subnet with Name tag 'subnet-public' not found."
    assert public_subnet['CidrBlock'] == '10.0.1.0/24', "Public Subnet CIDR is incorrect"
    assert public_subnet['VpcId'] == vpc_id, "Public Subnet is not in the correct VPC"
    public_subnet_id = public_subnet['SubnetId']
    print("✅ Subnet 'subnet-public' exists with correct CIDR.")

    private_subnet = get_resource_by_tag(ec2_client, 'describe_subnets', 'Subnets', 'Name', 'subnet-private')
    assert private_subnet, "Subnet with Name tag 'subnet-private' not found."
    assert private_subnet['CidrBlock'] == '10.0.2.0/24', "Private Subnet CIDR is incorrect"
    assert private_subnet['VpcId'] == vpc_id, "Private Subnet is not in the correct VPC"
    print("✅ Subnet 'subnet-private' exists with correct CIDR.")

    # 3. Verify Security Groups
    sg_web_response = ec2_client.describe_security_groups(Filters=[{'Name': 'group-name', 'Values': ['sg-web']}])
    assert len(sg_web_response['SecurityGroups']) == 1, "Security Group 'sg-web' not found"
    sg_web = sg_web_response['SecurityGroups'][0]
    sg_web_id = sg_web['GroupId']
    
    http_rule = any(p['FromPort'] == 80 and any(r.get('CidrIp') == '0.0.0.0/0' for r in p.get('IpRanges', [])) for p in sg_web.get('IpPermissions', []))
    assert http_rule, "Web SG does not have an ingress rule for HTTP (port 80) from 0.0.0.0/0"
    print("✅ Security Group 'sg-web' exists with correct HTTP rule.")
    
    sg_db_response = ec2_client.describe_security_groups(Filters=[{'Name': 'group-name', 'Values': ['sg-db']}])
    assert len(sg_db_response['SecurityGroups']) == 1, "Security Group 'sg-db' not found"
    sg_db = sg_db_response['SecurityGroups'][0]
    
    db_rule = any(p['FromPort'] == 3306 and any(g.get('GroupId') == sg_web_id for g in p.get('UserIdGroupPairs', [])) for p in sg_db.get('IpPermissions', []))
    assert db_rule, f"DB SG does not allow MySQL traffic (3306) from Web SG '{sg_web_id}'"
    print("✅ Security Group 'sg-db' exists and allows traffic from 'sg-web'.")

    # 4. Verify EC2 Instance
    instance = get_instance_by_tag('instance-web')
    assert instance, "EC2 instance with Name tag 'instance-web' not found or not running."
    assert 'PublicIpAddress' in instance, "Instance does not have a public IP address"
    assert instance['SubnetId'] == public_subnet_id, "Instance is not in the public subnet"
    instance_sg_ids = [sg['GroupId'] for sg in instance['SecurityGroups']]
    assert sg_web_id in instance_sg_ids, "Instance is not associated with the 'sg-web' security group"
    print("✅ EC2 Instance 'instance-web' is running in the public subnet with a public IP.")

    # 5. Verify RDS Instance
    db_instances = rds_client.describe_db_instances(DBInstanceIdentifier='db-private')['DBInstances']
    assert len(db_instances) == 1, "Expected 1 RDS instance with identifier 'db-private'"
    db_instance = db_instances[0]
    assert db_instance['DBInstanceStatus'] == 'available', f"RDS instance is not available, status is {db_instance['DBInstanceStatus']}"
    assert db_instance['Engine'] == 'mysql', "RDS engine is not mysql"
    assert not db_instance['PubliclyAccessible'], "RDS instance is publicly accessible, but should be private"
    print("✅ RDS Instance 'db-private' is available and configured as private.")

    print("\n--- All checks passed! ---")


if __name__ == "__main__":
    try:
        verify_infrastructure()
        print("VERIFICATION SUCCESS")
    except Exception as e:
        print(f"\nVERIFICATION FAILED: {e}")
        # Re-raising allows CI/CD systems to catch the failure exit code
        raise
