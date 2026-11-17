# Common issues

## The site is still on Frappe 15

Nudg and the official `whatsapp` app need Frappe 16 or newer. Check the running version in the bench console with `frappe.__version__`. A site that is still on 15 cannot load the official app.

## Nudg is not installed

`/nudg` returns 404 until the app is installed:

```bash
bench get-app https://github.com/mytra-money/nudg
bench --site <site> install-app nudg
bench build --app nudg
```

If the page opens and the inbox says WhatsApp is not connected, install the official app as well:

```bash
bench --site <site> install-app whatsapp
```

## The wrong address

Open `/nudg`. `/whatsapp-inbox` is a different app when `whatsapp_chat` is installed.

## Port 4178 is already taken

The dev server uses port `4178` and will not switch to another port. Stop the other process, or change the port in `frontend/package.json` and the Vite config together.

## Login works on the site but the dev server shows sample data

The dev server is a different origin from the site, so the session cookie may not be sent. Open `/nudg` on the site itself. If you use the dev server against the site, turn CSRF checking off only for that local site, and turn it back on when you finish. See [Development setup](../getting-started/DEVELOPMENT_SETUP.md).

## Permission error

The signed-in user needs the **WhatsApp User** role to read messages, or **WhatsApp Manager** / **System Manager** to connect a number. A System Manager assigns the role in Desk.

## Webhook traffic does not arrive

Point Meta at the official WhatsApp app's webhook, not at `/nudg`. Subscribe to `messages`. The verify token and secret are in WA Settings.

## The page is blank after a frontend change

Build again so the site picks up the new files:

```bash
bench build --app nudg
bench --site <site> clear-cache
```

## Sent back to login

Guests are sent to `/login` and returned to `/nudg` after they sign in. Use the same host you use for the bench site. A different host does not keep the session.
