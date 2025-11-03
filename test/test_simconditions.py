import unittest
import json
import pathlib

from neph.sim import suggest_condition


class ConditionSuggestionsUnitTest(unittest.TestCase):
    def get_json_data(self, file_name: str = None):
        # load the json file matching the provided file name or fall back to the test case
        file_name = file_name if file_name else self._testMethodName
        return json.loads(pathlib.Path(f"simresults/{file_name}.json").read_text())


# TODO: resource analysis
class ConditionSuggestions(ConditionSuggestionsUnitTest):
    def test_implicitdeny_allowcondition_valuedict_1(self):
        # results from an allow policy with a single condition value
        # where the request did not contain the condition key
        results = self.get_json_data()
        suggestions = suggest_condition(results)

        # expect the condition key from the results in the suggestions
        self.assertIn("iam:PermissionsBoundary", suggestions)
        # but not an arbitrary one
        self.assertNotIn("aws:PrincipalOrgID", suggestions)

        values = suggestions.get("iam:PermissionsBoundary")
        # should only be 1 suggested value based on the condition value being a dict
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0], "arn:aws:iam::*:policy/boundary")

    def test_implicitdeny_allowcondition_valuelist_1(self):
        # results from an allow policy with multiple condition values
        # where the request did not contain one of the condition keys
        results = self.get_json_data()
        suggestions = suggest_condition(results)

        # expect the condition key from the results in the suggestions
        self.assertIn("iam:PermissionsBoundary", suggestions)
        # but not an arbitrary one
        self.assertNotIn("aws:PrincipalOrgID", suggestions)

        values = suggestions.get("iam:PermissionsBoundary")
        # should be 2 suggested value based on the condition value being a dict
        self.assertEqual(len(values), 2)
        self.assertEqual(values[0], "arn:aws:iam::*:policy/boundary1")

    def test_explicitdeny_valuedict_1(self):
        # results from a policy with a deny containing a condition
        # where the request did not contain the condition key
        results = self.get_json_data()
        suggestions = suggest_condition(results)

        # expect the condition key from the results in the suggestions
        self.assertIn("aws:SecureTransport", suggestions)
        # but not an arbitrary one
        self.assertNotIn("aws:PrincipalOrgID", suggestions)

        values = suggestions.get("aws:SecureTransport")
        # should only be 1 suggested value based on the condition value being a dict
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0], "false")

    def test_allow_nosuggestions_1(self):
        # results from a simulation that was allowed
        results = self.get_json_data()
        suggestions = suggest_condition(results)

        # expect no suggestions for an allowed outcome
        self.assertIsNone(suggestions)


if __name__ == "__main__":
    unittest.main()
