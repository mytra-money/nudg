# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

from __future__ import annotations

import unittest
from datetime import datetime

from nudg.chatbot.ai_responder import phone_variants
from nudg.chatbot.flow_engine import next_step_name, substitute, validate_input
from nudg.chatbot.keyword_matcher import rule_matches
from nudg.services.bulk import clean_mobile
from nudg.services.campaign_replies import apply_unsubscribe, phone_digits, stop_plan
from nudg.services.display_titles import bulk_display_title
from nudg.services.campaign_schedules import (
	end_date_for,
	recipient_receives_campaign,
	schedule_is_due,
	schedule_sends_on,
	should_create_bulk,
	trigger_time_reached,
)


class _Rule:
	def __init__(self, **kwargs):
		self.__dict__.update(kwargs)


class _Step:
	def __init__(self, **kwargs):
		self.__dict__.update(kwargs)


class TestChatbotMatching(unittest.TestCase):
	def test_keyword_match_types(self):
		exact = _Rule(keywords="order, status", match_type="Exact", case_sensitive=0)
		self.assertTrue(rule_matches(exact, "Order"))
		self.assertFalse(rule_matches(exact, "order please"))

		contains = _Rule(keywords="invoice", match_type="Contains", case_sensitive=0)
		self.assertTrue(rule_matches(contains, "Where is my Invoice?"))

		starts = _Rule(keywords="hi", match_type="Starts With", case_sensitive=0)
		self.assertTrue(rule_matches(starts, "Hi there"))
		self.assertFalse(rule_matches(starts, "say hi"))

		pattern = _Rule(keywords=r"ord-\d+", match_type="Regex", case_sensitive=0)
		self.assertTrue(rule_matches(pattern, "see ORD-15"))

	def test_input_validation(self):
		email = _Step(input_type="Email")
		self.assertTrue(validate_input(email, "a@b.co")[0])
		self.assertFalse(validate_input(email, "not-an-email")[0])

		number = _Step(input_type="Number")
		self.assertTrue(validate_input(number, "1,200")[0])
		self.assertFalse(validate_input(number, "twelve")[0])

		choice = _Step(input_type="Select", options="Yes|No")
		self.assertTrue(validate_input(choice, "yes")[0])
		self.assertFalse(validate_input(choice, "maybe")[0])

		phone = _Step(input_type="Phone")
		self.assertTrue(validate_input(phone, "+1 (415) 555-1212")[0])

	def test_next_step_and_substitution(self):
		current = _Step(step_name="ask", idx=1, conditional_next='{"yes": "done", "default": "retry"}', next_step=None)
		steps = [current, _Step(step_name="done", idx=2), _Step(step_name="retry", idx=3)]
		self.assertEqual(next_step_name(current, steps, "YES"), "done")
		self.assertEqual(next_step_name(current, steps, "later"), "retry")
		plain = _Step(step_name="a", idx=1, conditional_next=None, next_step=None)
		self.assertEqual(next_step_name(plain, [plain, _Step(step_name="b", idx=2)], "x"), "b")
		self.assertEqual(substitute("Hello {name}", {"name": "Ada"}), "Hello Ada")

	def test_phone_variants_and_mobile_cleanup(self):
		variants = phone_variants("+1 415-555-1212")
		self.assertIn("14155551212", variants)
		self.assertIn("4155551212", variants)
		self.assertEqual(clean_mobile(" +1 (415) 555-1212 "), "+14155551212")

	def test_schedule_is_due_once(self):
		start = datetime(2026, 11, 1).date()
		self.assertFalse(schedule_is_due(start, 3, on_date=datetime(2026, 11, 3).date()))
		self.assertTrue(schedule_is_due(start, 3, on_date=datetime(2026, 11, 4).date()))
		self.assertTrue(schedule_is_due(start, 3, on_date=datetime(2026, 11, 6).date()))
		self.assertFalse(schedule_is_due(start, 3, on_date=datetime(2026, 11, 6).date(), already_sent=True))

	def test_end_date_and_trigger_match_email_campaign(self):
		start = datetime(2026, 11, 1).date()
		self.assertEqual(end_date_for(start, [0, 3, 1]), datetime(2026, 11, 4).date())
		self.assertIsNone(end_date_for(start, []))
		self.assertTrue(schedule_sends_on(start, 3, datetime(2026, 11, 4).date()))
		self.assertFalse(schedule_sends_on(start, 3, datetime(2026, 11, 5).date()))
		self.assertFalse(schedule_sends_on(start, 3, datetime(2026, 11, 3).date()))
		morning = datetime(2026, 11, 4, 8, 59)
		due = datetime(2026, 11, 4, 9, 0)
		self.assertFalse(trigger_time_reached("09:00:00", morning))
		self.assertTrue(trigger_time_reached("09:00", due))
		self.assertFalse(trigger_time_reached(None, due))

	def test_a_schedule_step_is_not_sent_again_once_a_bulk_message_exists(self):
		self.assertTrue(should_create_bulk(None))
		self.assertFalse(should_create_bulk("BULK-WA-2026-00009"))

	def test_unsubscribed_rows_stay_out_of_the_bulk_message(self):
		self.assertFalse(recipient_receives_campaign(1, True))
		self.assertFalse(recipient_receives_campaign(0, False))
		self.assertTrue(recipient_receives_campaign(0, True))

	def test_audience_phone_ignores_formatting(self):
		self.assertEqual(phone_digits("+1 555-000-7777"), "15550007777")
		self.assertEqual(phone_digits(""), "")

	def test_reply_before_the_first_step_does_not_unsubscribe(self):
		plan = stop_plan("+91 98450 22119", _drip(has_dispatch=False))
		self.assertEqual(plan["campaign_rows"], [])
		self.assertEqual(plan["list_rows"], [])
		self.assertFalse(plan["cancel"])

	def test_reply_unsubscribes_that_person_on_the_campaign_and_the_list(self):
		plan = stop_plan("919845022119", _drip())
		self.assertEqual(plan["campaign_rows"], ["camp-meera"])
		self.assertEqual(plan["list_rows"], ["list-meera"])
		self.assertFalse(plan["cancel"])

	def test_reply_cancels_the_campaign_when_nobody_else_is_still_subscribed(self):
		campaign = _drip()
		campaign["recipients"] = [campaign["recipients"][0]]
		plan = stop_plan("+91 98450 22119", campaign)
		self.assertEqual(plan["campaign_rows"], ["camp-meera"])
		self.assertTrue(plan["cancel"])

	def test_a_bulk_message_title_uses_the_campaign_and_template(self):
		self.assertEqual(bulk_display_title("WA-CAMP-2026-00004 day 1", "Test", "send_quotation1"), "Test · send_quotation1")
		self.assertEqual(bulk_display_title("Festive allocation", "Test", "send_quotation1"), "Festive allocation")

	def test_a_ticked_unsubscribe_box_is_kept_and_written_back(self):
		source = [{"mobile_number": "+91 98450 22119", "unsubscribed": 0}]
		submitted = [{"mobile_number": "+91 98450 22119", "unsubscribed": 1}]
		previous = [{"mobile_number": "+91 98450 22119", "unsubscribed": 0}]
		rows, edits = apply_unsubscribe(source, submitted, {}, previous)
		self.assertEqual(rows[0]["unsubscribed"], 1)
		self.assertEqual(edits, [("+91 98450 22119", 1)])

	def test_an_untouched_campaign_save_keeps_a_tick_already_on_the_list(self):
		source = [{"mobile_number": "919845022119", "unsubscribed": 1}]
		submitted = [{"mobile_number": "+91 98450 22119", "unsubscribed": 0}]
		previous = [{"mobile_number": "+91 98450 22119", "unsubscribed": 0}]
		rows, edits = apply_unsubscribe(source, submitted, {}, previous)
		self.assertEqual(rows[0]["unsubscribed"], 1)
		self.assertEqual(edits, [])

	def test_reply_is_ignored_when_the_option_is_off_or_the_campaign_has_ended(self):
		off = _drip()
		off["stop_on_reply"] = 0
		self.assertFalse(stop_plan("+91 98450 22119", off)["cancel"])
		self.assertEqual(stop_plan("+91 98450 22119", off)["campaign_rows"], [])
		done = _drip()
		done["status"] = "Completed"
		self.assertEqual(stop_plan("+91 98450 22119", done)["campaign_rows"], [])
		self.assertEqual(stop_plan("+91 90000 00000", _drip())["campaign_rows"], [])


def _drip(has_dispatch: bool = True) -> dict:
	return {
		"stop_on_reply": 1,
		"status": "In Progress",
		"has_dispatch": has_dispatch,
		"recipient_type": "WA Recipient List",
		"recipients": [
			{"name": "camp-meera", "mobile_number": "+91 98450 22119", "unsubscribed": 0},
			{"name": "camp-arjun", "mobile_number": "+91 98250 44218", "unsubscribed": 0},
		],
		"list_recipients": [
			{"name": "list-meera", "mobile_number": "919845022119", "unsubscribed": 0},
			{"name": "list-arjun", "mobile_number": "919825044218", "unsubscribed": 0},
		],
	}


if __name__ == "__main__":
	unittest.main()
