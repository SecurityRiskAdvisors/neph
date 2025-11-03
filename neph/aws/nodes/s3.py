from ...nodes import BaseGraphNode


class S3Bucket(BaseGraphNode):
    table = "aws_s3_bucket"
    id = "arn"
    label = "S3Bucket"
