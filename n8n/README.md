# Quad campus notifications

This n8n workflow sends two kinds of alerts based on Quad's published listings. Recipients can opt into either or both and optionally pick topics. The same workflow can send each message by Gmail, by phone through ntfy, or by both channels.

| Flow | Schedule in Vancouver | Message |
| --- | --- | --- |
| Morning digest | 8:00 a.m. daily, with retries at 8:10 and 8:20 | Today's matching events in time order. The phone version shows up to four and links to Quad. |
| One-hour reminder | Checks every ten minutes | The event name, current start time and venue, and a link to its event page. Normally sent 50–60 minutes before the start. Events with an unknown start time stay in the digest. |

1. Import [`quad-campus-notifications.json`](quad-campus-notifications.json) into n8n. Leave it unpublished while testing. Select **Preview both alerts** and run the workflow. Open **Inspect the digest and reminder** to see today's digest and an explicitly labeled sample reminder. The preview creates or reuses the receipt table and sends no messages.
2. In **Quad settings**, enter opted-in recipients in the workspace copy. Set a unique `id` for each person. Set `digest` and `reminder` separately. An empty `topics` list includes all topics. Set `emailEnabled` or `phoneEnabled` for the channels you plan to use. Keep real addresses and phone topics out of the exported file.
3. To send email, open **Send email via Gmail**. Create or select a Gmail credential, connect your Google account, then enable the node. For phone, install ntfy on the device and subscribe to the configured `phoneTopic`. Use a private topic for real subscribers or an unguessable topic for public sample content. An access token, if required by the topic, belongs in an n8n Header Auth credential on **Push to phone via ntfy**.
4. For one test delivery, set `testRecipientId` in **Quad settings** and set `mode` to `test` in **Select preview or test**. Run the manual trigger. The sample goes to that recipient's enabled channels. Confirm receipt before scheduling. Restore `mode` to `preview` when finished.
5. To start scheduled delivery, set `enabled = true` in **Quad settings** and publish the workflow. In **Executions**, inspect **Record successful delivery** for receipts and **Inspect delivery failures** for errors. The ledger skips a channel after it succeeds. A reminder for a rescheduled start has a new key. Keep one published copy of the workflow per receipt table so concurrent copies don't race to send the same message.

The workflow calls Quad's public event feed. It does not use the private dispatch endpoints or import Quad's existing subscriber list. The workspace owner manages the recipient list and each recipient's preferences in **Quad settings**.

To rebuild the import file after editing the planner, run `node n8n/build-workflow.mjs` from the repo root. Verify the planner with `node --test n8n/plan-notifications.test.mjs`.
