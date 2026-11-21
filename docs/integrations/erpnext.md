---
title: ERPNext
sidebar_position: 3
---

ERPNext is optional. Conversations, templates, and campaigns work with no ERPNext site connected.

There are two ways Nudg meets ERPNext.

## Same site

When ERPNext is installed on this bench site, a manager can import Item records into a [catalog](../catalogs/overview.md). The import copies a limited set of items (optionally one item group) into the catalog. Later changes to the Item are not pushed automatically. Run the import again when you want a newer copy.

Sending a template that is tied to a document such as a Lead or a Sales Invoice links that document on the conversation. The contact panel lists it.

## Another site

**Integrations → ERPNext** connects a remote ERPNext site and sends an approved template when a document on that site changes.

Add a site with:

| Field | Meaning |
| --- | --- |
| Site name | A label in Nudg |
| Site URL | The ERPNext site, without a trailing path you do not intend to call |
| API key and API secret | A user on that site who can read the DocTypes you will watch |
| WhatsApp account | The number that sends the template |

Nudg checks the connection before you rely on it. A failed check lists which step failed. Fix the URL, the key, or the user's permissions, then check again. You can disable a site without deleting it.

## Alerts

An alert is one DocType, one event, one phone field, and one template.

1. Open the site and add an alert.
2. Pick the DocType. Nudg reads the DocType list from the remote site.
3. Pick the event, the field that holds the phone number, and an approved template.
4. Map each template variable to a field on that DocType.
5. Save, and leave the alert enabled.

When the event happens, Nudg sends that template to the number in the phone field, using the variable map. The same document event is not sent twice for the same change. Alerts can be turned off or deleted without removing the site.

Use a utility template for transactional alerts. Use Marketing only for messages the recipient opted into.
