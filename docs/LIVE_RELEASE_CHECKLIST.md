# Live production release checklist

Deterministic CI verifies code, contracts, security and offline outputs. The following checks require real credentials and must never be simulated.

## Gemini and Telegram

- [ ] Set `GEMINI_API_KEY` locally; never paste it into an issue or workflow log.
- [ ] Verify a normal Russian text request returns a non-fallback response.
- [ ] Upload a real JPEG and confirm Vision describes only visible content.
- [ ] Break provider access and confirm the bot reports unavailability instead of inventing details.
- [ ] Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_OWNER_ID`.
- [ ] Verify a different Telegram account receives no content.
- [ ] Complete onboarding, restart the container and verify profile persistence.
- [ ] Test guided text, voice, photo, `/cancel` and `/capabilities`.
- [ ] Interrupt networking and verify retry without duplicate replies.

## Operations

- [ ] `docker compose config --quiet` succeeds with newly generated secrets.
- [ ] `/health/live` is public; `/health/ready` requires the valid Brain API key.
- [ ] Back up and restore `brain-data`; verify profile, CRM and knowledge.
- [ ] Keep ports on `127.0.0.1` unless a TLS reverse proxy and firewall are configured.

MAX remains `experimental` until it has a real transport runner and the same checklist.
