---
title: Business hours and AI
sidebar_position: 3
---

Both settings are on **Automation → Set up bot**, for the account selected at the top of the page.

## Business hours

Turn on **Limit** when the bot should send an away message outside working hours. Set the away message, then the days and the start and end time for each day you are open.

Outside those hours the customer gets the away message. Inside those hours, keywords, flows, and AI run as usual. Leave **Limit** off if the bot should answer at any time.

This clock belongs to the bot. It does not change the WhatsApp 24-hour window, and it does not stop an agent from replying in Conversations.

## AI replies

Turn on AI when a message matches no keyword and no flow and you want a generated answer instead of only the default reply.

| Field | What to enter |
| --- | --- |
| Provider | OpenAI, Anthropic, Google, or Custom |
| Model | The model name from that provider |
| API key | The provider key. It is stored for the account and is not shown again after you save it |

The default reply is still the fallback when AI is off, the key is missing, or the provider does not return an answer.

AI runs in the same session as the rest of the bot. **Forget a chat after (minutes)** applies to it too. A handoff to an agent pauses AI for that number along with the rest of the bot.

## Excluded numbers

Put phone numbers that must never get an automated reply on the excluded list for that account. Agents can still open the thread and reply by hand.
