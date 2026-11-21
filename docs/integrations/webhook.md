---
title: Webhook
sidebar_position: 2
---

Meta delivers inbound messages to the official WhatsApp app. Nudg wraps that webhook so chatbot button replies and WhatsApp Flow replies keep their raw payload, then the official handler stores the message.

Do not point Meta at `/nudg`. Point it at the official app's webhook method.

## What to enter in Meta

| Meta field | Where it lives in Nudg |
| --- | --- |
| Callback URL | The official WhatsApp webhook method on this site |
| Verify token | **Settings → WABA Profile**, Webhook verify token |
| App secret | **Settings → WABA Profile**, Webhook secret |

Subscribe the Meta app to `messages`. Without that subscription the inbox never sees new chats, even when the number is connected and sends work.

Only an Administrator or System Manager can see and save the verify token and the secret. The secret field stays blank after it is saved. Type a new value only when you are replacing it.

## API URL and version

On the same card:

| Field | Typical value |
| --- | --- |
| API URL | `https://graph.facebook.com` |
| API version | The Graph version your Meta app uses, such as `v23.0` |

Leave these at the defaults unless Meta has told you to use a different host or version.

## When messages do not arrive

1. Confirm the callback URL is the official WhatsApp method, not `/nudg`.
2. Confirm `messages` is subscribed.
3. Confirm the verify token in Meta matches the one saved here.
4. Open **Integrations → Logs** and look for a webhook error.

A successful webhook creates or updates the thread in **Conversations**. The bot, if it is on for that account, runs after the message is stored.
