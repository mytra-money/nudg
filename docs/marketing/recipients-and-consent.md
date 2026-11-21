---
title: Recipients and consent
sidebar_position: 2
---

A recipient list is the set of people a campaign sends to. Consent decides who is allowed to be on that send.

## Lists

WhatsApp Manager maintains recipient lists (WA Recipient List). A campaign points at one list. People on the list need a phone number WhatsApp can deliver to. The campaign stores a row per recipient with the status of that send, so a later campaign can use the same list without mixing up the old results.

Build the list from people who asked to hear from you. A purchased list is not an opt-in.

## STOP and START

Nudg reads a single-word reply as consent.

Opt-out words include `STOP`, `STOPALL`, `UNSUBSCRIBE`, `CANCEL`, `END`, `QUIT`, and `OPTOUT`. The contact is marked opted out. Later campaigns skip them.

Opt-in words include `START`, `UNSTOP`, and `YES`. The contact is marked opted in again.

The match is the whole message, after surrounding punctuation is removed, and it is not case-sensitive. A sentence that merely contains the word STOP does not opt the person out. An old STOP echoed from message history does not opt them out either.

Blocked, opted-out, and unsubscribed profiles are skipped when a campaign builds its send list.

## What the customer experiences

After they send `STOP`, they should not get another campaign until they send `START`. Replies inside an open service window are a separate path. Do not use a campaign to continue a support thread. Use [Conversations](../conversations/overview.md).
