---
title: Prerequisites
sidebar_position: 1
---

Nudg runs inside a Frappe bench. The inbox, templates, and campaigns talk to Meta through the official WhatsApp app.

| Requirement | Version |
| --- | --- |
| Frappe | 16 or newer, below 18 |
| Python | 3.10 or newer |
| Node | 20 or newer. 24 matches current Frappe benches |
| Official `whatsapp` app | Needed for a live inbox |

Do not install Nudg on a Frappe 15 site. The official WhatsApp app will not load there.

## Apps on the site

| App | Role |
| --- | --- |
| `frappe` | Site, login, users, and permissions |
| `whatsapp` | WhatsApp accounts, messages, templates, and the Meta webhook |
| `nudg` | The shared inbox, campaigns, catalogs, chatbot, and `/nudg` |
| `wiki` | This documentation, when you publish it on the site |
| `erpnext` | Optional. Item import and document links when it is on the same site |

Nudg still installs and the page still opens when `whatsapp` is missing. The inbox stays empty until that app is installed and a number is connected.

## Other apps on the same URLs

If `whatsapp_chat` is installed, `/whatsapp-inbox` belongs to that app. Nudg is `/nudg`.

## Who can use it

| Role | Use |
| --- | --- |
| WhatsApp User | Inbox, replies, quick replies, internal notes |
| WhatsApp Manager | Connect a number, campaigns, catalogs, the chatbot |
| System Manager | Desk, tokens, webhook secret, and site setup |

A System Manager assigns the WhatsApp roles after install.
