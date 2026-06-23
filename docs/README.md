# intextum Documentation

This folder captures the implementation-level documentation for the current
system. The root `README.md` stays focused on quick start and repository layout;
these pages go deeper into how the parts fit together.

## Pages

- [Architecture](architecture.md): system components, data flow, and storage.
- [Security](security.md): user auth, ACLs, worker auth, and task-scoped access.
- [Content Enrichment](content-enrichment.md): classification, chat extraction,
  schema design, examples, and versioning.
- [Chat And Deep Research](research.md): interactive chat, report generation,
  citations, research events, and follow-up context.
- [Worker Runtime](worker-runtime.md): worker capabilities, task lifecycle,
  backend proxies, and local/runtime profiles.
- [Operations](operations.md): local development, migrations, tests, and common
  maintenance tasks.

## Status

The Docker Compose stack is a development stack. Security notes in these docs
focus on application auth, ACLs, task authorization, and secret handling rather
than production network perimeter controls.
