connection "aws" {
    plugin = "aws"
    profile = "steampipe"
    regions = ["us-east-*"]
    ignore_error_codes = ["AccessDenied", "AccessDeniedException", "NotAuthorized", "UnauthorizedOperation", "UnrecognizedClientException", "AuthorizationError"]
}