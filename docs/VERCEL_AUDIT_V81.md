# Jinshu V8.1 — deployment audit and DeepSeek integration

## Scope and baseline

Continue the full V8 runtime rather than replacing it with a browser mock. Local service mode and Vercel use `index.py -> unified.app -> jinshu.runtime.Runtime`. The historical V7 remains a backup; this change does not overwrite production `main` or existing data. Source baseline: `2fb2329b93f3c9bdbb1125c20df1b5ace148ae75` (application code matches the previous verified V8 snapshot).

## Fixed in this revision

- `DEEPSEEK_API_KEY`/`DEEPSEEK_MODEL`/`DEEPSEEK_BASE_URL` are resolved in the same server-side configuration used by both runtimes. Empty `CHAT_*` variables no longer shadow them. A complete generic `CHAT_*` triplet remains compatible; incomplete generic settings cannot borrow a DeepSeek key. DeepSeek credentials are restricted to the official HTTPS endpoint. External DeepSeek cannot be labelled `JINSHU_MODEL_SCOPE=local`.
- Header displays actual configured provider, model and V8.1 build identity. Missing credentials explicitly say not called; offline fixtures explicitly identify themselves. No browser key storage and no fake successful connection badge.
- DeepSeek bounded multi-stage calls disable thinking mode and retain existing harness prompts, evidence permissions and verification. Successful responses record actual returned model ID and token usage. Unauthorized, timeout, redirect, empty or truncated completions fail instead of returning a fabricated answer. The model-check API no longer labels an offline fixture response a real model call.
- Unsigned/forged requests are rejected before opening MongoDB/Milvus connections. Redis sockets and pool sizes are bounded; failed runtime initialization has a short per-process backoff. This is not a replacement for Vercel WAF or global abuse controls.
- Explicit FastAPI entrypoint and Python 3.12 project metadata; production dependencies pinned to the previous successful V8 CI versions. Browser/test packages are not production dependencies. Pyproject and pip lists are checked for consistency.
- Build imports the complete app without production credentials, checks critical runtime assets and exercises the homepage, status and static/API routes. It emits a dependency footprint diagnostic. Packaging exclusions retain `engine/backend`, `jinshu`, `unified` and synthetic opt-in tool inputs, while excluding local secrets, historical frontend, archives, tests and evidence.

## Not certified by these changes

The Vercel connector returned 403 for the existing `cxy-peters-projects` scope (`team_etAwwBaKnbplwCg3pTB0OUxm`), and the surfaced build-log/deploy tools returned tool-not-found. The prior preview commit `4611088338ff198e7c560f93940dc216aa0debd1` has a failed Vercel status. Its build logs were not accessible, so the specific historical build failure root cause is NOT established.

No real DeepSeek credential was available to this repair session. Protocol tests use an HTTP mock and are not provider availability, paid inference or full RAG quality acceptance. No production MongoDB, Redis, Milvus, embedding or reranker credentials have been verified. A DeepSeek key alone does not make the full RAG stack ready.

The standard FastAPI function bundle limit is 500MB as documented on 2026-09-25. Heavy native dependencies remain a packaging risk until the Vercel-generated artifact is measured. Nothing here silently removes document parsing, clustering or retrieval to fit a browser-only demo.

## Release gate

1. Run full Python, historical Node, browser and isolated-service CI on the pinned source commit. Check the actual workflow result, not the unrelated Vercel Preview Comments check.
2. Sync that exact source commit into the private release repo, including pyproject, requirements and packaging exclusions. Verify the new Vercel deployment status and build logs.
3. In the owning Vercel team, configure Preview and Production separately from `unified/environment.example`. Keys belong only in secret environment variables. MongoDB facts/tasks, Redis sessions/jobs, Milvus vectors, embeddings and reranking remain real services.
4. Create an editor and independent reviewer using the one-time bootstrap token; remove that token afterward. Run authenticated service checks and an explicitly consented model-check. Use synthetic/public data first; never upload employer secrets without authorization.
5. Verify upload, independent review, retrieval citations, eight tool tasks, exports, memory/feedback and restart durability. Only then promote the validated deployment to production. Keep the prior working production for rollback.

Official references: https://vercel.com/docs/frameworks/backend/fastapi ; https://api-docs.deepseek.com/ ; https://api-docs.deepseek.com/guides/thinking_mode/
