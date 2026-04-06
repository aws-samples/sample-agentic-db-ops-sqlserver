#!/usr/bin/env python3
"""Validate infrastructure prerequisites before deploying AgentCore agents.

Run this if you're using Option B (existing RDS SQL Server) to verify
networking, security groups, RDS configuration, and secrets are set up
correctly before deploying VPC endpoints and agents.

Usage:
    source .env && source .venv/bin/activate
    python3 scripts/validate_prerequisites.py
"""
import boto3
import json
import os
import sys

REGION = os.environ.get("AWS_REGION", "us-east-1")
DB_INSTANCE_ID = os.environ.get("DB_INSTANCE_ID", "")
DB_SECRET_ID = os.environ.get("DB_SECRET_ID", "")
SECURITY_GROUP_ID = os.environ.get("SECURITY_GROUP_ID", "")
SUBNET1 = os.environ.get("SUBNET1", "")

passed = 0
failed = 0
warnings = 0


def check(name, ok, msg_pass, msg_fail, warn=False):
    global passed, failed, warnings
    if ok:
        print(f"  ✅ {name}: {msg_pass}")
        passed += 1
    elif warn:
        print(f"  ⚠️  {name}: {msg_fail}")
        warnings += 1
    else:
        print(f"  ❌ {name}: {msg_fail}")
        failed += 1


def validate_env_vars():
    print("\n🔧 Environment Variables")
    print("=" * 60)
    required = {
        "DB_INSTANCE_ID": DB_INSTANCE_ID,
        "DB_SECRET_ID": DB_SECRET_ID,
        "SECURITY_GROUP_ID": SECURITY_GROUP_ID,
        "SUBNET1": SUBNET1,
        "AWS_REGION": REGION,
    }
    for var, val in required.items():
        check(var, bool(val), f"set ({val[:40]}{'...' if len(val) > 40 else ''})", "not set — add to .env")


def validate_subnet():
    print("\n🌐 Networking — Private Subnet")
    print("=" * 60)
    if not SUBNET1:
        check("Subnet", False, "", "SUBNET1 not set, skipping")
        return None

    ec2 = boto3.client("ec2", region_name=REGION)
    try:
        resp = ec2.describe_subnets(SubnetIds=[SUBNET1])
        subnet = resp["Subnets"][0]
        vpc_id = subnet["VpcId"]
        az = subnet["AvailabilityZone"]
        is_public = subnet.get("MapPublicIpOnLaunch", False)

        check("Subnet exists", True, f"{SUBNET1} in {az} (VPC: {vpc_id})", "")
        check("Private subnet", not is_public,
              "MapPublicIpOnLaunch=false (private)",
              "MapPublicIpOnLaunch=true — agents must run in private subnets")

        # Check route table for NAT or internet gateway
        rt_resp = ec2.describe_route_tables(
            Filters=[{"Name": "association.subnet-id", "Values": [SUBNET1]}]
        )
        if not rt_resp["RouteTables"]:
            rt_resp = ec2.describe_route_tables(
                Filters=[{"Name": "vpc-id", "Values": [vpc_id]},
                         {"Name": "association.main", "Values": ["true"]}]
            )

        has_nat = False
        has_igw = False
        route_table_id = None
        if rt_resp["RouteTables"]:
            rt = rt_resp["RouteTables"][0]
            route_table_id = rt["RouteTableId"]
            for route in rt.get("Routes", []):
                if route.get("NatGatewayId"):
                    has_nat = True
                if route.get("GatewayId", "").startswith("igw-"):
                    dest = route.get("DestinationCidrBlock", "")
                    if dest == "0.0.0.0/0":
                        has_igw = True

        if has_nat:
            check("Outbound access", True,
                  f"NAT gateway found (route table: {route_table_id}) — VPC endpoints optional but recommended",
                  "", warn=True)
        elif has_igw:
            check("Outbound access", False, "",
                  "Default route points to IGW — this is a public subnet, agents need a private subnet")
        else:
            check("Outbound access", True,
                  f"No NAT/IGW (route table: {route_table_id}) — VPC endpoints required",
                  "")

        return vpc_id
    except Exception as e:
        check("Subnet lookup", False, "", f"Error: {e}")
        return None


