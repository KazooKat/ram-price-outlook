# r/buildapcsales post metadata (Arctic Shift archive)

Fetched: 2026-10-06

Sources:
- https://arctic-shift.photon-reddit.com/api/posts/search
- https://arctic-shift.photon-reddit.com/api/posts/search/aggregate
- https://github.com/ArthurHeitmann/arctic_shift/blob/master/api/README.md

Fields kept: id, created_utc, title, score, num_comments, link_flair_text, domain (derived from the post url). Score/num_comments are as of the archive's retrieval time, not final. One gzip JSONL file per UTC month. coverage.csv compares posts fetched per month with the archive's aggregate count (it matches exactly), but that only proves we pulled everything Arctic Shift holds; completeness against Reddit itself was not verifiable because reddit.com JSON returns 403 to unauthenticated clients. PullPush (api.pullpush.io) was tried first and rejected unauthenticated requests.
