# Deploy & Monetize Checklist

Everything below is what needs to happen between "code is written" and "money hits your account."

## 1. Get an Anthropic API key
- Sign up: https://console.anthropic.com/ → **API Keys** → **Create Key**.
- Add payment method + set a monthly usage cap (e.g. $50) so a runaway loop can't drain the wallet.
- Copy the key (`sk-ant-…`) — you'll paste it into Render in step 4.

## 2. Set up Stripe
- Sign up: https://dashboard.stripe.com/register.
- Complete account activation (business details, bank account). India accounts need PAN + GST or an equivalent registered-business proof.
- **Products/pricing**: nothing to configure here — the code creates ad-hoc line items per checkout using `PACKS` in `app/credits.py`. Change prices there if needed.
- Under **Developers → API keys**, copy:
  - `Publishable key` (starts `pk_live_…` or `pk_test_…`) — not needed server-side, but keep it if you ever move to embedded checkout.
  - `Secret key` (`sk_live_…` / `sk_test_…`) — this goes into Render.
- Under **Developers → Webhooks → Add endpoint**:
  - URL: `https://vishaal-vedic-astro-app.onrender.com/stripe/webhook`
  - Events: **checkout.session.completed** (that's the only one the code listens for)
  - After creating, click into it and copy the **Signing secret** (`whsec_…`) — this goes into Render.

## 3. Push the code
```bash
cd C:\Projects\vedic-astro-app
git status                          # see what's changed
git add -A
git commit -m "Add LLM interpretation + Stripe monetization + demo Q&A"
git push
```
Render auto-deploys both services (`vedic-astro-api`, `vedic-astro-frontend`) on push.

## 4. Set env vars on Render (backend service only)
Dashboard → **vedic-astro-api** → **Environment** → add:

| Key                    | Value                                             |
| ---------------------- | ------------------------------------------------- |
| `ANTHROPIC_API_KEY`    | `sk-ant-…` from step 1                            |
| `ANTHROPIC_MODEL`      | `claude-sonnet-5` (already set in render.yaml)    |
| `STRIPE_SECRET_KEY`    | `sk_live_…` or `sk_test_…` from step 2            |
| `STRIPE_WEBHOOK_SECRET`| `whsec_…` from step 2                             |
| `FRONTEND_BASE_URL`    | `https://vishaalvedic-astro-app.onrender.com`     |
| `CREDITS_CURRENCY`     | `inr`                                             |

Save — Render re-deploys automatically.

## 5. Test the flow (in Stripe TEST mode first)
Use `sk_test_…` + `pk_test_…` for the first pass:
1. Open the deployed frontend → generate a chart.
2. Click **Buy** on the Starter pack → you should be redirected to Stripe Checkout.
3. Pay with card `4242 4242 4242 4242`, any future date, any CVC.
4. On success you'll return to the frontend and a "Payment received" banner shows a 16-char code.
5. Copy the code, paste into the Ask card, type a question, click **Ask**. You should see an interpretation and credit count go from 5 → 4.

If step 4's banner never shows a code:
- Stripe → **Webhooks** → your endpoint → check recent deliveries for errors.
- Common cause: signing secret mismatch, or the API service was cold-starting and dropped the webhook. Retry the webhook from the Stripe dashboard.

Once test flow works end-to-end, swap to LIVE keys (`sk_live_…`, `whsec_…` from a live-mode webhook) and repeat step 5 with a real ₹99 card.

## 6. Legal pages (before taking real money)
The frontend footer has placeholder links for **Terms**, **Refund Policy**, **Privacy**. These need real text before you go live in India:
- **Refund policy** — recommended: "Credits are non-refundable once redeemed. Unredeemed credits refundable within 7 days on request." Stripe India requires this to be visible.
- **Terms** — one-page: what the service is (informational, not medical/legal/financial advice), age restriction (18+), acceptable use.
- **Privacy** — what data is collected (name, DOB, TOB, place — not stored server-side beyond the request), what Stripe processes.
- Add a **Contact** email (Stripe requires one for chargeback disputes).

Two options: (a) write these yourself and swap the `#` in the footer for real pages/anchors; (b) use a generator like Termly / iubenda.

## 7. Known limits to watch after launch
- **Free-tier ephemeral disk** on Render means the credit-code SQLite DB (`/tmp/credits.sqlite3`) resets when the dyno restarts. For soft-launch fine; before real volume, attach a Render persistent disk (paid) and set `CREDITS_DB_PATH=/var/data/credits.sqlite3`.
- **Free-tier cold starts** on Render: first request after ~15 min idle takes 30–60s. Users may bail. Upgrade to Starter ($7/mo) once you have paying users.
- **LLM cost per question**: at Sonnet 5 pricing, one interpretation is roughly ₹3–8 depending on chart size and answer length. Starter pack (5 for ₹99) gives ~₹19/question margin — healthy.
- **Rate limiting**: not implemented. If someone shares a credit code publicly, it drains fast but that's their loss. Consider adding IP-based throttling in `api.py` if abuse shows up.

## 8. Marketing hooks already in the code
- Landing page shows 3 fully-worked demo Q&As before a visitor even enters birth details — this is the "show, don't tell" that converts.
- Demo section auto-hides once a real chart is generated, so it doesn't clutter the results view.
- Each interpretation opens with a "Working from" data-restatement — this builds trust that the answer is grounded in real placements, not generic horoscope filler.

## 9. Not yet built (post-launch, if it earns)
- Email delivery of credit codes (currently code is only shown once on the return page — session-storage only).
- Interpretation history (would need accounts).
- Multi-language (Hindi UI would materially expand the India audience).
- SEO/blog content — public chart interpretations for famous births, indexed for organic traffic.