def validate_security_group(vpc_id):
    print("\n🔒 Networking — Security Groups")
    print("=" * 60)
    if not SECURITY_GROUP_ID:
        check("Agent SG", False, "", "SECURITY_GROUP_ID not set, skipping")
        return

    ec2 = boto3.client("ec2", region_name=REGION)
    try:
        resp = ec2.describe_security_groups(GroupIds=[SECURITY_GROUP_ID])
        sg = resp["SecurityGroups"][0]
        sg_vpc = sg["VpcId"]

        check("Agent SG exists", True, f"{SECURITY_GROUP_ID} in VPC {sg_vpc}", "")
        check("Same VPC", sg_vpc == vpc_id if vpc_id else True,
              f"Matches subnet VPC ({vpc_id})",
              f"VPC mismatch — SG is in {sg_vpc}, subnet is in {vpc_id}")

        # Check outbound rules for port 443
        has_443_outbound = False
        has_all_outbound = False
        for rule in sg.get("IpPermissionsEgress", []):
            proto = rule.get("IpProtocol", "")
            if proto == "-1":
                has_all_outbound = True
            from_port = rule.get("FromPort", 0)
            to_port = rule.get("ToPort", 0)
            if proto == "tcp" and from_port <= 443 <= to_port:
                has_443_outbound = True

        check("Outbound 443", has_443_outbound or has_all_outbound,
              "Allows outbound HTTPS (443) to AWS services",
              "No outbound rule for port 443 — agents need this to reach AWS services via VPC endpoints")

        # Check if agent SG is allowed inbound 1433 on any RDS security group
        if DB_INSTANCE_ID:
            rds = boto3.client("rds", region_name=REGION)
            try:
                db_resp = rds.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
                db_sgs = [sg["VpcSecurityGroupId"] for sg in
                          db_resp["DBInstances"][0].get("VpcSecurityGroups", [])]

                if db_sgs:
                    rds_sg_resp = ec2.describe_security_groups(GroupIds=db_sgs)
                    agent_allowed = False
                    for rds_sg in rds_sg_resp["SecurityGroups"]:
                        for rule in rds_sg.get("IpPermissions", []):
                            from_port = rule.get("FromPort", 0)
                            to_port = rule.get("ToPort", 0)
                            if from_port <= 1433 <= to_port:
                                for pair in rule.get("UserIdGroupPairs", []):
                                    if pair.get("GroupId") == SECURITY_GROUP_ID:
                                        agent_allowed = True

                    check("RDS inbound 1433", agent_allowed,
                          f"RDS SG ({', '.join(db_sgs)}) allows inbound 1433 from agent SG",
                          f"RDS SG ({', '.join(db_sgs)}) does not allow inbound 1433 from {SECURITY_GROUP_ID} — "
                          "agents won't be able to connect to SQL Server")
            except Exception as e:
                check("RDS SG check", False, "", f"Error checking RDS security groups: {e}", warn=True)

    except Exception as e:
        check("Agent SG lookup", False, "", f"Error: {e}")


