from ...nodes import BaseGraphNode


class SecretsManagerSecret(BaseGraphNode):
    table = "aws_secretsmanager_secret"
    id = "arn"
    label = "SecretsManagerSecret"
