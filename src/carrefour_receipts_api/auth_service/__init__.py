"""Browser-based authentication for the Carrefour extractor.

A small FastAPI service that, much like Claude Code's browser login, opens the
Carrefour login portal in a real browser, lets the user authenticate (clearing
Cloudflare Turnstile), then **captures the resulting session cookies** and writes
them to ``config.COOKIES_FILE`` in the Netscape format the extractor's
``curl -b`` calls already expect. Those cookies are effectively the access token.

Carrefour is not an OAuth provider for this app, so there is no cross-domain
``localhost`` token callback — the cookies live on ``carrefour.fr`` and can only be
read from the browser context that performed the login. Hence the popup-and-capture
approach instead of a redirect/callback.

Run it with ``make auth-service`` (or
``uvicorn carrefour_receipts_api.auth_service.app:app``); see ``docs/api-extraction.md``.
"""
