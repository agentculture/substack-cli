# Substack API endpoints observed for substack-cli v1

Substack publishes no API. Everything below was **observed** on 2026-09-13
in the owner's logged-in Chrome session against `jetsonailab.substack.com`
(publication id `11024739`) and `substack.com`, using an in-page
`fetch`/XHR interceptor plus the browser's network log. Cookie and
`Authorization` headers are redacted throughout; ids of the throwaway
test post, comments and reactions created during the capture are kept
because they are already deleted. Anything not observed is marked
**not observed** and must not ship until it is.

Two API bases exist (spec claim c36):

| Base | Scope | Auth |
|------|-------|------|
| `https://<publication-host>/api/v1` | posts, drafts, comments, reactions, publication | public reads need no session; owner verbs need the session |
| `https://substack.com/api/v1` | the reader feed, account-level calls | session required |

Post and comment bodies are ProseMirror documents serialized as a JSON
**string** (`draft_body`, `body`) or as an object (`body_json` on comments).

## Legend

- **capture** — page and action that produced the request.
- Request/response shapes list the keys that matter to the CLI; objects
  carry many more keys than shown.

## Account (`account whoami`, `account overview`)

| Verb | Method and path | Auth | Capture |
|------|-----------------|------|---------|
| whoami | `GET <pub>/api/v1/subscription` | session | public post page, page load |
| whoami (publication) | `GET <pub>/api/v1/publication` | session | dashboard `/publish/home`, page load; **403** when anonymous |

- `GET /api/v1/subscription` → `{id, user_id, publication_id, email_disabled, email_settings, notification_settings, ...}`. This is the whoami source: `user_id` is the signed-in user on this publication host.
- `GET /api/v1/publication` → `{id, subdomain, name, custom_domain, logo_url, ...}` (owner only).
- `GET https://substack.com/api/v1/user/self` → **403 Not authorized** even when signed in. Not a whoami source.
- Sign-out signal (any owner endpoint): HTTP **401** with body `{"errors":[{"msg":"Please sign in", ...}]}` (observed on `substack.com/api/v1/feed/following` while anonymous).

## Post, public read side (`post list`, `post get`)

| Verb | Method and path | Auth | Capture |
|------|-----------------|------|---------|
| list | `GET <pub>/api/v1/archive?sort=new&offset=0&limit=N` | none | curl and in-page fetch |
| get | `GET <pub>/api/v1/posts/<slug>` | none | public post page, page load |

- archive → JSON array of post summaries: `id, publication_id, title, subtitle, slug, post_date, audience, type, canonical_url, reaction_count, comment_count, ...`. An empty publication answers `[]`.
- posts/`<slug>` → full post: `id, slug, title, subtitle, post_date, updated_at, publication_id, canonical_url, audience, type, is_published, reactions ({emoji: count}), restacks, write_comment_permissions, cover_image, body_html, description, previous_post_slug, next_post_slug, ...`.
- Note: after the test post was deleted the public archive still listed it for a short while (cache); treat archive as eventually consistent.

## Post, owner side (`post publish`, `post schedule`, `post unpublish`, `post delete`)

| Step | Method and path | Request body | Capture |
|------|-----------------|--------------|---------|
| create draft | `POST <pub>/api/v1/drafts` | `{"draft_title", "draft_body": "<ProseMirror JSON string>", "type": "newsletter", "audience": "everyone", "draft_bylines": [{"id": <user_id>, "is_guest": false}]}` | in-page fetch from the editor |
| update draft | `PUT <pub>/api/v1/drafts/<id>` | same keys plus `draft_subtitle`, `section_chosen`, `draft_section_id`, `translations`, `last_updated_at`; before publish the UI also sends `should_send_email`, `write_comment_permissions`, `meter_type`, `cover_image`, `search_engine_title/description`, `hide_from_feed` | editor autosave; publish dialog |
| read draft | `GET <pub>/api/v1/drafts/<id>` | — | editor |
| pre-flight | `GET <pub>/api/v1/drafts/<id>/prepublish?publish_date=<iso>` | — | publish dialog |
| publish | `POST <pub>/api/v1/drafts/<id>/publish` | `{"send": false, "saved_segment_id": null}` — `send: true` also emails subscribers (**not exercised**) | publish dialog, "Publish now" then "Publish on web only" |
| schedule | `POST <pub>/api/v1/drafts/<id>/scheduled_release` | `{"trigger_at": "<iso>", "post_audience": "everyone", "saved_segment_id": null}` | publish dialog with "Schedule time to publish" |
| unschedule | `DELETE <pub>/api/v1/drafts/<id>/scheduled_release` | — → `[<scheduled_release_id>]` | in-page fetch |
| unpublish | `POST <pub>/api/v1/drafts/<id>/unpublish` | `{}` → empty body; post returns to drafts | dashboard Posts list, "..." menu, Unpublish, confirm |
| delete | `DELETE <pub>/api/v1/drafts/<id>` | — → `{}`; works on drafts and on unpublished posts | in-page fetch |

