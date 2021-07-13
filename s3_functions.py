import boto3

def s3upload_file(file_name, bucket):
    key_name = file_name
    s3_client = boto3.client('s3')
    response = s3_client.upload_file(file_name, bucket, key_name)
    return response
