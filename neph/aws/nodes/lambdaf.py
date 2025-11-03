from ...nodes import BaseGraphNode


class LambdaFunction(BaseGraphNode):
    table = "aws_lambda_function"
    id = "arn"
    label = "LambdaFunction"
