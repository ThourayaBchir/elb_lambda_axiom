# Streaming AWS ELB Logs to Axiom via Lambda

Forward AWS Elastic Load Balancer logs to Axiom for analysis using a Lambda function.

## Prerequisites
- Axiom account and API token
- AWS account with Lambda, S3, and ELB access
- ELB with access logging enabled

## Setup

### 1. Enable ELB Logging
Via AWS Console:
- Go to ELB → Attributes
- Enable access logging
- Select S3 bucket


### 2. Deploy Lambda
```python
# See lambda_function.py for the code
```

### 3. Configure Lambda
```bash
pip install requests -t .
zip -r function.zip .
```

Environment variables:
- `AXIOM_API_TOKEN`
- `AXIOM_DATASET_NAME`
- `DATASET_NAME`


### 4. Set Up Trigger
Add S3 trigger:
- Select ELB logs bucket
- Event: ObjectCreated

### 5. IAM Permissions
Add to Lambda role:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject"
            ],
            "Resource": "arn:aws:s3:::your-elb-logs-bucket/*"
        }
    ]
}
```

## License
MIT
