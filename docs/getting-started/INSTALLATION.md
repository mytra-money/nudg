# Installation

Nudg needs the official `whatsapp` app for a live inbox. Nudg still installs if that app is missing. The page opens for a logged-in user, and the inbox stays empty until WhatsApp is connected.

## Commands

From the bench root:

```bash
cd frappe-bench
bench get-app https://github.com/frappe/whatsapp
bench get-app https://github.com/mytra-money/nudg
bench --site <site> install-app whatsapp
bench --site <site> install-app nudg
bench build --app nudg
```

The app name for `install-app` and `bench build` is `nudg`.

Install `whatsapp` when you want live accounts and messages. Installing `nudg` alone is valid.

`bench build --app nudg` builds the page from `frontend/`. You can also build from that directory with `npm run build:frappe`. See [Development setup](DEVELOPMENT_SETUP.md).

## What install does

Install creates the **WhatsApp User** role for agents and the **WhatsApp Manager** role for people who connect numbers. A System Manager assigns those roles.

Account tokens and webhook secrets stay on the official WhatsApp DocTypes, with System Manager.

## Where to open it

| URL | What it is |
| --- | --- |
| `/nudg` | The Nudg app. Guests are sent to login. |
| `/desk/nudg` | The Desk workspace tile. |

`/whatsapp-inbox` is a different app. Use `/nudg`.

## After install

Connect the number from Nudg, or enter the official WhatsApp account in Desk. See [Configuration](CONFIGURATION.md).
