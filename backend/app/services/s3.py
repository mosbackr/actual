import boto3
from botocore.exceptions import ClientError
from app.config import settings


def _get_client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )


def upload_file(file_data: bytes, s3_key: str) -> str:
    client = _get_client()
    client.put_object(Bucket=settings.s3_bucket_name, Key=s3_key, Body=file_data)
    return s3_key


def download_file(s3_key: str) -> bytes:
    client = _get_client()
    response = client.get_object(Bucket=settings.s3_bucket_name, Key=s3_key)
    return response["Body"].read()


def delete_file(s3_key: str) -> None:
    client = _get_client()
    try:
        client.delete_object(Bucket=settings.s3_bucket_name, Key=s3_key)
    except ClientError:
        pass


def delete_files(s3_keys: list[str]) -> None:
    if not s3_keys:
        return
    client = _get_client()
    objects = [{"Key": key} for key in s3_keys]
    client.delete_objects(Bucket=settings.s3_bucket_name, Delete={"Objects": objects})


def generate_presigned_upload_url(s3_key: str, content_type: str, expires_in: int = 3600) -> str:
    """Generate a presigned URL for direct client-side upload to S3."""
    client = _get_client()
    url = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_bucket_name,
            "Key": s3_key,
            "ContentType": content_type,
        },
        ExpiresIn=expires_in,
    )
    return url
