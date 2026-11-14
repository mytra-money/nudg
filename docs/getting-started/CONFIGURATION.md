# Configuration

Connect a WhatsApp number from **Integrations** in NUDG, or create the account in Desk on the official WhatsApp DocTypes. Do this as System Manager.

## Login with Facebook

Use **Login with Facebook** when Embedded Signup is turned on for the site. The customer picks their WhatsApp Business account and number. NUDG stores the account. The signup PIN is shown once. Save it.

## Already have credentials

Use **I already have credentials** when you have:

- Account name
- Phone number ID
- WhatsApp Business Account ID
- Access token
- Meta app ID

The token is stored on the WhatsApp account. It is not shown again in NUDG.

## Webhook

Inbound messages are delivered to the official WhatsApp app, not to a NUDG URL. In Meta, set the callback to that app's webhook method and subscribe to `messages`.

The verify token and webhook secret stay in WhatsApp Settings. Only a System Manager should open that form.

## Default account

If the site has more than one number, mark the one NUDG should use by default. Outbound sends and unmatched inbound messages use that account.

## Templates

Create and submit templates in the official WhatsApp app. NUDG uses the approved templates for campaigns and for replies outside the 24-hour window.
