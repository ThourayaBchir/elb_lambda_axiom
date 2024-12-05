import os
import boto3
import requests
import gzip
import logging
import re

from datetime import datetime
from typing import Dict, Any


logger = logging.getLogger()
logger.setLevel(logging.INFO)


def parse_elb_log(log_line: str) -> Dict[str, Any]:
    # Normalize the log line to hide instance-specific details
    log_line = re.sub(r'app/k8s-default-ingressn-[a-z0-9]+/[a-z0-9]+', 
                      'app/k8s-default-ingress', 
                      log_line)
    
    pattern = r'''
        (?P<type>\S+)\s
        (?P<time>\S+)\s
        \S+\s  # Skip ELB name
        (?P<client_port>\S+)\s
        (?P<target_port>\S+|-)\s
        (?P<request_processing_time>-?\d+|-)\s
        (?P<target_processing_time>-?\d+|-)\s
        (?P<response_processing_time>-?\d+|-)\s
        (?P<elb_status_code>\d+|-)\s
        (?P<target_status_code>\S+)\s
        (?P<received_bytes>\d+|-)\s
        (?P<sent_bytes>\d+)\s
        "(?P<request>(?P<method>\S+)\s(?P<url>\S+)\s(?P<protocol>\S+))"\s
        "(?P<user_agent>[^"]*)"\s
        (?P<ssl_cipher>\S+)\s
        (?P<ssl_protocol>\S+)\s
        (?P<target_group_arn>\S+)\s
        "(?P<trace_id>[^"]*)"\s
        "(?P<domain_name>[^"]*)"\s
        \S+\s  # Skip cert ARN
        (?P<matched_rule_priority>\S+)\s
        (?P<request_creation_time>\S+)\s
        "(?P<actions_executed>[^"]*)"\s
        "(?P<redirect_url>[^"]*)"\s
        "(?P<error_reason>[^"]*)"\s
        "(?P<target_port_list>[^"]*)"\s
        "(?P<target_status_code_list>[^"]*)"\s
        "(?P<classification>[^"]*)"\s
        "(?P<classification_reason>[^"]*)"\s
        (?P<tid>\S+)
    '''
    match = re.match(pattern, log_line, re.VERBOSE)
    
    if not match:
        return {"_time": "", "data": {"error": "Failed to parse log line"}}
    
    result = match.groupdict()
    
    # Format timestamp
    try:
        time = datetime.strptime(result['time'], "%Y-%m-%dT%H:%M:%S.%fZ")
        iso_time = time.isoformat() + "Z"
    except ValueError:
        iso_time = result['time']
    
    # Split client and target addresses
    result['client'], result['client_port'] = result['client_port'].rsplit(':', 1) if ':' in result['client_port'] else (result['client_port'], "")
    result['target'], result['target_port'] = result['target_port'].rsplit(':', 1) if ':' in result['target_port'] else (result['target_port'], "")
    
    # Extract service name
    result['service'] = result['target_group_arn'].split('/')[-1] if result['target_group_arn'] != '-' else ''
    del result['target_group_arn']
    
    # Clean up fields
    del result['time']
    
    # Normalize empty values
    for key, value in result.items():
        result[key] = '' if value == '-' else str(value)
    
    # Store sanitized raw log
    result['raw_log'] = log_line.replace(os.environ.get("CERT_ARN", ""), "CERT_ARN").replace(os.environ.get("ACCOUNT_ID", ""), "ACCOUNT_ID")
    
    return {
        "_time": iso_time,
        **result
    }

def lambda_handler(event, context):
    s3 = boto3.client('s3')
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    
    try:
        # Get and process log file
        obj = s3.get_object(Bucket=bucket, Key=key)
        json_logs = []
        
        with gzip.GzipFile(fileobj=obj['Body']) as gzipfile:
            for line in gzipfile:
                log_entry = parse_elb_log(line.decode('utf-8'))
                json_logs.append(log_entry)
        
        # Prepare Axiom ingestion
        dataset_name = os.environ['DATASET_NAME']
        axiom_headers = {
            "Authorization": f"Bearer {os.environ['AXIOM_API_TOKEN']}",
            "Content-Type": "application/json"
        }
        
        # Send logs in batches
        batch_size = 50
        for i in range(0, len(json_logs), batch_size):
            batch = json_logs[i:i + batch_size]
            response = requests.post(
                f"https://api.axiom.co/v1/datasets/{dataset_name}/ingest",
                headers=axiom_headers,
                json=batch
            )
            if response.status_code != 200:
                logger.info(f"Batch {i//batch_size + 1} failed: {response.status_code}")
        
        return {"statusCode": 200, "message": f"Processed {len(json_logs)} logs"}
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise
