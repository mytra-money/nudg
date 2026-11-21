---
title: Send a template
sidebar_position: 1
---

You send a template in three places. The template itself is the same record.

| Place | When |
| --- | --- |
| Conversations | One customer, usually because the 24-hour window is closed |
| Template Studio | You want to review the preview and the variables first, then send |
| Marketing | Many recipients on a list |

## Fill the variables

A body such as `Hello {{1}}, your order {{2}} has shipped` needs a value for each placeholder. Enter the values in the order the template declares them. The preview updates as you type. Header media, when the template has an image, video, or document header, has to be available on the account before the send.

Buttons on the template (a quick reply, a link, or a phone number) are part of the approved template. You do not rewrite them at send time.

## One recipient from a thread

Open the thread, choose the template, fill the variables, and send. If Meta rejects it, the thread shows **Failed** and **Integrations → Logs** has the reason. The usual reasons are: the template is not approved, a variable is empty, or the number is not allowed to send that template.

## Many recipients

Use **Marketing**. Pick the account, the recipient list, and the template. Recipients who sent `STOP` are skipped. See [Recipients and consent](../marketing/recipients-and-consent.md).
