# 1K Saver Club — Django + Tailwind port

This is a full conversion of the original React/TanStack ("1K_Savings_Hub.zip")
prototype into **Django templates + Tailwind CSS**, keeping the same visual
design, layout structure, and file organization pattern (one file per page,
shared layout, shared partials).

## What's here

- **24 pages**, all wired and tested: landing page, 4 role dashboards
  (Member, Merchant, Rider, Agent), and 19 Admin console pages (overview +
  18 sub-pages).
- **Same design tokens as the original** — the exact oklch color palette,
  radii and shadow from the source `styles.css` are ported into a Tailwind
  config (`hub/templates/hub/base.html`), so classes like `bg-primary`,
  `bg-primary-soft`, `text-sidebar-foreground` work identically.
- **Responsive** — same breakpoints (`sm/md/lg`) as the original: desktop
  gets a fixed sidebar, mobile gets a bottom tab bar + drawer nav + role
  pill scroller, exactly like the source.
- **Animations** — fade-in-up, scale-in, staggered reveal-on-scroll
  (IntersectionObserver), hover/press affordances — see
  `hub/static/hub/css/theme.css` and `hub/static/hub/js/app.js`.
- **Charts** — Chart.js replaces Recharts (line/bar/pie), fed by JSON via
  Django's `json_script` template tag.
- **Sample data** ported 1:1 from `lib/sample-data.ts` into `hub/data.py`.

## Project layout

```
savings_hub_django/
  manage.py
  config/                  # Django project (settings, urls, wsgi)
  hub/                     # the app
    data.py                # sample data (Python port of sample-data.ts)
    nav.py                 # per-role nav config (port of DashboardLayout.tsx)
    views.py                # one view per page
    urls.py
    templatetags/hub_extras.py   # ugx / ugx_short / badge_class filters
    templates/hub/
      base.html             # <head>, Tailwind CDN config, fonts, chart.js
      dashboard.html        # shared sidebar/topbar/bottom-nav layout
      landing.html
      member.html / merchant.html / rider.html / agent.html
      admin/                # 19 admin pages
      partials/             # page_header.html, stat_card.html
    static/hub/
      css/theme.css          # design tokens + animation keyframes
      js/app.js               # nav, reveal-on-scroll, modals, Chart.js helpers
```

## Running it standalone

```bash
cd savings_hub_django
pip install django
python manage.py runserver
```

Visit `http://127.0.0.1:8000/`.

## Wiring it into your existing Django project

1. Copy the `hub/` app folder into your project.
2. Add `"hub"` to `INSTALLED_APPS`.
3. Add `path("", include("hub.urls"))` to your root `urls.py` (or mount it
   under a prefix, e.g. `path("saver-club/", include("hub.urls"))`).
4. Make sure `STATICFILES_DIRS` includes the app's `static/` folder (or run
   `collectstatic` if `hub/static/` sits alongside your other apps).
5. Replace the sample data in `hub/data.py` with real querysets/model data
   as you build out the backend — the views (`hub/views.py`) already pass
   this data into templates by name, so swapping a Python list for a
   queryset is usually a one-line change per view.

## Known simplifications vs. a production build

- All data is still static/mock (ported from the original prototype) — no
  models, no database, no auth. That matches the original's state, which
  was also UI-only with no backend wiring.
- Table "search" inputs do client-side text filtering only (no server
  round-trip) — see `data-table-search` in `app.js`.
- The "Create agent" modal and a few other buttons are visual/interactive
  but don't submit anywhere yet (same as the original — no forms had
  `onSubmit` handlers either).


## Quick start (local)
```bash
python -m venv env && source env/bin/activate     # Windows: env\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                              # for local dev set DJANGO_SETTINGS_MODULE=config.settings.development
python manage.py migrate
python manage.py seed_system_settings && python manage.py seed_subscription_plans && python manage.py seed_admin_group
python manage.py seed_demo_data                   # optional demo members/merchants/offers (password: DemoPass123!)
python manage.py createsuperuser
python manage.py runserver
```
Tests: `DJANGO_SETTINGS_MODULE=config.settings.testing python manage.py test`

## Frontend assets
Tailwind is compiled (no CDN). After adding new utility classes to templates: `npm install && npm run build:css`.
Lucide, Chart.js and the Inter font are vendored under `hub/static/hub/`.

## Production
`docker compose up -d --build`, then `migrate` and the seed commands (see comments in `docker-compose.yml`). Put TLS certs in `deploy/certs/`.
Admin users must enrol an authenticator app on first login; reset a lost device with `python manage.py reset_2fa <phone>`.
See `REVIEW.md` for the pre-launch checklist.
