import boto3

def s3upload_file(file_name, bucket):
    key_name = file_name
    s3_client = boto3.client('s3')
    response = s3_client.upload_file(file_name, bucket, key_name)
    return response

def get_presigned_url(bucket, s3_key): 
    s3_client = boto3.client('s3')
    presigned_url = s3_client.generate_presigned_url('get_object', Params = {'Bucket': bucket, 'Key': s3_key}, ExpiresIn = 100)
    return presigned_url    

def show_image(bucket):
    s3_client = boto3.client('s3')
    # location = boto3.client('s3').get_bucket_location(Bucket=bucket)['LocationConstraint']
    public_urls = []
    try:
        for item in s3_client.list_objects(Bucket=bucket)['Contents']:
            presigned_url = s3_client.generate_presigned_url('get_object', Params = {'Bucket': bucket, 'Key': item['Key']}, ExpiresIn = 100)
            # print("[DATA] : presigned url = ", presigned_url)
            public_urls.append(presigned_url)
    except Exception as e:
        pass
    # print("[DATA] : The contents inside show_image = ", public_urls)
    return public_urls
    
def list_files(bucket):
    s3_client = boto3.client('s3')
    contents = []
    try:
        for item in s3_client.list_objects(Bucket=bucket)['Contents']:
            # print(item)
            contents.append(item)
    except Exception as e:
        pass
    return contents
