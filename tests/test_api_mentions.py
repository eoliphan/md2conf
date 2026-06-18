import unittest

from md2conf.api import ConfluenceUser


class TestConfluenceUser(unittest.TestCase):
    def test_dataclass_fields(self) -> None:
        user = ConfluenceUser(email="alice@example.com", csf_attr="ri:account-id", csf_value="557058:abc")
        self.assertEqual(user.email, "alice@example.com")
        self.assertEqual(user.csf_attr, "ri:account-id")
        self.assertEqual(user.csf_value, "557058:abc")

    def test_none_email(self) -> None:
        user = ConfluenceUser(email=None, csf_attr="ri:username", csf_value="jsmith")
        self.assertIsNone(user.email)