def validate_rds():
    print("\n🗄️  RDS SQL Server Configuration")
    print("=" * 60)
    if not DB_INSTANCE_ID:
        check("RDS instance", False, "", "DB_INSTANCE_ID not set, skipping")
        return

    rds = boto3.client("rds", region_name=REGION)
    try:
        resp = rds.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        db = resp["DBInstances"][0]

        engine = db.get("Engine", "")
        engine_ver = db.get("EngineVersion", "")
        status = db.get("DBInstanceStatus", "")

        check("RDS instance", True, f"{DB_INSTANCE_ID} ({engine} {engine_ver}) — {status}", "")
        check("Engine is SQL Server", "sqlserver" in engine,
              f"Engine: {engine}",
              f"Engine is {engine} — this toolkit is designed for SQL Server")

        # Database Insights (Performance Insights)
        pi_enabled = db.get("PerformanceInsightsEnabled", False)
        pi_retention = db.get("PerformanceInsightsRetentionPeriod", 0)
        check("Database Insights", pi_enabled,
              f"Enabled (retention: {pi_retention} days)",
              "Not enabled — Database Health Agent needs this for load analysis, wait events, and top SQL")
        if pi_enabled and pi_retention < 7:
            check("DI retention", False, "",
                  f"Retention is {pi_retention} day(s) — recommend 7 days for meaningful trend analysis",
                  warn=True)

        # CloudWatch Logs exports
        log_exports = db.get("EnabledCloudwatchLogsExports", [])
        has_error = "error" in log_exports
        has_agent = "agent" in log_exports
        check("CW Logs: error", has_error,
              "Error log export enabled",
              "Error log export not enabled — Security Audit Agent uses this for failed login detection")
        check("CW Logs: agent", has_agent,
              "Agent log export enabled",
              "Agent log export not enabled — recommended for Security Audit Agent",
              warn=True)

        # Check if publicly accessible
        public = db.get("PubliclyAccessible", False)
        check("Not public", not public,
              "PubliclyAccessible=false",
              "PubliclyAccessible=true — consider disabling for security",
              warn=True)

        # Storage encryption
        encrypted = db.get("StorageEncrypted", False)
        check("Storage encrypted", encrypted,
              "Storage encryption enabled",
              "Storage encryption not enabled — recommended for security",
              warn=True)

    except rds.exceptions.DBInstanceNotFoundFault:
        check("RDS instance", False, "", f"Instance '{DB_INSTANCE_ID}' not found in {REGION}")
    except Exception as e:
        check("RDS instance", False, "", f"Error: {e}")


def validate_secret():
    print("\n🔑 Secrets Manager")
    print("=" * 60)
    if not DB_SECRET_ID:
        check("Secret", False, "", "DB_SECRET_ID not set, skipping")
        return

    sm = boto3.client("secretsmanager", region_name=REGION)
    try:
        resp = sm.get_secret_value(SecretId=DB_SECRET_ID)
        secret_str = resp.get("SecretString", "")
        try:
            secret = json.loads(secret_str)
            has_username = "username" in secret
            has_password = "password" in secret
            keys = list(secret.keys())

            check("Secret exists", True, f"{DB_SECRET_ID}", "")
            check("Has username", has_username,
                  f"username key present (value: {secret['username'][:3]}***)",
                  "Missing 'username' key — agents need this to connect to SQL Server")
            check("Has password", has_password,
                  "password key present",
                  "Missing 'password' key — agents need this to connect to SQL Server")

            extra_keys = [k for k in keys if k not in ("username", "password")]
            if extra_keys:
                print(f"       ℹ️  Additional keys in secret: {extra_keys}")

        except json.JSONDecodeError:
            check("Secret format", False, "", "Secret is not valid JSON — expected {\"username\": ..., \"password\": ...}")

    except sm.exceptions.ResourceNotFoundException:
        check("Secret exists", False, "", f"Secret '{DB_SECRET_ID}' not found in {REGION}")
    except Exception as e:
        check("Secret access", False, "", f"Error: {e}")


def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   DBOps Agent Prerequisites Validator                   ║")
    print("╚══════════════════════════════════════════════════════════╝")

    validate_env_vars()
    vpc_id = validate_subnet()
    validate_security_group(vpc_id)
    validate_rds()
    validate_secret()

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed, {warnings} warnings")
    print("=" * 60)

    if failed > 0:
        print(f"\n❌ {failed} check(s) failed — fix these before deploying agents.")
        sys.exit(1)
    elif warnings > 0:
        print(f"\n⚠️  All required checks passed, but {warnings} warning(s) to review.")
        print("   You can proceed with deployment.")
    else:
        print("\n✅ All checks passed — ready to deploy VPC endpoints and agents.")


if __name__ == "__main__":
    main()
