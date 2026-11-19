# Prerequisites

Nudg runs inside a Frappe bench.

| Requirement | Version |
| --- | --- |
| Frappe | 16 or newer, below 18 |
| Python | 3.10 or newer |
| Node | 20 or newer. 24 matches current Frappe benches |
| Official `whatsapp` app | Needed for a live inbox. Nudg still installs when it is absent |

Do not install Nudg on a Frappe 15 site. The official `whatsapp` app will not load there.

## Apps

| App | Role |
| --- | --- |
| `frappe` | Site, login, and permissions |
| `whatsapp` | WhatsApp accounts, messages, templates, and the Meta webhook |

Install `whatsapp` before you expect a live inbox. Nudg still opens when that app is absent and shows that WhatsApp is not connected.

## Other apps on the same URLs

If `whatsapp_chat` is installed, `/whatsapp-inbox` belongs to that app. Nudg is `/nudg`.

## Who can use it

| Role | Use |
| --- | --- |
| WhatsApp User | Inbox and replies |
| WhatsApp Manager | Connect a number, campaigns, and the chatbot |
| System Manager | Desk, tokens, and site setup |

A System Manager assigns the WhatsApp roles after install.
