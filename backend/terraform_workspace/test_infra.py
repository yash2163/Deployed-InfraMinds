import boto3
import os
import time

# --- Configuration ---
LOCALSTACK_ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", 'http://localhost:4566')
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", 'us-east-1')
VPC_CIDR = '10.0.0.0/16'
PUBLIC_SUBNET_CIDR = '10.0.1.0/24'
PRIVATE_SUBNET_CIDR = '10.0.2.0/24'
INSTANCE_TAG_NAME = 'web-instance'
DB_IDENTIFIER = 'db-private'
WEB_SG_NAME = 'sg-web'
DB_SG_NAME = 'sg-db'

def get_boto_client(service_name):
    """Initializes and returns a boto3 client for LocalStack."""
    return boto3.client(
        service_name,
        endpoint_url=LOCALSTACK_ENDPOINT,
        region_name=AWS_REGION,
        aws_access_key_id='test',
        aws_secret_access_key='test'
    )

def verify_infra():
    """Runs all verification checks."""
    print("--- Starting Infrastructure Verification ---")
    ec2 = get_boto_client('ec2')
    rds = get_boto_client('rds')

    # 1. Verify VPC and Subnets
    print("Verifying VPC and Subnets...")
    vpcs = ec2.describe_vpcs(Filters=[{'Name': 'cidr-block', 'Values': [VPC_CIDR]}])['Vpcs']
    if not vpcs: raise Exception(f"VPC with CIDR {VPC_CIDR} not found.")
    vpc_id = vpcs[0]['VpcId']
    print(f"  [PASS] Found VPC {vpc_id}")

    subnets = ec2.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])['Subnets']
    public_subnet = next((s for s in subnets if s['CidrBlock'] == PUBLIC_SUBNET_CIDR), None)
    private_subnet = next((s for s in subnets if s['CidrBlock'] == PRIVATE_SUBNET_CIDR), None)
    if not public_subnet: raise Exception(f"Public subnet {PUBLIC_SUBNET_CIDR} not found.")
    if not private_subnet: raise Exception(f"Private subnet {PRIVATE_SUBNET_CIDR} not found.")
    public_subnet_id = public_subnet['SubnetId']
    print(f"  [PASS] Found Public Subnet {public_subnet_id}")
    print(f"  [PASS] Found Private Subnet {private_subnet['SubnetId']}")

    # 2. Verify Security Groups and Rules
    print("Verifying Security Groups...")
    sgs = ec2.describe_security_groups(
        Filters=[
            {'Name': 'vpc-id', 'Values': [vpc_id]},
            {'Name': 'group-name', 'Values': [WEB_SG_NAME, DB_SG_NAME]}
        ]
    )['SecurityGroups']
    web_sg = next((sg for sg in sgs if sg['GroupName'] == WEB_SG_NAME), None)
    db_sg = next((sg for sg in sgs if sg['GroupName'] == DB_SG_NAME), None)

    if not web_sg: raise Exception(f"Security group '{WEB_SG_NAME}' not found.")
    if not db_sg: raise Exception(f"Security group '{DB_SG_NAME}' not found.")
    web_sg_id = web_sg['GroupId']
    print(f"  [PASS] Found Web SG: {web_sg_id}")
    print(f"  [PASS] Found DB SG: {db_sg['GroupId']}")

    # Check Web SG rules
    ssh_rule = any(p['FromPort'] == 22 and p['ToPort'] == 22 and any(ip['CidrIp'] == '0.0.0.0/0' for ip in p['IpRanges']) for p in web_sg['IpPermissions'])
    http_rule = any(p['FromPort'] == 80 and p['ToPort'] == 80 and any(ip['CidrIp'] == '0.0.0.0/0' for ip in p['IpRanges']) for p in web_sg['IpPermissions'])
    if not ssh_rule: raise Exception(f"Web SG missing inbound SSH rule from 0.0.0.0/0.")
    if not http_rule: raise Exception(f"Web SG missing inbound HTTP rule from 0.0.0.0/0.")
    print("  [PASS] Web SG has correct inbound SSH and HTTP rules.")

    # Check DB SG rules
    db_rule = any(p['FromPort'] == 5432 and p['ToPort'] == 5432 and any(ug['GroupId'] == web_sg_id for ug in p['UserIdGroupPairs']) for p in db_sg['IpPermissions'])
    if not db_rule: raise Exception(f"DB SG does not allow port 5432 from Web SG ({web_sg_id}).")
    print("  [PASS] DB SG has correct inbound PostgreSQL rule from Web SG.")

    # 3. Verify EC2 Instance
    print("Verifying EC2 Instance...")
    reservations = ec2.describe_instances(Filters=[{'Name': 'tag:Name', 'Values': [INSTANCE_TAG_NAME]}])['Reservations']
    if not reservations or not reservations[0]['Instances']:
        raise Exception(f"EC2 instance with tag Name={INSTANCE_TAG_NAME} not found.")
    instance = reservations[0]['Instances'][0]
    
    if instance['State']['Name'] != 'running':
        raise Exception(f"Instance is not running. Current state: {instance['State']['Name']}.")
    print(f"  [PASS] Instance '{instance['InstanceId']}' is running.")
    
    if instance['SubnetId'] != public_subnet_id:
        raise Exception(f"Instance is in wrong subnet {instance['SubnetId']}. Expected {public_subnet_id}.")
    print("  [PASS] Instance is in the correct public subnet.")

    if 'PublicIpAddress' not in instance:
        raise Exception("Instance does not have a public IP address.")
    print(f"  [PASS] Instance has a public IP: {instance['PublicIpAddress']}")
    
    instance_sg_ids = {sg['GroupId'] for sg in instance['SecurityGroups']}
    if web_sg_id not in instance_sg_ids:
        raise Exception(f"Instance is not in the correct security group. Missing {web_sg_id}.")
    print("  [PASS] Instance is associated with the correct web security group.")

    # 4. Verify RDS Instance
    print("Verifying RDS Instance...")
    try:
        db_instances = rds.describe_db_instances(DBInstanceIdentifier=DB_IDENTIFIER)['DBInstances']
        if not db_instances:
             raise Exception(f"RDS instance with identifier '{DB_IDENTIFIER}' not found.")
        db_instance = db_instances[0]
    except rds.exceptions.DBInstanceNotFoundFault:
        raise Exception(f"RDS instance with identifier '{DB_IDENTIFIER}' not found.")

    if db_instance['DBInstanceStatus'] != 'available':
        raise Exception(f"RDS instance is not available. Current status: {db_instance['DBInstanceStatus']}.")
    print(f"  [PASS] RDS instance '{db_instance['DBInstanceIdentifier']}' is available.")
    
    if db_instance['PubliclyAccessible']:
        raise Exception("RDS instance is publicly accessible, but should be private.")
    print("  [PASS] RDS instance is correctly configured as private.")

    db_instance_sg_ids = {sg['VpcSecurityGroupId'] for sg in db_instance['VpcSecurityGroups']}
    if db_sg['GroupId'] not in db_instance_sg_ids:
        raise Exception(f"RDS instance is not in the correct security group. Missing {db_sg['GroupId']}.")
    print("  [PASS] RDS instance is associated with the correct DB security group.")

    print("\n--- All checks passed ---")


if __name__ == "__main__":
    try:
        # Allow some time for resources to become fully available in LocalStack
        time.sleep(10)
        verify_infra()
        print("\nVERIFICATION SUCCESS")
    except Exception as e:
        print(f"\nVERIFICATION FAILED: {e}")
        exit(1)
