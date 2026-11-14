# Development setup

The app source is in `frontend/`.

## Preview without a site

```bash
cd frontend
npm install
npm run dev
```

The dev server uses port `4178`. If that port is busy, the process stops. Nothing is sent to Meta. Without a logged-in site, the screen shows sample conversations.

## Dev server against a site

Run the dev server from `frontend/` while the bench is up. The page is served with your site login at `/nudg`.

Frappe's session cookie and the CSRF check do not line up with a separate dev-server origin. For local development only:

```bash
bench --site <site> set-config ignore_csrf 1
```

Turn it off when you stop:

```bash
bench --site <site> set-config ignore_csrf 0
```

Do not leave CSRF disabled on a shared or production site. Production builds do not need the flag.

## Build for the site

```bash
cd frontend
npm run build:frappe
```

Or, from the bench root:

```bash
bench build --app nudg
```

Either command writes the files the site serves for `/nudg`.
