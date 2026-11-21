---
title: Logs
sidebar_position: 4
---

**Integrations → Logs** is the audit of messages and webhooks. It is shown when your user is allowed to read logs. Managers use it when a send fails or a webhook does not show up in the inbox.

Each row has a time, a reference (often a WA Message or a WA Template), and the message text. When the row points at a document you can open, the reference is a link.

## What to look for

| Symptom | What the log usually says |
| --- | --- |
| Reply rejected | The 24-hour window is closed. Send a template |
| Template rejected | The template is not approved, or a variable is missing |
| Inbox is quiet | No webhook row. Meta is not calling the official webhook. See [Webhook](webhook.md) |
| Campaign recipient failed | The error Meta returned for that number |

Logs explain a failure. They do not retry it. Fix the cause, then reply again from the thread or run the failed part of the campaign again.

Overview also shows recent log lines for the selected account when the page is live, so a manager can see a new error without opening Logs first.
