---
title: Configuration
sidebar_position: 3
---

Connect a WhatsApp number from **Integrations** in Nudg. Do this as a WhatsApp Manager. Tokens and the webhook secret stay with System Manager.

## Login with Facebook

Use **Login with Facebook** when Embedded Signup is turned on for the site. The customer picks their WhatsApp Business account and number. Nudg stores the account. The signup PIN is shown once. Save it.

If chats are still copying in from the WhatsApp Business app, that can take a few minutes after the success message.

## Already have credentials

Use **I already have credentials** when the number is already on the WhatsApp Cloud API. The form asks for:

| Field | Required |
| --- | --- |
| Account name | Yes |
| Phone number ID | Yes |
| Access token | Yes |
| WhatsApp account ID | No |
| Meta app ID | No |

The token is stored on the WhatsApp account. It is not shown again in Nudg.

## Webhook

Inbound messages are delivered to the official WhatsApp app, not to a Nudg URL. In Meta, set the callback to that app's webhook method and subscribe to `messages`.

The verify token and webhook secret stay in **Settings → WABA Profile**, on the site-wide WhatsApp settings card. Only an Administrator or System Manager sees that card. See [Webhook](../integrations/webhook.md).

## Default account

If the site has more than one number, a System Manager can set **Default account** on that same card. Leave it empty on a multi-client site. It is used only when a webhook or send does not name a number and that number cannot be matched by phone id. People still message only from numbers they are allowed to use.

## Templates

Create and submit templates in the official WhatsApp app, or from Template Studio when that path is available on your site. Nudg uses the approved templates for campaigns and for replies outside the 24-hour window.
