import unittest
import json

from neph.aws.policies import get_allowed_actions_from_policy


# TODO: break out by action/effect types/combos
class GetActionsTest(unittest.TestCase):
    def test_get_actions_std_policy_1(self):
        # normal looking policy with a few allows
        policy = json.loads(
            """
        {"Version": "2012-10-17", "Statement": [{"Sid": "VisualEditor0", "Action": ["dynamodb:Scan", "logs:CreateLogGroup"], "Effect": "Allow", "Resource": ["arn:aws:dynamodb:us-east-1:123456789012:table/*_secrets", "arn:aws:dynamodb:us-east-1:123456789012:table/*_github", "arn:aws:logs:us-east-1:123456789012:*"]}, {"Sid": "VisualEditor1", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"], "Effect": "Allow", "Resource": "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/abcd:*"}]}
        """
        )
        actions = get_allowed_actions_from_policy(policy)

        # should be in allowed actions
        self.assertIn("dynamodb:Scan", actions)
        self.assertIn("logs:CreateLogGroup", actions)

        # real permission, not in policy
        self.assertNotIn("iam:CreateUser", actions)
        # fake permission, not in policy
        self.assertNotIn("dynamodb:DoestExist", actions)

    def test_get_actions_denyonly_1(self):
        policy = json.loads(
            """
        {"Version": "2012-10-17", "Statement": [{"Sid": "VisualEditor0", "Action": ["iam:CreateUser"], "Effect": "Deny", "Resource": ["*"]}]}
        """
        )
        actions = get_allowed_actions_from_policy(policy)

        # should be an empty set since the policy only has a deny
        self.assertEqual(actions, set())

    def test_get_actions_denyallow_all(self):
        # deny * and allow *
        policy = json.loads(
            """
        {"Version": "2012-10-17", "Statement": [{"Sid": "VisualEditor0", "Action": "*", "Effect": "Deny", "Resource": ["*"]}, {"Sid": "VisualEditor1", "Action": "*", "Effect": "Allow", "Resource": ["*"]}]}
        """
        )
        actions = get_allowed_actions_from_policy(policy)

        # should be an empty set since denies override allows
        self.assertEqual(actions, set())

    def test_get_actions_notaction_allow_1(self):
        policy = json.loads(
            """
        {"Version": "2012-10-17", "Statement": [{"Sid": "VisualEditor0", "NotAction": ["iam:CreateUser"], "Effect": "Allow", "Resource": ["*"]}]}
        """
        )
        actions = get_allowed_actions_from_policy(policy)

        # the permissions should be the only item not in the list
        self.assertNotIn("iam:CreateUser", actions)
        # and the list should have everything else
        #   should be around 20k
        self.assertGreater(len(actions), 100)

    def test_get_actions_notaction_deny_1(self):
        policy = json.loads(
            """
        {"Version": "2012-10-17", "Statement": [{"Sid": "VisualEditor0", "NotAction": ["iam:CreateUser"], "Effect": "Deny", "Resource": ["*"]}]}
        """
        )
        actions = get_allowed_actions_from_policy(policy)

        # only denies in policy, so it should be empty
        self.assertEqual(actions, set())

    def test_get_actions_notaction_deny_2(self):
        policy = json.loads(
            """
        {"Version": "2012-10-17", "Statement": [{"Sid": "VisualEditor0", "NotAction": ["iam:CreateUser"], "Effect": "Deny", "Resource": ["*"]}, {"Sid": "VisualEditor1", "Action": ["iam:*"], "Effect": "Allow", "Resource": ["*"]}]}
        """
        )
        actions = get_allowed_actions_from_policy(policy)

        # allow all IAM actions then deny not action createuser
        # should have an effective allow of only createuser
        self.assertIn("iam:CreateUser", actions)
        self.assertEqual(len(actions), 1)

    def test_get_actions_notaction_allow_2(self):
        policy = json.loads(
            """
        {"Version": "2012-10-17", "Statement": [{"Sid": "VisualEditor0", "NotAction": ["iam:*"], "Effect": "Allow", "Resource": ["*"]}]}
        """
        )
        actions = get_allowed_actions_from_policy(policy)

        # should not contain any IAM permissions
        self.assertNotIn("iam:CreateUser", actions)
        # but the list should have everything else
        self.assertGreater(len(actions), 100)


if __name__ == "__main__":
    unittest.main()
