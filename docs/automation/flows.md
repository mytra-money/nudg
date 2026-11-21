---
title: Flows
sidebar_position: 2
---

A flow is a short sequence of questions on one WhatsApp account. Use it when one keyword is not enough, for example when you need an order id and then an email.

## Build a flow

Open **Automation → Flows** and add a flow. Each step has:

| Field | Meaning |
| --- | --- |
| Step name | A label for the team |
| Message | The question sent to the customer |
| Input type | Text, Email, Phone, or Number |
| Store as | The name to keep the answer under for this session |

Put the steps in the order the customer should answer them. A keyword can start the flow. See [Keywords](keywords.md).

## While it is running

The session remembers which step the customer is on. Their next message is the answer to the current step, checked against the input type. When the steps are finished, the bot returns to keywords, AI, or the default reply on the next message.

If the customer should talk to a person instead, hand the chat off. The bot pauses for that number. See [Handoffs](handoffs.md).

## Delete a flow

Deleting a flow removes it from the account. A keyword that still points at it has nothing to start. Update or delete that keyword in the same pass.
