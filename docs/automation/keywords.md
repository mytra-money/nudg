---
title: Keywords
sidebar_position: 1
---

A keyword rule watches the incoming text and either sends a reply or starts a flow.

## Create a rule

Open **Automation → Keywords** and add a rule for the selected account.

| Field | Choices |
| --- | --- |
| Keywords | One or more words or phrases |
| Match | Contains, Exact, or Starts With |
| Response | Send a reply, or start a flow |

**Contains** matches when the message includes the keyword. **Exact** matches the whole message. **Starts With** matches only at the beginning. When more than one rule could match, the one with the higher priority wins.

**Send a reply** uses the text you write on the rule. **Start a flow** needs a flow you have already saved. See [Flows](flows.md).

## Examples

| Customer writes | Match | Result |
| --- | --- | --- |
| `hours` | Exact | The opening-hours reply |
| `track my order 1042` | Starts With `track` | The tracking reply, or a flow that asks for the order id |
| `I need the price list` | Contains `price` | The price-list reply |

Keyword text is an automatic reply inside the service window. It is not a template and it is not reviewed by Meta. For a message you start, use [Marketing](../marketing/campaigns.md) or [Template Studio](../template-studio/send-a-template.md).

`STOP` and `START` are handled as consent before they are treated as ordinary keywords. See [Recipients and consent](../marketing/recipients-and-consent.md).
