# Alabama — confirmed broken (dead server)

Any Alabama company will land in `manual_review_needed`. Confirmed, not a bug to chase.

**Official lookup:** Alabama Secretary of State, Business Entity Records
(https://www.sos.alabama.gov/government-records/business-entity-records) forwards to the actual
search backend at `arc-sos.state.al.us`, a legacy CGI system.

**Failure:** That backend is dead at the TCP level. Confirmed via a raw `curl` bypassing
Playwright/browser entirely — DNS resolves fine (216.226.179.218), but the connection itself times
out (server not accepting connections, not just slow). Alabama Dept of Revenue's own site has no
entity-status tool at all.

**Manual check:** https://www.sos.alabama.gov/government-records/business-entity-records (will
likely also fail to load, same dead backend) or request an official Certificate of
Existence/Compliance directly from the AL Secretary of State.

**Re-verify periodically** — state infrastructure does get fixed eventually, don't assume permanent.
