import unittest

from fastapi.testclient import TestClient

import app.web.app as web_app


class WebSecurityHeadersTests(unittest.TestCase):
    def test_web_security_headers_cover_embedding_and_content_sniffing(self):
        self.assertTrue(hasattr(web_app, "WEB_SECURITY_HEADERS"))

        headers = web_app.WEB_SECURITY_HEADERS
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

        response = TestClient(web_app.app).get("/not-found")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
