# Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for how to report security issues.

## Bastion Host Access

The CloudFormation template (`templates/infrastructure.yaml`) creates a Windows bastion host with RDP (port 3389) open to private networks (`10.0.0.0/8`). This is intentional for database administration access but should be hardened for production use:

- **Restrict the CIDR range** to your specific corporate IP range or VPN subnet instead of the broad `10.0.0.0/8` block
- **Use AWS Systems Manager Session Manager** as an alternative to RDP — it requires no open inbound ports
- **Enable CloudTrail logging** to audit bastion access
- **Consider time-limited access** using AWS IAM Identity Center or temporary security group rules

To restrict RDP access, update the `BastionSecurityGroup` ingress rule in `templates/infrastructure.yaml`:

```yaml
SecurityGroupIngress:
  - IpProtocol: tcp
    FromPort: 3389
    ToPort: 3389
    CidrIp: <your-specific-cidr>/32   # e.g., 10.1.2.100/32
    Description: RDP from specific admin IP
```

## S3 Backup Bucket

The S3 backup bucket (`SqlBackupLogBucket`) is created with default settings for simplicity. For production use, consider enabling:

- Access logging
- Versioning
- SSL-only bucket policy

These are not enabled by default as this is sample code intended for learning and experimentation.
