"""Unit tests for Phase 2 helpers that do not need a site DB."""

from __future__ import annotations

import unittest

from nudg.utils.conversation_status import conversation_status
from nudg.utils.errors import format_error_message


class TestPhase2Helpers(unittest.TestCase):
	def test_error_and_status_helpers(self):
		self.assertEqual(
			format_error_message('{"error":{"message":"Authentication Error","code":190}}'),
			"Error sending",
		)
		self.assertEqual(
			conversation_status(
				{"status": "Active"},
				{"direction": "Incoming", "status": "Delivered"},
				{"status": "open"},
			),
			"needs_reply",
		)

	def test_catalog_adapter_is_isolated(self):
		from pathlib import Path

		import nudg

		root = Path(nudg.__file__).resolve().parent
		source = (root / "integrations/whatsapp/catalog_adapter.py").read_text()
		self.assertIn("Meta Commerce Catalog sync is not enabled", source)
		self.assertNotIn("graph.facebook.com", source)


if __name__ == "__main__":
	unittest.main()
