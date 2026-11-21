---
title: Assignment and notes
sidebar_position: 4
---

Assignment records who owns the thread. Notes are for the team. Neither is sent to the customer.

## Assign a conversation

Open the thread and assign it to an agent. The assignee is stored the same way Frappe assigns any document: an open ToDo on the WhatsApp profile, so it shows up with the rest of that person's work.

You can filter the inbox by assignee. Unassigned threads stay in the shared list until someone takes them.

New conversations can be handed out round-robin across the agents who are on, so the next unassigned chat goes to the person who has waited longest since their last round-robin assignment. You can still assign or clear a thread by hand. Clearing the assignment leaves the conversation unassigned.

Add agents from **Settings → Team & Agents**. The routing tab on Settings explains the same rules. It does not replace the assign action in the inbox.

## Internal notes

Open notes on the thread, write the note, and save it. It is a comment on the conversation for the team. The customer does not receive it. Use a note for context the next agent needs, such as a promised callback or an order number that is not in the WhatsApp chat.

## Bot handoff

When Automation transfers a chat to a person, the bot pauses for that number and the thread shows a handoff banner. The agent replies from the inbox. Resume the bot from the handoff list in **Automation** when the person should take over again. See [Handoffs](../automation/handoffs.md).

## Linked Frappe records

The contact panel lists DocTypes already tied to the thread. A link is created when you send a template that is tied to a document, such as a Lead or a Sales Invoice. The panel shows the DocType and the document name. If your user can open that screen, the name is a link.
