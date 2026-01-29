import boto3
import sys
import time

# Configure boto3 to use LocalStack
endpoint_url = "http://localhost:4566"
region = "us-east-1"

ec2 = boto3.client("ec2", endpoint_url=endpoint_url, region_name=region)

def test_infra():
    print("Starting Infrastructure Verification (Fallback Mode)...")
    errors = []

    # 1. Verify VPC
    vpcs = ec2.describe_vpcs(Filters=[{'Name': 'tag:Name', 'Values': ['main-vpc']}])['Vpcs']
    if not vpcs:
        errors.append("VPC 'main-vpc' not found")
    else:
        print("✅ VPC found")
        vpc_id = vpcs[0]['VpcId']

        # 2. Verify Subnets
        subnets = ec2.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])['Subnets']
        if len(subnets) != 2:
             errors.append(f"Expected 2 subnets, found {len(subnets)}")
        else:
             print(f"✅ Found {len(subnets)} subnets")

    # 3. Verify Instances
    instances = ec2.describe_instances(Filters=[{'Name': 'tag:Name', 'Values': ['web-instance-*']}])
    
    clean_instances = []
    for r in instances['Reservations']:
        for i in r['Instances']:
            if i['State']['Name'] in ['running', 'pending']:
                clean_instances.append(i)

    if len(clean_instances) != 2:
        errors.append(f"Expected 2 running instances, found {len(clean_instances)}")
    else:
        print(f"✅ Found {len(clean_instances)} instances")
        # Check AZ distribution
        azs = set(i['Placement']['AvailabilityZone'] for i in clean_instances)
        if len(azs) < 2:
            print(f"⚠️ Warning: Instances are not Multi-AZ (Found in: {azs})")
        else:
            print(f"✅ Multi-AZ verified: {azs}")

    if errors:
        print("\n❌ Verification Failed with errors:")
        for e in errors:
            print(f" - {e}")
        sys.exit(1)
    else:
        print("\n✅ Infrastructure Validation Passed!")
        sys.exit(0)

if __name__ == "__main__":
    try:
        test_infra()
    except Exception as e:
        print(f"❌ Script failed: {e}")
        sys.exit(1)
