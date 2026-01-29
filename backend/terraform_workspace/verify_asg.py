import boto3
import sys
import time

# Configure boto3 to use LocalStack
endpoint_url = "http://localhost:4566"
region = "us-east-1"

# Explicit credentials for LocalStack
boto3.setup_default_session(
    aws_access_key_id="test",
    aws_secret_access_key="test",
    region_name=region
)

asg_client = boto3.client("autoscaling", endpoint_url=endpoint_url)
ec2_client = boto3.client("ec2", endpoint_url=endpoint_url)

def verify_deployment():
    print("--- Verifying High Availability Deployment (ASG) ---")
    errors = []

    # 1. Verify Auto Scaling Group
    try:
        response = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=["web-asg"])
        groups = response['AutoScalingGroups']
        if not groups:
            errors.append("❌ Auto Scaling Group 'web-asg' not found")
        else:
            asg = groups[0]
            print(f"✅ Found ASG: {asg['AutoScalingGroupName']}")
            print(f"   Desired Capacity: {asg['DesiredCapacity']}")
            
            # Check instances
            instances = asg['Instances']
            if len(instances) != 2:
                errors.append(f"❌ Expected 2 instances in ASG, found {len(instances)}")
            else:
                print(f"✅ Verified 2 instances in ASG")
                
                # Verify Multi-AZ
                instance_ids = [i['InstanceId'] for i in instances]
                ec2_resp = ec2_client.describe_instances(InstanceIds=instance_ids)
                azs = set()
                for r in ec2_resp['Reservations']:
                    for i in r['Instances']:
                         azs.add(i['Placement']['AvailabilityZone'])
                         print(f"   - Instance {i['InstanceId']} in {i['Placement']['AvailabilityZone']} ({i['State']['Name']})")
                
                if len(azs) < 2:
                    errors.append(f"⚠️ Warning: Instances should be in different AZs. Found: {azs}")
                else:
                    print(f"✅ Verified Multi-AZ Distribution: {azs}")

    except Exception as e:
        errors.append(f"❌ API Error checking ASG: {e}")

    # 2. Verify VPC and Security Group
    try:
        vpcs = ec2_client.describe_vpcs(Filters=[{'Name': 'tag:Name', 'Values': ['ha_vpc']}])['Vpcs']
        if vpcs:
            print("✅ Verified VPC 'ha_vpc'")
        else:
            errors.append("❌ VPC 'ha_vpc' not found")
            
        sgs = ec2_client.describe_security_groups(Filters=[{'Name': 'group-name', 'Values': ['web-server-sg']}])['SecurityGroups']
        if sgs:
            print("✅ Verified Security Group 'web-server-sg'")
        else:
            errors.append("❌ Security Group 'web-server-sg' not found")

    except Exception as e:
        errors.append(f"❌ API Error checking Network: {e}")

    if errors:
        print("\n❌ Verification Failed with errors:")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print("\n✅ All Checks Passed! High Availability Architecture is Active.")
        sys.exit(0)

if __name__ == "__main__":
    verify_deployment()
