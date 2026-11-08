# Instagram browser setup

## Current state

**Update:** directory-wide Instagram automation is now installed, with 294 linked accounts and a separate bounded twice-daily trigger prepared. Restarting Chromium for its automation interface reached a login screen; owner sign-in is pending in the private desktop. The trigger and `MARITIME_INSTAGRAM_ENABLED` remain disabled until the automated reader is verified. See [expanded monitoring setup](club-monitoring.md). The original sleep/wake verification below is historical and does not establish the current restarted browser's login.

The owner selected the separate Linux browser route after the costs below were disclosed. The persistent Linux computer `club-alerts-instagram` is now provisioned, and Chromium successfully opened Instagram's login form. Its ID is `1667005f-7f99-4cb5-aaf6-94a4b72c1c05`; its stable external user ID is `club-alerts-monitor-instagram`. Reuse this computer instead of creating one per check.

The browser profile is `/home/desk/.config/chromium`, on the computer's persistent disk. Its directory exists with permissions `0700`. On November 8, 2026 UTC, the owner completed login and signed-in access was verified by opening CSSS's "Full Stack Pancakes" post and reading its caption. The same post remained accessible after one sleep/wake cycle. The computer was then left asleep; its sleeping status was confirmed at 07:06:32 UTC. No password, cookies or session have been copied into the repository. Private takeover links are short-lived and are not saved here.

Non-secret resource metadata is recorded in [instagram-browser.json](config/instagram-browser.json). The existing `club-alerts-monitor` agent remains the calendar worker; automated control of this new browser has not been added to it. No model calls or subscription upgrade were made.

## Original agent's desktop limitation

The existing agent is on the active Scale usage plan, with 8 GB RAM and 100 GB disk. Its built-in desktop remains disabled. The separate Linux computer uses the supported Computers API rather than this blocked switch.

The owner API rejected `PATCH /api/agents/{id}/desktop-config` with `{"enabled":true}`:

```json
{
  "http_status": 402,
  "code": "seat_limit",
  "detail": "Desktop agents need a paid plan. Upgrade to Starter to enable one: https://maritime.sh/billing"
}
```

This conflicts with the account's live billing results: `billingModel=usage`, `plan=scale`, `planStatus=active`, `blocked=false`. The computer entitlement API also reports Linux desktops available. This appears to be an entitlement mismatch in the built-in agent desktop switch. Do not buy another subscription or modify billing to work around it.

## Costs before activation

- **Desktop inside the existing agent:** published agent-box pricing is approximately $11.60/month at the existing allocation: $4 for 8 GB RAM plus $7.60 for 95 GB of disk beyond the included 5 GB. The screen switch requires at least 4 GB RAM and 2 vCPU; the published price depends on memory and disk. No new machine is needed if Maritime fixes the switch.
- **Separate persistent Linux computer:** $0.12/hour awake, billed per second against hosting credit. Sleeping disk is $0.08/GB-month; the Computers API does not report an allocated disk size in its response, so an exact sleeping-storage total has not been confirmed. One hour awake per day is about $3.60 over 30 days, plus sleeping disk. A continuously awake computer is $87.60 over a 730-hour billing month. This is additional to the calendar worker's hosting.
- **Model calls:** no model is required to prepare a browser or sign in. Future model-driven post extraction would be a separate cost decision.

Sources: [Maritime billing](https://maritime.sh/docs/billing), [persistent Linux desktops](https://maritime.sh/docs/computers), and the authenticated account's read-only billing/entitlement APIs.

## Login procedure

1. Use the private desktop's control/takeover page opened for you. Future access is through [Maritime Computers](https://maritime.sh/computers), selecting `club-alerts-instagram` and taking control. A new signed control link can also be minted through its Computers API.
2. Visit `https://www.instagram.com/accounts/login/`.
3. The account owner enters the password and any 2FA code directly on Instagram, then hands control back.
4. Keep the browser profile on the machine's persistent storage, reuse that same machine/profile, and never commit or export the session to the repository.

The computer sleeps after five idle minutes. Sleep retains its browser profile and login cookies, although Instagram can independently expire the login. Viewer links expire and are revoked when the computer sleeps or the takeover completes; use the same computer with a fresh link when needed. Do not delete the computer to stop compute billing, because deleting also destroys the saved profile.

The separate Instagram checker and review routing are implemented and deployed, pending owner sign-in and a successful reader check. Public checks run independently. No Instagram posts were imported during initial verification. Instagram may expire a session or require the owner to sign in again.
