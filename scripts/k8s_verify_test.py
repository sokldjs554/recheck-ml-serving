"""Negative controls for the operational evidence success criterion."""
import unittest
from k8s_verify import assert_current_clear


class EvidenceContractTests(unittest.TestCase):
    @staticmethod
    def responder(status="clear", valid=True):
        def request(path, body=None):
            if path == "/api/sessions":
                return {"session_id": "isolated-test"}
            if path.endswith("/validate"):
                return {"valid": valid}
            return {"id": "receipt-test", "status": status, "model_hash": "hash-test", "trace_id": "trace-test"}
        return request

    def test_current_clear_passes(self):
        self.assertTrue(assert_current_clear(self.responder())["valid"])

    def test_http_200_review_is_not_success(self):
        with self.assertRaises(AssertionError):
            assert_current_clear(self.responder(status="review"))

    def test_clear_but_stale_is_not_success(self):
        with self.assertRaises(AssertionError):
            assert_current_clear(self.responder(valid=False))


if __name__ == "__main__":
    unittest.main()
