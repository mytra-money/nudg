---
title: Products
sidebar_position: 1
---

Each product sits on one catalog. Open the catalog, then add or edit an item.

Keep the name and price the same as the product the customer can actually order. When the item was imported from ERPNext, the catalog item remembers the Item it came from, so you can tell a hand-entered product from an imported one.

## Meta catalog id

If you sell through a Meta catalog, put that catalog's id on the Nudg catalog. Sends that refer to Meta's catalog need this id. A catalog you only use inside Nudg, with products you typed in, can exist without it. Those products are still sent as product messages from the thread.

## Remove a product or a catalog

Deleting a product removes it from the catalog. Deleting a catalog removes the catalog. Neither deletes the ERPNext Item, and neither deletes a WhatsApp thread that already sent the product.

## Who can change them

WhatsApp Manager creates and deletes catalogs and products. WhatsApp User can send a product from a thread when the account is one they are allowed to use.
