# Copyright (c) 2026, Nudg and contributors
# Live End-to-End Cross-Site Test Runner

import time
import uuid
from unittest.mock import patch
import frappe

def run_tests():
    print("=" * 70)
    print("STARTING LIVE CROSS-SITE TEST SUITE: whatsdesk <-> skilldzire")
    print("=" * 70)
    
    account_name = "Mytra Business Care"
    test_phone = f"+9198765{int(time.time()) % 100000:05d}"
    print(f"Test phone number: {test_phone}")
    
    # -------------------------------------------------------------
    # STEP 1: TEST CROSS-SITE CONNECTION
    # -------------------------------------------------------------
    print("\n[TEST 1] Verifying Cross-Site Connection...")
    from nudg.integrations.erpnext.service import verify_site, _load_site, _client_for_site
    from nudg.integrations.site_store import stores_remotely, RemoteStore
    
    site_config = _load_site(account_name)
    assert site_config is not None, "Site configuration for account could not be loaded"
    print(f"  Remote site URL: {site_config.site_url}")
    
    verify_res = verify_site(account_name)
    frappe.db.commit()
    print(f"  Verification Result: ok={verify_res.get('ok')}, status={verify_res.get('status')}, remote_user={verify_res.get('remote_user')}")
    assert verify_res.get("ok") is True, f"Site verification failed: {verify_res}"
    assert verify_res.get("status") == "Connected", f"Status not connected: {verify_res}"
    
    is_remote = stores_remotely(account_name)
    print(f"  stores_remotely({account_name}): {is_remote}")
    assert is_remote is True, "Account should store remotely when connected"
    
    client = _client_for_site(site_config)
    logged_user = client.get_logged_user()
    print(f"  Live remote authenticated user on skilldzire: {logged_user}")
    assert logged_user == "Administrator"
    print("  --> PASS: Cross-Site Connection verified and healthy.")

    # -------------------------------------------------------------
    # STEP 2: TEST INCOMING MESSAGE & REMOTE STORAGE
    # -------------------------------------------------------------
    print("\n[TEST 2] Testing Inbound WhatsApp Message Flow...")
    from nudg.integrations import site_store
    
    msg_id_1 = f"wamid.live.in.{uuid.uuid4().hex[:12]}"
    inbound_text = f"Hello from live test customer {time.strftime('%H:%M:%S')}"
    
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "102938475619283",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "15550001",
                        "phone_number_id": "10928374928172"
                    },
                    "contacts": [{
                        "profile": {"name": f"Customer {test_phone[-4:]}"},
                        "wa_id": test_phone.replace("+", "")
                    }],
                    "messages": [{
                        "from": test_phone.replace("+", ""),
                        "id": msg_id_1,
                        "timestamp": str(int(time.time())),
                        "text": {"body": inbound_text},
                        "type": "text"
                    }]
                }
            }]
        }]
    }
    
    site_store.ingest(payload)
    frappe.db.commit()
    
    # Check local profile on whatsdesk
    local_profile = frappe.db.get_value("WA Profile", {"phone_number": test_phone}, "name")
    print(f"  whatsdesk.localhost: Local mirror profile created: {local_profile}")
    assert local_profile is not None, "Local mirror profile was not created on whatsdesk"
    
    # Check remote profile and message on skilldzire via client
    remote_profiles = client.get_resources("WA Profile", fields=["name", "phone_number"], filters={"phone_number": test_phone})
    print(f"  skilldzire.localhost: Remote profile found: {remote_profiles}")
    assert len(remote_profiles) > 0, "Profile was not stored on skilldzire"
    remote_profile_name = remote_profiles[0]["name"]
    
    remote_messages = client.get_resources(
        "WA Message",
        fields=["name", "direction", "message", "message_id", "status"],
        filters={"message_id": msg_id_1}
    )
    print(f"  skilldzire.localhost: Remote incoming message found: {remote_messages}")
    assert len(remote_messages) > 0, "Incoming message was not stored on skilldzire"
    assert remote_messages[0]["direction"] == "Incoming"
    assert remote_messages[0]["message"] == inbound_text
    print("  --> PASS: Incoming message successfully processed, stored remotely on skilldzire and mirrored locally.")

    # -------------------------------------------------------------
    # STEP 3: TEST OUTGOING MESSAGE & REMOTE STORAGE
    # -------------------------------------------------------------
    print("\n[TEST 3] Testing Outbound WhatsApp Message Flow...")
    outbound_text = f"Agent reply to customer: Welcome! {time.strftime('%H:%M:%S')}"
    msg_id_out = f"wamid.live.out.{uuid.uuid4().hex[:12]}"
    
    with patch("nudg.integrations.whatsapp.adapter._deliver", return_value=msg_id_out):
        saved_msg_name = site_store.send_message(to=local_profile, message=outbound_text)
    frappe.db.commit()
    
    print(f"  Outgoing message sent, returned name: {saved_msg_name}")
    assert saved_msg_name is not None
    
    # Verify on skilldzire
    remote_out_msgs = client.get_resources(
        "WA Message",
        fields=["name", "direction", "message", "message_id", "status"],
        filters={"message_id": msg_id_out}
    )
    print(f"  skilldzire.localhost: Remote outgoing message found: {remote_out_msgs}")
    assert len(remote_out_msgs) > 0, "Outgoing message was not stored on skilldzire"
    assert remote_out_msgs[0]["direction"] == "Outgoing"
    assert remote_out_msgs[0]["message"] == outbound_text
    assert remote_out_msgs[0]["status"] == "Sent"
    
    # Status webhook: Delivered -> Read
    print("  Testing Delivery Status Updates (Delivered, Read)...")
    store = RemoteStore.for_account(account_name)
    store.take({
        "statuses": [{
            "id": msg_id_out,
            "status": "delivered",
            "timestamp": str(int(time.time())),
            "recipient_id": test_phone.replace("+", "")
        }]
    })
    delivered_msgs = client.get_resources("WA Message", fields=["name", "status"], filters={"message_id": msg_id_out})
    print(f"  skilldzire status after 'delivered': {delivered_msgs[0].get('status')}")
    assert delivered_msgs[0].get("status") == "Delivered"
    
    store.take({
        "statuses": [{
            "id": msg_id_out,
            "status": "read",
            "timestamp": str(int(time.time())),
            "recipient_id": test_phone.replace("+", "")
        }]
    })
    read_msgs = client.get_resources("WA Message", fields=["name", "status"], filters={"message_id": msg_id_out})
    print(f"  skilldzire status after 'read': {read_msgs[0].get('status')}")
    assert read_msgs[0].get("status") == "Read"
    print("  --> PASS: Outgoing message and status receipts (Delivered, Read) verified across sites.")

    # -------------------------------------------------------------
    # STEP 4: TEST TEMPLATE MESSAGE FLOW
    # -------------------------------------------------------------
    print("\n[TEST 4] Testing Template Message Flow...")
    approved_template = frappe.db.get_value("WA Template", {"status": "Approved"}, "name")
    if not approved_template:
        # Create a mock approved template for test
        tpl = frappe.get_doc({
            "doctype": "WA Template",
            "template_name": "live_test_template",
            "category": "MARKETING",
            "language": "en_US",
            "status": "Approved",
            "body": "Hello {{1}}, here is your test template alert."
        })
        tpl.insert(ignore_permissions=True)
        frappe.db.commit()
        approved_template = tpl.name
    
    tpl_name = frappe.db.get_value("WA Template", approved_template, "template_name")
    print(f"  Using approved template: {approved_template} ({tpl_name})")
    
    msg_id_tpl = f"wamid.live.tpl.{uuid.uuid4().hex[:12]}"
    with patch("nudg.integrations.whatsapp.adapter._deliver", return_value=msg_id_tpl):
        tpl_msg_name = site_store.send_template_message(
            template=approved_template,
            to=local_profile
        )
    frappe.db.commit()
    print(f"  Template message sent, returned name: {tpl_msg_name}")
    
    remote_tpl_msgs = client.get_resources(
        "WA Message",
        fields=["name", "direction", "message", "message_id", "status"],
        filters={"message_id": msg_id_tpl}
    )
    print(f"  skilldzire.localhost: Remote template message found: {remote_tpl_msgs}")
    assert len(remote_tpl_msgs) > 0, "Template message was not stored on skilldzire"
    assert remote_tpl_msgs[0]["direction"] == "Outgoing"
    print("  --> PASS: Template message flow verified across sites.")

    # -------------------------------------------------------------
    # STEP 5: TEST INBOX SYNC & THREAD RETRIEVAL ACROSS SITES
    # -------------------------------------------------------------
    print("\n[TEST 5] Testing Cross-Site Inbox Sync & Thread Retrieval...")
    from nudg.api import get_thread, get_inbox
    
    thread = get_thread(local_profile)
    messages = thread.get("messages", [])
    print(f"  Thread retrieved for profile {local_profile}: {len(messages)} messages found.")
    for m in messages:
        print(f"    - [{m.get('direction')}] {m.get('status')}: {m.get('message')}")
    assert len(messages) >= 3, "Expected at least 3 messages (incoming, outgoing, template)"
    
    # Check that messages match our sent items
    text_list = [m.get("message") for m in messages]
    assert inbound_text in text_list, "Inbound message not found in thread"
    assert outbound_text in text_list, "Outbound message not found in thread"
    
    # Verify get_inbox
    inbox = get_inbox(account=account_name)
    conversations = inbox.get("conversations", [])
    matching_conv = next((c for c in conversations if (c.get("profile", {}).get("name") == local_profile or c.get("profile", {}).get("phone_number") == test_phone)), None)
    print(f"  Inbox preview for conversation: {matching_conv.get('preview') if matching_conv else None}")
    assert matching_conv is not None, "Conversation not listed in get_inbox"
    print("  --> PASS: Cross-Site Inbox Sync and Thread retrieval successfully verified.")

    # -------------------------------------------------------------
    # STEP 6: TEST FAULT TOLERANCE & OFFLINE QUEUE (client_sync)
    # -------------------------------------------------------------
    print("\n[TEST 6] Testing Fault-Tolerance & Offline Sync Queue...")
    from nudg.integrations.erpnext.client import ERPNextClientError
    from nudg.integrations import site_sync
    
    # Simulate site down during incoming message
    msg_id_offline = f"wamid.live.offline.{uuid.uuid4().hex[:12]}"
    offline_text = f"Message received during site downtime {time.strftime('%H:%M:%S')}"
    
    # We patch insert_resource to simulate connection error
    store = RemoteStore.for_account(account_name)
    with patch.object(store.client, "insert_resource", side_effect=ERPNextClientError("Site connection timeout", retryable=True)):
        store.take({
            "contacts": [{"profile": {"name": f"Customer {test_phone[-4:]}"}}],
            "messages": [{
                "id": msg_id_offline,
                "from": test_phone.replace("+", ""),
                "type": "text",
                "text": {"body": offline_text},
                "timestamp": str(int(time.time()))
            }]
        })
    frappe.db.commit()
    
    # Verify message is held locally with client_sync = "Pending"
    held_row = frappe.db.get_value("WA Message", {"message_id": msg_id_offline}, ["name", "client_sync", "message"], as_dict=True)
    print(f"  whatsdesk.localhost: Held message record: {held_row}")
    assert held_row is not None, "Message was not held locally during downtime"
    assert held_row["client_sync"] == "Pending", f"Expected client_sync Pending, got {held_row['client_sync']}"
    
    # Now simulate site recovery and flush queue
    print("  Simulating site recovery: Flushing pending queue to skilldzire...")
    site_sync.flush_account(account_name)
    frappe.db.commit()
    
    # Verify status changed to Synced locally
    synced_row = frappe.db.get_value("WA Message", {"message_id": msg_id_offline}, ["name", "client_sync"], as_dict=True)
    print(f"  whatsdesk.localhost: After flush, client_sync: {synced_row['client_sync']}")
    assert synced_row["client_sync"] == "Synced", f"Expected Synced, got {synced_row['client_sync']}"
    
    # Verify message now exists on skilldzire
    flushed_remote_msgs = client.get_resources(
        "WA Message",
        fields=["name", "direction", "message", "message_id", "status"],
        filters={"message_id": msg_id_offline}
    )
    print(f"  skilldzire.localhost: Flushed message found on remote site: {flushed_remote_msgs}")
    assert len(flushed_remote_msgs) > 0, "Flushed message was not inserted on skilldzire"
    assert flushed_remote_msgs[0]["message"] == offline_text
    print("  --> PASS: Fault-tolerance offline queue and recovery flush verified.")

    # -------------------------------------------------------------
    # STEP 7: TEST ADDITIONAL FUNCTIONALITIES
    # -------------------------------------------------------------
    print("\n[TEST 7] Testing Additional Post-Connection Functionalities...")
    from nudg import desk_api
    
    # 7.1 Internal Notes
    note_content = f"Customer interested in enterprise plan. Note at {time.strftime('%H:%M:%S')}"
    desk_api.add_conversation_note(local_profile, note_content)
    frappe.db.commit()
    thread_with_notes = get_thread(local_profile)
    notes = thread_with_notes.get("notes", [])
    print(f"  Conversation notes count: {len(notes)}")
    assert any(note_content in n.get("content", "") for n in notes), "Internal note not found in thread"
    print("  - Internal conversation note added and retrieved successfully.")
    
    # 7.2 Agent Assignment
    assign_res = desk_api.assign_conversation(local_profile, "Administrator")
    frappe.db.commit()
    print(f"  Assigned conversation to: {assign_res.get('assignee')} (assignees: {assign_res.get('assignees')})")
    assert assign_res.get("assignee") == "Administrator" or "Administrator" in assign_res.get("assignees", [])
    print("  - Conversation assignment verified.")
    
    # 7.3 Quick Replies
    qr_res = desk_api.list_quick_replies(account=account_name)
    print(f"  Quick replies available: {len(qr_res)}")
    print("  - Quick replies list API verified.")
    
    # 7.4 Close Conversation
    close_res = desk_api.close_conversation(local_profile)
    frappe.db.commit()
    print(f"  Closed conversation status: {close_res.get('assignment_status')}")
    assert close_res.get("assignment_status") == "Closed"
    print("  - Conversation close/lifecycle verified.")
    
    print("\n" + "=" * 70)
    print("ALL LIVE CROSS-SITE TESTS PASSED SUCCESSFULLY! (7/7)")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
