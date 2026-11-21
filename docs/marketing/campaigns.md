---
title: Campaigns
sidebar_position: 1
---

Open **Marketing** and click **New Campaign**. The list and the funnel you are filling are the screen in [Marketing](overview.md).

| Field | What to enter |
| --- | --- |
| Name | A name the team will recognize in the list |
| Description | Optional context, not sent to WhatsApp |
| WhatsApp account | The number that sends |
| Recipient list | Who receives it |
| Template | An approved template on that account |
| Start date | When it may start |
| Send after days | Delay after the start date. `0` means no extra delay |

Save it as a draft, review the template and the list, then run it. Confirm the run when Nudg asks. A draft that has not been run does not message anyone.

## While it sends

The campaign shows **In Progress**, then **Completed** or **Failed**. Counts on the campaign are the totals Meta has reported:

- Sent
- Delivered
- Read
- Failed

Open the recipient table to see the same status per phone number. Filter that table by Read, Delivered, Failed, or Pending, or search by name.

A recipient who has opted out is not sent. Their row does not become a successful delivery. See [Recipients and consent](recipients-and-consent.md).

## After it finishes

Use the counts to decide whether the template or the list needs a change. A high failed count usually means the template was rejected, the number is not on WhatsApp, or the account hit a Meta limit. **Integrations → Logs** has the error text for a failed send.

You can edit a draft. Deleting a campaign removes that campaign record. It does not delete the template or the recipient list.
