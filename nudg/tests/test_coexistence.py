# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

from __future__ import annotations

import unittest
from unittest.mock import patch

from nudg.integrations import coexistence
from nudg.integrations import embedded_signup


class TestCoexistence(unittest.TestCase):
	def test_business_app_event_skips_cloud_registration(self):
		self.assertTrue(coexistence.on_business_app(False, "CLOUD_API", signup_event=True))

	def test_phone_on_the_business_app_is_coexistence(self):
		self.assertTrue(coexistence.on_business_app(True, "CLOUD_API"))
		self.assertTrue(coexistence.on_business_app(False, "SMB"))
		self.assertFalse(coexistence.on_business_app(False, "CLOUD_API"))

	def test_history_keeps_who_sent_each_message(self):
		parsed = coexistence.parse_history({
			"metadata": {"display_phone_number": "15550783881", "phone_number_id": "1065"},
			"history": [{
				"metadata": {"phase": 0, "chunk_order": 1, "progress": 55},
				"threads": [{
					"id": "16505551234",
					"messages": [
						{
							"from": "15550783881",
							"id": "wamid.out",
							"timestamp": "1739230955",
							"type": "text",
							"text": {"body": "Here is the update"},
							"history_context": {"status": "READ"},
						},
						{
							"from": "16505551234",
							"id": "wamid.in",
							"timestamp": "1739230970",
							"type": "text",
							"text": {"body": "Thanks"},
							"history_context": {"status": "READ"},
						},
						{
							"from": "15550783881",
							"id": "wamid.media",
							"timestamp": "1739230971",
							"type": "media_placeholder",
							"history_context": {"status": "PLAYED"},
						},
					],
				}],
			}],
		})
		by_id = {row["message_id"]: row for row in parsed["messages"]}
		self.assertEqual(parsed["progress"], 55)
		self.assertFalse(parsed["declined"])
		self.assertEqual(by_id["wamid.out"]["direction"], "Outgoing")
		self.assertEqual(by_id["wamid.out"]["status"], "Read")
		self.assertEqual(by_id["wamid.in"]["direction"], "Incoming")
		self.assertEqual(by_id["wamid.media"]["content"], "[Media]")

	def test_media_follow_up_can_replace_a_placeholder(self):
		parsed = coexistence.parse_history({
			"metadata": {"display_phone_number": "15550783881", "phone_number_id": "1065"},
			"messages": [{
				"from": "16505551234",
				"id": "wamid.media",
				"timestamp": "1738796547",
				"type": "image",
				"image": {"caption": "Black Prince", "id": "2423"},
			}],
		})
		row = parsed["messages"][0]
		self.assertEqual(row["content"], "Black Prince")
		self.assertTrue(row["fill_only"])
		self.assertTrue(coexistence._should_fill("[Media]", "Black Prince"))
		self.assertFalse(coexistence._should_fill("Already here", "Black Prince"))

	def test_declined_history_is_marked(self):
		parsed = coexistence.parse_history({
			"history": [{
				"errors": [{
					"code": 2593109,
					"title": "History sync is turned off by the business from the WhatsApp Business App",
				}],
			}],
		})
		self.assertTrue(parsed["declined"])
		self.assertEqual(parsed["messages"], [])

	def test_phone_echo_is_outgoing(self):
		rows = coexistence.parse_echoes({
			"message_echoes": [{
				"from": "15550783881",
				"to": "16505551234",
				"id": "wamid.echo",
				"timestamp": "1700255121",
				"type": "text",
				"text": {"body": "Sent from the phone"},
			}],
		})
		self.assertEqual(rows[0]["direction"], "Outgoing")
		self.assertEqual(rows[0]["customer"], "16505551234")
		self.assertEqual(rows[0]["content"], "Sent from the phone")

	def test_contact_remove_is_separate_from_add(self):
		rows = coexistence.parse_contacts({
			"state_sync": [
				{
					"type": "contact",
					"action": "add",
					"contact": {"full_name": "Pablo Morales", "phone_number": "16505551234"},
				},
				{"type": "contact", "action": "remove", "contact": {"phone_number": "16505551234"}},
			],
		})
		self.assertEqual(rows[0]["name"], "Pablo Morales")
		self.assertEqual(rows[1]["action"], "remove")

	@patch("nudg.integrations.embedded_signup.register_phone")
	@patch("nudg.integrations.embedded_signup.subscribe_app")
	def test_coexistence_does_not_register_the_phone(self, subscribe, register):
		subscribed, registered, warnings = embedded_signup._finish_cloud(
			"100", "200", "token", "", "v23.0", skip_register=True
		)
		self.assertTrue(subscribed)
		self.assertTrue(registered)
		self.assertEqual(warnings, [])
		subscribe.assert_called_once()
		register.assert_not_called()

	@patch("nudg.integrations.coexistence.save_message")
	@patch("nudg.integrations.site_store.account_for_phone", return_value="ACC")
	def test_echo_webhook_is_stored_as_outgoing(self, _account, save):
		coexistence.consume({
			"entry": [{
				"id": "1022",
				"changes": [{
					"field": "smb_message_echoes",
					"value": {
						"metadata": {"phone_number_id": "1065", "display_phone_number": "15550783881"},
						"message_echoes": [{
							"from": "15550783881",
							"to": "16505551234",
							"id": "wamid.echo",
							"timestamp": "1700255121",
							"type": "text",
							"text": {"body": "Sent from the phone"},
						}],
					},
				}],
			}],
		})
		row = save.call_args.args[1]
		self.assertEqual(save.call_args.args[0], "ACC")
		self.assertEqual(row["direction"], "Outgoing")