- Draft/post objects carry: `id, publication_id, slug, type, audience, is_published, post_date, draft_title, draft_subtitle, draft_body, body, should_send_email, write_comment_permissions, draft_created_at, draft_updated_at, email_sent_at, word_count, ...`.
- `should_send_email` on the draft mirrors the dialog's "Send via email and the Substack app" checkbox; the publish call's `send` field is what actually decides whether email goes out. The CLI's `--no-email` maps to `send: false`.
- Listing the owner's posts: `GET <pub>/api/v1/post_management/{drafts,published,scheduled}?offset&limit&order_by&order_direction` → `{posts, offset, limit, total, isCapped}`; counts: `GET <pub>/api/v1/post_management/counts` → `{published, drafts, scheduled, *IsCapped}`.
- Draft body ProseMirror shape as sent by the editor: `{"type":"doc","content":[{"type":"paragraph","attrs":{"textAlign":null},"content":[{"type":"text","text":"..."}]}]}`.

## Comment (`comment list`, `comment reply`, `comment delete`)

| Verb | Method and path | Request body | Auth | Capture |
|------|-----------------|--------------|------|---------|
| list | `GET <pub>/api/v1/post/<post_id>/comments` (UI adds `?token=&all_comments=true&sort=best_first`) | — | none | public post page |
| create | `POST <pub>/api/v1/post/<post_id>/comment` | `{"body": "<text>"}` | session | comment box, "Post" |
| reply | `POST <pub>/api/v1/post/<post_id>/comment` | `{"body": "<text>", "parent_id": <comment_id>}` | session | "Reply" under a comment |
| delete | `DELETE <pub>/api/v1/comment/<comment_id>` | — → `{}` | session | in-page fetch (reply and top-level) |

- list → `{"comments": [...], "automod_hidden_comments": [...]}`; comment objects: `id, user_id, name, body, body_json, post_id, publication_id, ancestor_path ("" for top-level, "<parent_id>" for replies), type "comment", status "published", deleted, date, edited_at, reactions, children...`.
- create/reply respond with the created comment object (same shape).

## Reaction (`reaction list`, `reaction add`, `reaction remove`)

| Verb | Method and path | Request body | Auth | Capture |
|------|-----------------|--------------|------|---------|
| list (post) | `GET <pub>/api/v1/posts/<slug>` → `reactions` map | — | none | public post page |
| add (post) | `POST <pub>/api/v1/post/<post_id>/reaction` | `{"reaction": "❤"}` → `{}` | session | heart button on the post |
| remove (post) | `DELETE <pub>/api/v1/post/<post_id>/reaction` | — → `{}` | session | in-page fetch |
| add (comment) | `POST <pub>/api/v1/comment/<comment_id>/reaction` | `{"reaction": "❤"}` → `{}` | session | "Like" on a comment |
| remove (comment) | `DELETE <pub>/api/v1/comment/<comment_id>/reaction` | — → `{}` | session | in-page fetch |

- Only the heart emoji was exercised; other emoji values are **not observed**.
- Per-user reaction listing beyond the aggregate `reactions` map is **not observed**.

## Feed (`feed read`)

| Verb | Method and path | Auth | Capture |
|------|-----------------|------|---------|
| read (home) | `GET https://substack.com/api/v1/reader/feed?limit=N` → `{items, originalCursorTimestamp, nextCursor, trackingParameters}` | session | substack.com/home |
| read (following) | `GET https://substack.com/api/v1/feed/following?limit=N` → JSON array | session (401 when anonymous) | substack.com/home |

- `GET https://substack.com/api/v1/notes` → **404**; the Notes home feed is `reader/feed`.
- Posting a Note (`POST /api/v1/comment/feed`) is out of v1 scope and **not observed**.
- Item shapes inside `reader/feed.items` were **not captured** (the sandbox blocked a second script run on that tab); the CLI treats each item as an opaque object and renders `type`, author name, date and text fields when present.

## Not observed (do not ship)

- Any subscriber or statistics endpoint beyond the dashboard's own `publication/stats/*` and `subscriber-stats/saved-segments` GETs, which were seen but not inspected.
- Publish with `send: true` (email delivery).
- Emoji values other than `❤`.
- Notes creation, restacks, custom-domain publications, CSRF or extra headers (none were needed in-browser; the CLI goes through the browser session via webglass, so this is deferred until webglass-cli#17 lands).

## Incidental endpoints (ignore)

`firehose/batch` (telemetry), `posts/<id>/progress`, `posts/<id>/seen`,
`realtime/token`, `activity/unread`, `messages/unread-count`,
`user/writer_referrals/code` (editor side effect), `headline-tests/<id>`,
`press_kit/assets/...`, `video/*`, `live_stream*`.
