<div align="center" markdown="1">

<img src="logo.svg" alt="Nudg logo" width="80" />

# Nudg

**One WhatsApp inbox for the team — reply, broadcast, and share a product.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](license.txt)

[Try it](https://nudg.mytra.money) · [Getting started](#getting-started)

</div>


Nudg helps sales and support teams handle customer WhatsApp chats in one shared inbox — with quick replies, approved templates, and campaigns.

It is built for companies that already talk to customers on WhatsApp and want the whole team on the same thread, instead of a phone only one person can open.

---

## Getting started

1. Open [nudg.mytra.money](https://nudg.mytra.money) and sign in. You can install Nudg on your own bench as well.
2. Go to **Integrations** and connect the WhatsApp number. Use **Login with Facebook**, or enter the phone number ID, WhatsApp Business Account ID, and access token.
3. Assign **WhatsApp User** to agents and **WhatsApp Manager** to the person who connects the number and runs campaigns.
4. Add **quick replies** (for example `/greet`) so common answers are one shortcut away.
5. New messages show up in **Conversations**. Reply in the open window, or send an approved template after it closes.

---

## The daily flow

```
Inbound message  →  Shared inbox  →  Reply or template  →  Campaign or catalog
```

### Conversations

The shared inbox. Filter by needs reply, the open 24-hour window, template only, and closed.

You can:

- Reply while the customer’s 24-hour window is open
- Send an approved template once that window has closed
- Leave an internal note the customer does not see
- Press `/` to insert a quick reply
- Link the thread to a Frappe document, such as a Customer, Lead, or Issue

### Template Studio

Templates are created and approved in the official WhatsApp app. Template Studio is where you pick one, fill its parameters, and send it.

### Marketing

Send an approved template to a list through **UTM Campaign**. Sent, delivered, read, and failed update as Meta reports them. Recipients who sent `STOP` are skipped.

### Catalogs

Open **Catalogs** in the menu. Add a catalog, its products, and the Meta catalog id there, then send a product from a chat.

### Chatbot

A keyword, a flow, or the default reply answers on the WhatsApp account that received the message. An agent transfer pauses the bot for that number. New conversations can still be assigned round-robin across the agents who are on.

---

## Settings

Open **Settings** from the menu.

| Section | What you set |
|---------|----------------|
| **Quick Replies** | Canned replies and the `/` shortcut for each |
| **Routing & Assignment** | How new conversations are handed to agents |
| **Team & Agents** | Who has WhatsApp User or WhatsApp Manager |
| **WABA Profile** | The WhatsApp business profile for the connected number |
| **Integrations** | The number, ERPNext, and logs |

Day-to-day replies happen in **Conversations**. Marketing and Integrations are for WhatsApp Manager.

---

## ERPNext integration

ERPNext is **optional**. The inbox, templates, and campaigns work without it.

When ERPNext is on the same site, Nudg can import **Item** records into a catalog and link a conversation to documents such as Lead, Quotation, and Issue. Nudg does not require ERPNext to run.

---

## Roles (who can do what)

| Role | Typical use |
|------|-------------|
| **WhatsApp User** | Day-to-day: conversations, replies, quick replies, internal notes |
| **WhatsApp Manager** | Connect a number, campaigns, the chatbot, catalogs |
| **System Manager** | Full access, including Desk and the WhatsApp account token |

Day-to-day work happens in the Nudg app (`/nudg`), not in Desk.

---

## Install (for admins)

On a Frappe bench (Frappe 16 or newer; ERPNext optional):

```bash
cd frappe-bench
bench get-app https://github.com/frappe/whatsapp
bench get-app https://github.com/mytra-money/nudg
bench --site <site> install-app whatsapp
bench --site <site> install-app nudg
bench --site <site> migrate
```

The official `whatsapp` app is what receives and sends messages. Nudg still installs without it. The page opens, and the inbox stays empty until a number is connected.

Build the app UI after install (or after frontend changes):

```bash
cd apps/nudg/frontend && npm install && npm run build:frappe
bench --site <site> clear-cache
```

`bench build --app nudg` from the bench root does the same build.

Then open `http://<site>:8000/nudg`. The guide is maintained in Desk.

---

## About Mytra

Nudg is built by [Mytra](https://mytra.money) for customer conversations on WhatsApp.

- Cloud: [nudg.mytra.money](https://nudg.mytra.money)

---

<div align="center">

Keep the team’s WhatsApp conversations in one place.

</div>
