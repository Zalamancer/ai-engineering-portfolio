# Saved failure examples

Pulled automatically from the latest run of each configuration. Judgments are by the local LLM judge; a human may disagree.

## fixed/dense/norerank (20260909-163651_fixed_dense_norerank)
### Wrong or partial answers (judge ≤3): 5
- **q004** (lookup, heldout): Which IPs does Uvicorn trust for proxy headers by default, and how do I trust everything?
  - gold: By default it trusts the $FORWARDED_ALLOW_IPS environment variable if set, otherwise 127.0.0.1. The literal '*' means trust everything.
  - system [answered]: By default, Uvicorn trusts no IPs for proxy headers; it does not trust any client IP addresses automatically [1][2]. To trust everything, you can configure Uvicorn to trust all clients by setting the value `"*"` in the `forwarded-allow-ips` option [3]. This should only be done when you are certain t
  - cited: [(1, 'uvicorn/deployment/index.md'), (2, 'fastapi/deployment/https.md'), (3, 'uvicorn/deployment/index.md')] · flags: ['unsupported_citation [3]: To trust everything, you can configure Uvicorn to trust all clients by setting t'] · top retrieved: ['uvicorn/deployment/index.md', 'fastapi/deployment/https.md', 'uvicorn/deployment/index.md']
- **q007** (lookup, dev): Why would I choose the httptools HTTP implementation in Uvicorn, and when can't I use it?
  - gold: httptools gives greater performance but is not compatible with PyPy.
  - system [answered]: You would choose the httptools HTTP implementation for better performance in HTTP/1.1 parsing, as it is a Python binding for the Node.js HTTP parser and provides greater performance than h11 [1][2]. However, you can't use httptools if it is not installed, as Uvicorn will fall back to h11 in that cas
  - cited: [(1, 'uvicorn/concepts/http-protocols.md'), (2, 'uvicorn/installation.md')] · flags: ['unsupported_citation [2]: You would choose the httptools HTTP implementation for better performance in HTT'] · top retrieved: ['uvicorn/concepts/http-protocols.md', 'uvicorn/installation.md', 'uvicorn/release-notes.md']
- **q011** (lookup, dev): Can JavaScript in the browser read Starlette's session cookie?
  - gold: No. SessionMiddleware always sets the session cookie with the HttpOnly flag, which prevents client-side JavaScript from accessing it.
  - system [answered]: Yes, JavaScript in the browser can read Starlette's session cookie if the cookie is marked with `httponly=False` and is accessible via the browser's `document.cookie`. However, if `httponly=True` is set, JavaScript cannot access the cookie, as this flag prevents access via JavaScript [2][5]. The def
  - cited: [(2, 'starlette/responses.md'), (5, 'starlette/middleware.md')] · flags: ["uncited_claim: Yes, JavaScript in the browser can read Starlette's session cookie if the cookie", 'unsupported_citation [5]: However, if `httponly=True` is set, JavaScript cannot access the cookie, as this', "unsupported_citation [5]: The default behavior in Starlette's `SessionMiddleware` is `httponly=False`, so "] · top retrieved: ['starlette/third-party-packages.md', 'starlette/responses.md', 'starlette/middleware.md']
- **q012** (lookup, heldout): I appended an item to request.session["cart"] in Starlette but it wasn't saved. Why?
  - gold: Changes to nested values are not tracked automatically; assign the updated value back (request.session["cart"] = cart) so the session is marked modified.
  - system [answered]: The session data was not saved because the SessionMiddleware in Starlette only provides read-only session access (session information is readable but not modifiable) [4]. Additionally, if no session storage backend is explicitly configured or if the session middleware is not properly set up, changes
  - cited: [(1, 'starlette/third-party-packages.md'), (4, 'starlette/middleware.md')] · flags: ['unsupported_citation [1]: Additionally, if no session storage backend is explicitly configured or if the s'] · top retrieved: ['starlette/third-party-packages.md', 'starlette/applications.md', 'starlette/middleware.md']

### Answered a question the corpus cannot answer (should have abstained): 0

### Abstained on an answerable question: 10
- **q005** (lookup, dev): What is the default maximum WebSocket message size in Uvicorn?
  - gold: 16777216 bytes (16 MB), set with --ws-max-size.
  - system [insufficient]: The default maximum WebSocket message size in Uvicorn is not specified in the provided passages.
  - cited: [] · flags: ['model_reported_insufficient'] · top retrieved: ['uvicorn/concepts/websockets.md', 'uvicorn/release-notes.md', 'uvicorn/release-notes.md']
- **q010** (lookup, dev): What does --timeout-graceful-shutdown do in Uvicorn?
  - gold: It is the maximum number of seconds to wait for a graceful shutdown; after that the server starts terminating requests.
  - system [insufficient]: The provided passages do not mention the `--timeout-graceful-shutdown` option or its function. Therefore, its behavior cannot be determined from the given context.
  - cited: [] · flags: ['model_reported_insufficient'] · top retrieved: ['uvicorn/server-behavior.md', 'uvicorn/concepts/lifespan.md', 'uvicorn/server-behavior.md']
- **q017** (lookup, heldout): How do I get the client's IP address and port from a Starlette Request?
  - gold: request.client.host gives the hostname or IP and request.client.port the port; request.client may be None.
  - system [insufficient]: 
  - cited: [] · flags: ['model_reported_insufficient'] · top retrieved: ['starlette/index.md', 'fastapi/release-notes.md', 'fastapi/tutorial/middleware.md']
- **q019** (lookup, heldout): What is the signature of Starlette's BackgroundTasks class and what is it for?
  - gold: BackgroundTasks(tasks=[]); it is used to add multiple background tasks to a response.
  - system [insufficient]: The signature of Starlette's `BackgroundTasks` class is not provided in the passages. While the passages describe its usage and functionality—such as running background tasks in a path operation function and merging tasks from multiple levels—the specific signature (i.e., function definition or para
  - cited: [(1, 'starlette/background.md'), (2, 'fastapi/tutorial/background-tasks.md'), (3, 'fastapi/tutorial/background-tasks.md'), (5, 'fastapi/tutorial/background-tasks.md')] · flags: ['model_reported_insufficient'] · top retrieved: ['starlette/background.md', 'fastapi/tutorial/background-tasks.md', 'fastapi/tutorial/background-tasks.md']

### Citations judged NOT_SUPPORTED: 16
- **q002** (lookup, dev): What happens when Uvicorn's --limit-concurrency limit is exceeded?
  - gold: Excess requests receive an immediate HTTP 503 response; they are not queued.
  - system [answered]: When Uvicorn's `--limit-concurrency` limit is exceeded, the excess requests receive a "503 Service Unavailable" response immediately and are not queued or held in the backlog [1][3]. The check occurs after a request's headers are fully received, and both open connections and in-flight tasks are coun
  - cited: [(1, 'uvicorn/server-behavior.md'), (3, 'uvicorn/server-behavior.md'), (5, 'uvicorn/server-behavior.md')] · flags: ["unsupported_citation [5]: The check occurs after a request's headers are fully received, and both open con"] · top retrieved: ['uvicorn/server-behavior.md', 'uvicorn/server-behavior.md', 'uvicorn/server-behavior.md']
- **q004** (lookup, heldout): Which IPs does Uvicorn trust for proxy headers by default, and how do I trust everything?
  - gold: By default it trusts the $FORWARDED_ALLOW_IPS environment variable if set, otherwise 127.0.0.1. The literal '*' means trust everything.
  - system [answered]: By default, Uvicorn trusts no IPs for proxy headers; it does not trust any client IP addresses automatically [1][2]. To trust everything, you can configure Uvicorn to trust all clients by setting the value `"*"` in the `forwarded-allow-ips` option [3]. This should only be done when you are certain t
  - cited: [(1, 'uvicorn/deployment/index.md'), (2, 'fastapi/deployment/https.md'), (3, 'uvicorn/deployment/index.md')] · flags: ['unsupported_citation [3]: To trust everything, you can configure Uvicorn to trust all clients by setting t'] · top retrieved: ['uvicorn/deployment/index.md', 'fastapi/deployment/https.md', 'uvicorn/deployment/index.md']
- **q007** (lookup, dev): Why would I choose the httptools HTTP implementation in Uvicorn, and when can't I use it?
  - gold: httptools gives greater performance but is not compatible with PyPy.
  - system [answered]: You would choose the httptools HTTP implementation for better performance in HTTP/1.1 parsing, as it is a Python binding for the Node.js HTTP parser and provides greater performance than h11 [1][2]. However, you can't use httptools if it is not installed, as Uvicorn will fall back to h11 in that cas
  - cited: [(1, 'uvicorn/concepts/http-protocols.md'), (2, 'uvicorn/installation.md')] · flags: ['unsupported_citation [2]: You would choose the httptools HTTP implementation for better performance in HTT'] · top retrieved: ['uvicorn/concepts/http-protocols.md', 'uvicorn/installation.md', 'uvicorn/release-notes.md']
- **q009** (lookup, heldout): What is the default value of --reload-delay in Uvicorn?
  - gold: 0.25 seconds between reload checks.
  - system [answered]: The default value of --reload-delay in Uvicorn is 0.25. This is stated in passage [2], which specifies that the default value for `--reload-delay` is 0.25. Additionally, passage [3] confirms that the `reload_delay` default was changed from `None` to `0.25` in version 0.18.3, further supporting this 
  - cited: [(1, 'uvicorn/release-notes.md'), (2, 'uvicorn/settings.md'), (3, 'uvicorn/release-notes.md')] · flags: ['uncited_claim: The default value of --reload-delay in Uvicorn is 0.25.', 'unsupported_citation [1]: Additionally, passage  confirms that the `reload_delay` default was changed from'] · top retrieved: ['uvicorn/release-notes.md', 'uvicorn/settings.md', 'uvicorn/release-notes.md']

### Ambiguity not surfaced: 2
- **q069** (ambiguous, heldout): How do I set the maximum size?
  - gold: Ambiguous: could be Uvicorn's WebSocket --ws-max-size, a FastAPI Query max_length, or HTTP 413 Content Too Large; the answer should name the interpretations.
  - system [answered]: You can set the maximum request body size using the `max_body_size` parameter in `RequestBodyLimitMiddleware`, which limits the total request body including uploaded files and multipart encoding overhead [2]. This middleware uses the `Content-Length` header to reject oversized bodies when possible a
  - cited: [(1, 'starlette/requests.md'), (2, 'starlette/middleware.md')] · flags: [] · top retrieved: ['starlette/requests.md', 'starlette/middleware.md', 'starlette/release-notes.md']
- **q073** (ambiguous, heldout): How long is keep-alive?
  - gold: Ambiguous: Uvicorn's --timeout-keep-alive defaults to 5 seconds, while in HTTP/1.1 (RFC 9112) 'keep-alive' is a connection option for HTTP/1.0 persistence with no fixed duration; the answer should separate the two.
  - system [insufficient]: The provided passages do not specify how long a keep-alive connection lasts. While [5] mentions conditions under which a connection persists, it does not define a duration for keep-alive. The passage notes that keep-alive behavior depends on protocol version, headers, and client capabilities, but no
  - cited: [(5, 'rfc/rfc9112-http11.txt')] · flags: ['model_reported_insufficient'] · top retrieved: ['uvicorn/concepts/lifespan.md', 'rfc/rfc6265-http-cookies.html', 'starlette/lifespan.md']

### Gold evidence not retrieved (retrieval miss): 28
- **q001** (lookup, dev): What is the default value of Uvicorn's --timeout-keep-alive option?
  - gold: 5 seconds. Keep-Alive connections are closed if no new data is received within this timeout.
  - system [answered]: The default value of Uvicorn's --timeout-keep-alive option is 5 seconds [1][5].
  - cited: [(1, 'uvicorn/server-behavior.md'), (5, 'uvicorn/server-behavior.md')] · flags: [] · top retrieved: ['uvicorn/server-behavior.md', 'uvicorn/release-notes.md', 'uvicorn/concepts/lifespan.md']
- **q002** (lookup, dev): What happens when Uvicorn's --limit-concurrency limit is exceeded?
  - gold: Excess requests receive an immediate HTTP 503 response; they are not queued.
  - system [answered]: When Uvicorn's `--limit-concurrency` limit is exceeded, the excess requests receive a "503 Service Unavailable" response immediately and are not queued or held in the backlog [1][3]. The check occurs after a request's headers are fully received, and both open connections and in-flight tasks are coun
  - cited: [(1, 'uvicorn/server-behavior.md'), (3, 'uvicorn/server-behavior.md'), (5, 'uvicorn/server-behavior.md')] · flags: ["unsupported_citation [5]: The check occurs after a request's headers are fully received, and both open con"] · top retrieved: ['uvicorn/server-behavior.md', 'uvicorn/server-behavior.md', 'uvicorn/server-behavior.md']
- **q003** (lookup, dev): How many worker processes does Uvicorn start if I don't pass --workers?
  - gold: It uses the $WEB_CONCURRENCY environment variable if set, otherwise 1. The option is not valid together with --reload.
  - system [answered]: If you don't pass the `--workers` command line option, Uvicorn starts a single worker process [1][3]. This is the default behavior when running Uvicorn without specifying the number of workers.
  - cited: [(1, 'fastapi/deployment/server-workers.md'), (3, 'fastapi/deployment/server-workers.md')] · flags: ['uncited_claim: This is the default behavior when running Uvicorn without specifying the number '] · top retrieved: ['fastapi/deployment/server-workers.md', 'uvicorn/deployment/docker.md', 'fastapi/deployment/server-workers.md']
- **q004** (lookup, heldout): Which IPs does Uvicorn trust for proxy headers by default, and how do I trust everything?
  - gold: By default it trusts the $FORWARDED_ALLOW_IPS environment variable if set, otherwise 127.0.0.1. The literal '*' means trust everything.
  - system [answered]: By default, Uvicorn trusts no IPs for proxy headers; it does not trust any client IP addresses automatically [1][2]. To trust everything, you can configure Uvicorn to trust all clients by setting the value `"*"` in the `forwarded-allow-ips` option [3]. This should only be done when you are certain t
  - cited: [(1, 'uvicorn/deployment/index.md'), (2, 'fastapi/deployment/https.md'), (3, 'uvicorn/deployment/index.md')] · flags: ['unsupported_citation [3]: To trust everything, you can configure Uvicorn to trust all clients by setting t'] · top retrieved: ['uvicorn/deployment/index.md', 'fastapi/deployment/https.md', 'uvicorn/deployment/index.md']

## recursive/hybrid/rerank (20260909-180754_recursive_hybrid_rerank)
### Wrong or partial answers (judge ≤3): 3
- **q004** (lookup, heldout): Which IPs does Uvicorn trust for proxy headers by default, and how do I trust everything?
  - gold: By default it trusts the $FORWARDED_ALLOW_IPS environment variable if set, otherwise 127.0.0.1. The literal '*' means trust everything.
  - system [answered]: By default, Uvicorn trusts no IPs for proxy headers, as it requires explicit configuration to trust any IP addresses [3]. To trust everything, set `--forwarded-allow-ips="*"` to accept all incoming IPs, which should only be done when you know the proxies remove or correctly set the forwarded headers
  - cited: [(1, 'fastapi/advanced/behind-a-proxy.md'), (2, 'uvicorn/deployment/index.md'), (3, 'uvicorn/deployment/index.md'), (5, 'fastapi/deployment/https.md')] · flags: ['unsupported_citation [2]: To trust everything, set `--forwarded-allow-ips="*"` to accept all incoming IPs,'] · top retrieved: ['fastapi/advanced/behind-a-proxy.md', 'uvicorn/deployment/index.md', 'uvicorn/deployment/index.md']
- **q008** (lookup, dev): Is the uvicorn.workers Gunicorn worker class still supported?
  - gold: No. The uvicorn.workers module is deprecated and will be removed; use the separate uvicorn-worker package instead.
  - system [answered]: Yes, the `uvicorn.workers` Gunicorn worker class is still supported, but it is deprecated and will be removed in a future release. Users are advised to use the `uvicorn-worker` package instead [2][3].
  - cited: [(2, 'uvicorn/index.md'), (3, 'uvicorn/deployment/index.md')] · flags: ['uncited_claim: Yes, the `uvicorn.workers` Gunicorn worker class is still supported, but it is d'] · top retrieved: ['uvicorn/deployment/index.md', 'uvicorn/index.md', 'uvicorn/deployment/index.md']
- **q059** (multi_hop, dev): Which forwarded headers does Uvicorn's --proxy-headers option read, and why do the FastAPI deployment docs say they are needed behind a TLS termination proxy?
  - gold: Uvicorn reads X-Forwarded-Proto and X-Forwarded-For to populate remote address info. FastAPI's HTTPS docs explain that behind a TLS termination proxy the app only sees plain HTTP from the proxy, so it needs these headers
  - system [answered]: Uvicorn's `--proxy-headers` option reads the forwarded headers: `X-Forwarded-For`, `X-Forwarded-Proto`, and `X-Forwarded-Host` [3][5]. The FastAPI deployment docs state these headers are needed behind a TLS termination proxy because the proxy handles HTTPS and forwards the request with headers indic
  - cited: [(1, 'uvicorn/deployment/index.md'), (3, 'fastapi/deployment/https.md'), (5, 'fastapi/advanced/behind-a-proxy.md')] · flags: [] · top retrieved: ['uvicorn/deployment/index.md', 'fastapi/advanced/behind-a-proxy.md', 'fastapi/deployment/https.md']

### Answered a question the corpus cannot answer (should have abstained): 0

### Abstained on an answerable question: 8
- **q006** (lookup, heldout): What does Uvicorn's --ws-max-queue setting control and which protocol implementation supports it?
  - gold: It sets the maximum length of the WebSocket incoming message queue (default 32) and is only available with the websockets protocol implementation.
  - system [insufficient]: The passages do not mention the `--ws-max-queue` setting or specify which protocol implementation supports it. Therefore, its function and associated protocol cannot be determined from the provided context.
  - cited: [] · flags: ['model_reported_insufficient'] · top retrieved: ['uvicorn/concepts/websockets.md', 'uvicorn/concepts/websockets.md', 'uvicorn/server-behavior.md']
- **q017** (lookup, heldout): How do I get the client's IP address and port from a Starlette Request?
  - gold: request.client.host gives the hostname or IP and request.client.port the port; request.client may be None.
  - system [insufficient]: The provided passages do not contain information on how to extract the client's IP address and port from a Starlette Request. While the passages mention accessing request properties like `request.method` or `request.url`, they do not specify methods for obtaining the client's IP or port [1][5].
  - cited: [(1, 'starlette/requests.md'), (5, 'starlette/middleware.md')] · flags: ['model_reported_insufficient'] · top retrieved: ['starlette/requests.md', 'fastapi/advanced/using-request-directly.md', 'starlette/testclient.md']
- **q019** (lookup, heldout): What is the signature of Starlette's BackgroundTasks class and what is it for?
  - gold: BackgroundTasks(tasks=[]); it is used to add multiple background tasks to a response.
  - system [insufficient]: The passages do not provide the signature of Starlette's `BackgroundTasks` class. While they describe its usage and benefits, such as being used as a path operation function parameter and handling background tasks in FastAPI, no explicit signature is given [2][4]. The `BackgroundTask` class is menti
  - cited: [(2, 'fastapi/tutorial/background-tasks.md'), (4, 'starlette/background.md')] · flags: ['model_reported_insufficient'] · top retrieved: ['starlette/background.md', 'fastapi/tutorial/background-tasks.md', 'starlette/middleware.md']
- **q026** (lookup, dev): How do I restrict a FastAPI path parameter to a fixed set of values?
  - gold: Create an Enum subclass that inherits from both str and Enum, and use it as the parameter's type; inheriting from str lets the docs render the values as strings.
  - system [insufficient]: 
  - cited: [] · flags: ['model_reported_insufficient'] · top retrieved: ['fastapi/release-notes.md', 'fastapi/tutorial/response-model.md', 'fastapi/tutorial/body.md']

### Citations judged NOT_SUPPORTED: 9
- **q004** (lookup, heldout): Which IPs does Uvicorn trust for proxy headers by default, and how do I trust everything?
  - gold: By default it trusts the $FORWARDED_ALLOW_IPS environment variable if set, otherwise 127.0.0.1. The literal '*' means trust everything.
  - system [answered]: By default, Uvicorn trusts no IPs for proxy headers, as it requires explicit configuration to trust any IP addresses [3]. To trust everything, set `--forwarded-allow-ips="*"` to accept all incoming IPs, which should only be done when you know the proxies remove or correctly set the forwarded headers
  - cited: [(1, 'fastapi/advanced/behind-a-proxy.md'), (2, 'uvicorn/deployment/index.md'), (3, 'uvicorn/deployment/index.md'), (5, 'fastapi/deployment/https.md')] · flags: ['unsupported_citation [2]: To trust everything, set `--forwarded-allow-ips="*"` to accept all incoming IPs,'] · top retrieved: ['fastapi/advanced/behind-a-proxy.md', 'uvicorn/deployment/index.md', 'uvicorn/deployment/index.md']
- **q014** (lookup, dev): Which two middleware does every Starlette application include by default?
  - gold: ServerErrorMiddleware (always the outermost layer; custom 500 page or traceback in debug) and ExceptionMiddleware (exception handlers).
  - system [answered]: Every Starlette application includes `ServerErrorMiddleware` and `ExceptionMiddleware` by default [1][2].
  - cited: [(1, 'starlette/middleware.md'), (2, 'starlette/middleware.md')] · flags: ['unsupported_citation [2]: Every Starlette application includes `ServerErrorMiddleware` and `ExceptionMiddl'] · top retrieved: ['starlette/middleware.md', 'starlette/middleware.md', 'starlette/middleware.md']
- **q022** (lookup, heldout): How many times may a FastAPI dependency use yield?
  - gold: Exactly once per dependency; the code after the yield runs as the extra/cleanup steps.
  - system [answered]: A FastAPI dependency may use `yield` only one time per dependency [1]. This is because the documentation explicitly states, "Make sure to use `yield` one single time per dependency" [1]. Multiple uses of `yield` are not permitted, as the design relies on a single `yield` to manage context and exit c
  - cited: [(1, 'fastapi/tutorial/dependencies/dependencies-with-yield.md'), (3, 'fastapi/tutorial/dependencies/dependencies-with-yield.md')] · flags: ['unsupported_citation [3]: Multiple uses of `yield` are not permitted, as the design relies on a single `yi'] · top retrieved: ['fastapi/tutorial/dependencies/dependencies-with-yield.md', 'fastapi/advanced/advanced-dependencies.md', 'fastapi/tutorial/dependencies/dependencies-with-yield.md']
- **q023** (lookup, dev): Should I return or raise HTTPException in FastAPI?
  - gold: Raise it. HTTPException is a normal Python exception with extra API data, so you raise rather than return it.
  - system [answered]: You should raise, not return, an HTTPException in FastAPI. Raising an HTTPException terminates the request immediately and sends the error to the client, which is the intended behavior for error handling [5]. Returning it would not trigger the HTTP error response as expected [5]. The exception must 
  - cited: [(4, 'fastapi/reference/exceptions.md'), (5, 'fastapi/tutorial/handling-errors.md')] · flags: ['uncited_claim: You should raise, not return, an HTTPException in FastAPI.', 'unsupported_citation [5]: Returning it would not trigger the HTTP error response as expected.'] · top retrieved: ['fastapi/tutorial/handling-errors.md', 'fastapi/tutorial/dependencies/dependencies-with-yield.md', 'fastapi/tutorial/handling-errors.md']

### Ambiguity not surfaced: 3
- **q069** (ambiguous, heldout): How do I set the maximum size?
  - gold: Ambiguous: could be Uvicorn's WebSocket --ws-max-size, a FastAPI Query max_length, or HTTP 413 Content Too Large; the answer should name the interpretations.
  - system [answered]: You can set the maximum size of the request body using `max_body_size` in the application or route configuration, which limits the total request body bytes including multipart file data and encoding overhead [2][4]. For multipart form data, individual part sizes can also be limited using `max_part_s
  - cited: [(1, 'starlette/requests.md'), (2, 'starlette/routing.md'), (4, 'starlette/middleware.md'), (5, 'starlette/release-notes.md')] · flags: [] · top retrieved: ['starlette/requests.md', 'starlette/routing.md', 'fastapi/tutorial/query-params-str-validations.md']
- **q070** (ambiguous, dev): How do I enable HTTPS?
  - gold: Ambiguous: Uvicorn can terminate TLS itself with --ssl-keyfile/--ssl-certfile, the FastAPI deployment docs recommend a TLS termination proxy, and Starlette offers HTTPSRedirectMiddleware to force https; the answer should
  - system [answered]: To enable HTTPS, you first need to acquire a domain name and configure an A record in your DNS to point to the public IP address of your server [2]. Then, you can use the SNI extension in TLS to serve multiple HTTPS domains from a single IP address, provided the server has all the required HTTPS cer
  - cited: [(2, 'fastapi/deployment/https.md'), (3, 'fastapi/deployment/https.md'), (5, 'fastapi/deployment/concepts.md')] · flags: [] · top retrieved: ['fastapi/deployment/https.md', 'fastapi/deployment/https.md', 'fastapi/deployment/https.md']
- **q073** (ambiguous, heldout): How long is keep-alive?
  - gold: Ambiguous: Uvicorn's --timeout-keep-alive defaults to 5 seconds, while in HTTP/1.1 (RFC 9112) 'keep-alive' is a connection option for HTTP/1.0 persistence with no fixed duration; the answer should separate the two.
  - system [answered]: The keep-alive timeout is 5 seconds by default [1][2]. This timeout determines how long a connection remains open after the current request before being disconnected if no new data is received [1][2].
  - cited: [(1, 'uvicorn/server-behavior.md'), (2, 'uvicorn/settings.md')] · flags: [] · top retrieved: ['uvicorn/server-behavior.md', 'uvicorn/settings.md', 'rfc/rfc9112-http11.txt']

### Gold evidence not retrieved (retrieval miss): 12
- **q002** (lookup, dev): What happens when Uvicorn's --limit-concurrency limit is exceeded?
  - gold: Excess requests receive an immediate HTTP 503 response; they are not queued.
  - system [answered]: When Uvicorn's `--limit-concurrency` limit is exceeded, the server responds immediately with a "503 Service Unavailable" error. The request is not queued and does not wait for a slot to free up. Both the number of open connections and in-flight requests are counted toward the limit, and once the lim
  - cited: [(1, 'uvicorn/server-behavior.md'), (5, 'uvicorn/server-behavior.md')] · flags: ["uncited_claim: When Uvicorn's `--limit-concurrency` limit is exceeded, the server responds imme", 'uncited_claim: The request is not queued and does not wait for a slot to free up.'] · top retrieved: ['uvicorn/server-behavior.md', 'uvicorn/server-behavior.md', 'uvicorn/deployment/index.md']
- **q003** (lookup, dev): How many worker processes does Uvicorn start if I don't pass --workers?
  - gold: It uses the $WEB_CONCURRENCY environment variable if set, otherwise 1. The option is not valid together with --reload.
  - system [answered]: If you don't pass the `--workers` flag, Uvicorn starts a single worker process by default. This is implied by the context that the `--workers` option is used to specify the number of worker processes, and without it, the default behavior is one process [1][3][5].
  - cited: [(1, 'fastapi/deployment/server-workers.md'), (3, 'uvicorn/deployment/index.md'), (5, 'fastapi/deployment/server-workers.md')] · flags: ["uncited_claim: If you don't pass the `--workers` flag, Uvicorn starts a single worker process b"] · top retrieved: ['fastapi/deployment/server-workers.md', 'uvicorn/deployment/index.md', 'uvicorn/deployment/index.md']
- **q004** (lookup, heldout): Which IPs does Uvicorn trust for proxy headers by default, and how do I trust everything?
  - gold: By default it trusts the $FORWARDED_ALLOW_IPS environment variable if set, otherwise 127.0.0.1. The literal '*' means trust everything.
  - system [answered]: By default, Uvicorn trusts no IPs for proxy headers, as it requires explicit configuration to trust any IP addresses [3]. To trust everything, set `--forwarded-allow-ips="*"` to accept all incoming IPs, which should only be done when you know the proxies remove or correctly set the forwarded headers
  - cited: [(1, 'fastapi/advanced/behind-a-proxy.md'), (2, 'uvicorn/deployment/index.md'), (3, 'uvicorn/deployment/index.md'), (5, 'fastapi/deployment/https.md')] · flags: ['unsupported_citation [2]: To trust everything, set `--forwarded-allow-ips="*"` to accept all incoming IPs,'] · top retrieved: ['fastapi/advanced/behind-a-proxy.md', 'uvicorn/deployment/index.md', 'uvicorn/deployment/index.md']
- **q006** (lookup, heldout): What does Uvicorn's --ws-max-queue setting control and which protocol implementation supports it?
  - gold: It sets the maximum length of the WebSocket incoming message queue (default 32) and is only available with the websockets protocol implementation.
  - system [insufficient]: The passages do not mention the `--ws-max-queue` setting or specify which protocol implementation supports it. Therefore, its function and associated protocol cannot be determined from the provided context.
  - cited: [] · flags: ['model_reported_insufficient'] · top retrieved: ['uvicorn/concepts/websockets.md', 'uvicorn/concepts/websockets.md', 'uvicorn/server-behavior.md']

## recursive/dense/rerank (20260909-183143_recursive_dense_rerank)
### Wrong or partial answers (judge ≤3): 7
- **q003** (lookup, dev): How many worker processes does Uvicorn start if I don't pass --workers?
  - gold: It uses the $WEB_CONCURRENCY environment variable if set, otherwise 1. The option is not valid together with --reload.
  - system [answered]: The number of worker processes Uvicorn starts without the `--workers` flag is not specified in the provided passages. While passages [1] and [3] mention starting with `--workers 4`, they do not state the default number of workers when `--workers` is omitted. Therefore, the default value cannot be de
  - cited: [(1, 'fastapi/deployment/server-workers.md'), (3, 'uvicorn/deployment/index.md')] · flags: ['uncited_claim: The number of worker processes Uvicorn starts without the `--workers` flag is no', 'uncited_claim: Therefore, the default value cannot be determined from the given information.'] · top retrieved: ['fastapi/deployment/server-workers.md', 'uvicorn/deployment/index.md', 'uvicorn/deployment/index.md']
- **q004** (lookup, heldout): Which IPs does Uvicorn trust for proxy headers by default, and how do I trust everything?
  - gold: By default it trusts the $FORWARDED_ALLOW_IPS environment variable if set, otherwise 127.0.0.1. The literal '*' means trust everything.
  - system [answered]: By default, Uvicorn trusts no IPs for proxy headers, as it requires explicit configuration to trust any IP addresses or networks [3]. To trust everything, set the `--forwarded-allow-ips="*"` option, which instructs Uvicorn to accept all incoming IPs, but only do so when you know the proxies have cor
  - cited: [(1, 'fastapi/advanced/behind-a-proxy.md'), (2, 'uvicorn/deployment/index.md'), (3, 'uvicorn/deployment/index.md')] · flags: [] · top retrieved: ['fastapi/advanced/behind-a-proxy.md', 'uvicorn/deployment/index.md', 'uvicorn/deployment/index.md']
- **q008** (lookup, dev): Is the uvicorn.workers Gunicorn worker class still supported?
  - gold: No. The uvicorn.workers module is deprecated and will be removed; use the separate uvicorn-worker package instead.
  - system [answered]: Yes, the `uvicorn.workers` Gunicorn worker class is still supported, but it is deprecated and will be removed in a future release. Users are advised to use the `uvicorn-worker` package instead [2][3].
  - cited: [(2, 'uvicorn/index.md'), (3, 'uvicorn/deployment/index.md')] · flags: ['uncited_claim: Yes, the `uvicorn.workers` Gunicorn worker class is still supported, but it is d'] · top retrieved: ['uvicorn/deployment/index.md', 'uvicorn/index.md', 'uvicorn/deployment/index.md']
- **q016** (lookup, dev): My Starlette lifespan handler doesn't run in tests with TestClient. What am I missing?
  - gold: The TestClient must be used as a context manager (with TestClient(app) as client) for the lifespan handler to run; it is not triggered on instantiation.
  - system [answered]: You are missing the use of the `TestClient` as a context manager, which is required for the lifespan handler to be triggered during tests. The lifespan will not run if the `TestClient` is instantiated without a `with` statement [3][2]. Additionally, the lifespan should be wrapped in an `@contextlib.
  - cited: [(2, 'starlette/lifespan.md'), (3, 'starlette/testclient.md'), (5, 'starlette/release-notes.md')] · flags: ['uncited_claim: You are missing the use of the `TestClient` as a context manager, which is requi'] · top retrieved: ['fastapi/advanced/testing-events.md', 'starlette/lifespan.md', 'starlette/testclient.md']

### Answered a question the corpus cannot answer (should have abstained): 0

### Abstained on an answerable question: 9
- **q005** (lookup, dev): What is the default maximum WebSocket message size in Uvicorn?
  - gold: 16777216 bytes (16 MB), set with --ws-max-size.
  - system [insufficient]: The passages do not specify the default maximum WebSocket message size in Uvicorn. While [1] mentions a default `ws max_size` of 16MB, it refers to the server's default for the WebSocket maximum size, and does not confirm whether this is the message size or a different configuration. The term "max_s
  - cited: [(1, 'uvicorn/release-notes.md'), (4, 'uvicorn/release-notes.md')] · flags: ['model_reported_insufficient'] · top retrieved: ['uvicorn/release-notes.md', 'uvicorn/release-notes.md', 'uvicorn/release-notes.md']
- **q006** (lookup, heldout): What does Uvicorn's --ws-max-queue setting control and which protocol implementation supports it?
  - gold: It sets the maximum length of the WebSocket incoming message queue (default 32) and is only available with the websockets protocol implementation.
  - system [insufficient]: The passages do not mention the `--ws-max-queue` setting or specify which WebSocket protocol implementation supports it. [1][3][4][5] discuss WebSocket and HTTP protocol implementations but do not address this specific setting.
  - cited: [(1, 'uvicorn/concepts/websockets.md'), (3, 'uvicorn/concepts/http-protocols.md'), (4, 'uvicorn/concepts/lifespan.md'), (5, 'uvicorn/index.md')] · flags: ['model_reported_insufficient'] · top retrieved: ['uvicorn/concepts/websockets.md', 'uvicorn/server-behavior.md', 'uvicorn/concepts/http-protocols.md']
- **q017** (lookup, heldout): How do I get the client's IP address and port from a Starlette Request?
  - gold: request.client.host gives the hostname or IP and request.client.port the port; request.client may be None.
  - system [insufficient]: 
  - cited: [] · flags: ['model_reported_insufficient'] · top retrieved: ['starlette/requests.md', 'starlette/testclient.md', 'starlette/authentication.md']
- **q019** (lookup, heldout): What is the signature of Starlette's BackgroundTasks class and what is it for?
  - gold: BackgroundTasks(tasks=[]); it is used to add multiple background tasks to a response.
  - system [insufficient]: The passages do not provide the signature of Starlette's `BackgroundTasks` class. While [2] mentions that `BackgroundTasks` comes from `starlette.background` and is used in FastAPI, it does not specify its signature. The passage only describes its purpose and usage in FastAPI, not its exact function
  - cited: [(2, 'fastapi/tutorial/background-tasks.md')] · flags: ['model_reported_insufficient'] · top retrieved: ['starlette/background.md', 'fastapi/tutorial/background-tasks.md', 'starlette/responses.md']

### Citations judged NOT_SUPPORTED: 10
- **q013** (lookup, dev): When does Starlette's GZipMiddleware compress a response?
  - gold: For any request whose Accept-Encoding header includes "gzip"; it handles both standard and streaming responses.
  - system [answered]: Starlette's GZipMiddleware compresses a response when the request includes `"gzip"` in the `Accept-Encoding` header. It will not compress responses that already have a `Content-Encoding` set, to prevent double encoding [2]. It also does not compress partial content responses (status `206`) to preser
  - cited: [(2, 'starlette/release-notes.md'), (5, 'starlette/middleware.md')] · flags: ['uncited_claim: Starlette\'s GZipMiddleware compresses a response when the request includes `"gzi', 'unsupported_citation [2]: It also does not compress partial content responses (status `206`) to preserve r'] · top retrieved: ['starlette/middleware.md', 'starlette/release-notes.md', 'starlette/third-party-packages.md']
- **q018** (lookup, dev): In what order does Starlette's Config read a configuration value?
  - gold: First from an environment variable, then from the .env file, then the default given in config(); if none match it raises an error.
  - system [answered]: Starlette's Config reads configuration values in the order of environment variables first, then from a `.env` file if specified. If both are present, environment variables take precedence over the `.env` file. The configuration is read during initialization, and once read, environment variables are 
  - cited: [(1, 'starlette/config.md'), (2, 'starlette/config.md'), (3, 'starlette/config.md'), (4, 'starlette/config.md')] · flags: ["uncited_claim: Starlette's Config reads configuration values in the order of environment variab", 'uncited_claim: If both are present, environment variables take precedence over the `.env` file.', 'unsupported_citation [3]: The configuration is read during initialization, and once read, environment vari'] · top retrieved: ['starlette/config.md', 'starlette/config.md', 'starlette/config.md']
- **q022** (lookup, heldout): How many times may a FastAPI dependency use yield?
  - gold: Exactly once per dependency; the code after the yield runs as the extra/cleanup steps.
  - system [answered]: A FastAPI dependency may use `yield` only one time per dependency [1]. This is because the documentation explicitly states, "Make sure to use `yield` one single time per dependency" [1]. Multiple uses of `yield` are not permitted, as the design relies on a single `yield` to manage context and exit c
  - cited: [(1, 'fastapi/tutorial/dependencies/dependencies-with-yield.md'), (3, 'fastapi/tutorial/dependencies/dependencies-with-yield.md')] · flags: ['unsupported_citation [3]: Multiple uses of `yield` are not permitted, as the design relies on a single `yi'] · top retrieved: ['fastapi/tutorial/dependencies/dependencies-with-yield.md', 'fastapi/advanced/advanced-dependencies.md', 'fastapi/tutorial/dependencies/dependencies-with-yield.md']
- **q023** (lookup, dev): Should I return or raise HTTPException in FastAPI?
  - gold: Raise it. HTTPException is a normal Python exception with extra API data, so you raise rather than return it.
  - system [answered]: You should raise, not return, an HTTPException in FastAPI. Raising an HTTPException terminates the request immediately and sends the error to the client, which is the intended behavior for error handling [5]. Returning it would not trigger the HTTP error response as expected [5]. The exception must 
  - cited: [(1, 'fastapi/tutorial/handling-errors.md'), (4, 'fastapi/reference/exceptions.md'), (5, 'fastapi/tutorial/handling-errors.md')] · flags: ['uncited_claim: You should raise, not return, an HTTPException in FastAPI.', 'unsupported_citation [5]: Returning it would not trigger the HTTP error response as expected.', 'unsupported_citation [1]: The exception must be raised, not returned, to properly handle errors in path op'] · top retrieved: ['fastapi/tutorial/handling-errors.md', 'fastapi/tutorial/dependencies/dependencies-with-yield.md', 'fastapi/tutorial/handling-errors.md']

### Ambiguity not surfaced: 3
- **q069** (ambiguous, heldout): How do I set the maximum size?
  - gold: Ambiguous: could be Uvicorn's WebSocket --ws-max-size, a FastAPI Query max_length, or HTTP 413 Content Too Large; the answer should name the interpretations.
  - system [answered]: You can set the maximum request body size using `max_body_size` in the application or route configuration, which limits the total bytes of the request body including multipart file data and encoding overhead [2][4]. For multipart form data, the size of individual parts can also be limited using `max
  - cited: [(1, 'starlette/requests.md'), (2, 'starlette/routing.md'), (4, 'starlette/middleware.md'), (5, 'starlette/release-notes.md')] · flags: [] · top retrieved: ['starlette/requests.md', 'starlette/routing.md', 'fastapi/tutorial/query-params-str-validations.md']
- **q070** (ambiguous, dev): How do I enable HTTPS?
  - gold: Ambiguous: Uvicorn can terminate TLS itself with --ssl-keyfile/--ssl-certfile, the FastAPI deployment docs recommend a TLS termination proxy, and Starlette offers HTTPSRedirectMiddleware to force https; the answer should
  - system [insufficient]: The provided passages discuss HTTPS in general and its implementation for developers, including the use of SNI to support multiple certificates on a single IP address, and mention that HTTPS requires a domain name, DNS configuration, and a public IP address [4]. However, the passages do not contain 
  - cited: [(4, 'fastapi/deployment/https.md')] · flags: ['model_reported_insufficient'] · top retrieved: ['fastapi/deployment/https.md', 'uvicorn/concepts/http2.md', 'uvicorn/concepts/http2.md']
- **q073** (ambiguous, heldout): How long is keep-alive?
  - gold: Ambiguous: Uvicorn's --timeout-keep-alive defaults to 5 seconds, while in HTTP/1.1 (RFC 9112) 'keep-alive' is a connection option for HTTP/1.0 persistence with no fixed duration; the answer should separate the two.
  - system [answered]: The default keep-alive timeout is 5 seconds [1][2]. This timeout applies to connections that are kept alive, and after this period, if no new data is received, the connection will be disconnected [2].
  - cited: [(1, 'uvicorn/server-behavior.md'), (2, 'uvicorn/settings.md')] · flags: [] · top retrieved: ['uvicorn/server-behavior.md', 'uvicorn/settings.md', 'rfc/rfc9112-http11.txt']

### Gold evidence not retrieved (retrieval miss): 14
- **q002** (lookup, dev): What happens when Uvicorn's --limit-concurrency limit is exceeded?
  - gold: Excess requests receive an immediate HTTP 503 response; they are not queued.
  - system [answered]: When Uvicorn's `--limit-concurrency` limit is exceeded, the server responds immediately with a "503 Service Unavailable" to the request, and the request is not queued or processed later [1]. This behavior occurs after the request's headers have been fully received, and the limit applies to both open
  - cited: [(1, 'uvicorn/server-behavior.md'), (5, 'uvicorn/server-behavior.md')] · flags: [] · top retrieved: ['uvicorn/server-behavior.md', 'uvicorn/server-behavior.md', 'uvicorn/deployment/index.md']
- **q003** (lookup, dev): How many worker processes does Uvicorn start if I don't pass --workers?
  - gold: It uses the $WEB_CONCURRENCY environment variable if set, otherwise 1. The option is not valid together with --reload.
  - system [answered]: The number of worker processes Uvicorn starts without the `--workers` flag is not specified in the provided passages. While passages [1] and [3] mention starting with `--workers 4`, they do not state the default number of workers when `--workers` is omitted. Therefore, the default value cannot be de
  - cited: [(1, 'fastapi/deployment/server-workers.md'), (3, 'uvicorn/deployment/index.md')] · flags: ['uncited_claim: The number of worker processes Uvicorn starts without the `--workers` flag is no', 'uncited_claim: Therefore, the default value cannot be determined from the given information.'] · top retrieved: ['fastapi/deployment/server-workers.md', 'uvicorn/deployment/index.md', 'uvicorn/deployment/index.md']
- **q004** (lookup, heldout): Which IPs does Uvicorn trust for proxy headers by default, and how do I trust everything?
  - gold: By default it trusts the $FORWARDED_ALLOW_IPS environment variable if set, otherwise 127.0.0.1. The literal '*' means trust everything.
  - system [answered]: By default, Uvicorn trusts no IPs for proxy headers, as it requires explicit configuration to trust any IP addresses or networks [3]. To trust everything, set the `--forwarded-allow-ips="*"` option, which instructs Uvicorn to accept all incoming IPs, but only do so when you know the proxies have cor
  - cited: [(1, 'fastapi/advanced/behind-a-proxy.md'), (2, 'uvicorn/deployment/index.md'), (3, 'uvicorn/deployment/index.md')] · flags: [] · top retrieved: ['fastapi/advanced/behind-a-proxy.md', 'uvicorn/deployment/index.md', 'uvicorn/deployment/index.md']
- **q005** (lookup, dev): What is the default maximum WebSocket message size in Uvicorn?
  - gold: 16777216 bytes (16 MB), set with --ws-max-size.
  - system [insufficient]: The passages do not specify the default maximum WebSocket message size in Uvicorn. While [1] mentions a default `ws max_size` of 16MB, it refers to the server's default for the WebSocket maximum size, and does not confirm whether this is the message size or a different configuration. The term "max_s
  - cited: [(1, 'uvicorn/release-notes.md'), (4, 'uvicorn/release-notes.md')] · flags: ['model_reported_insufficient'] · top retrieved: ['uvicorn/release-notes.md', 'uvicorn/release-notes.md', 'uvicorn/release-notes.md']

## recursive/sparse/norerank (20260909-190346_recursive_sparse_norerank)
### Wrong or partial answers (judge ≤3): 2
- **q016** (lookup, dev): My Starlette lifespan handler doesn't run in tests with TestClient. What am I missing?
  - gold: The TestClient must be used as a context manager (with TestClient(app) as client) for the lifespan handler to run; it is not triggered on instantiation.
  - system [answered]: You are missing the use of the `TestClient` as a context manager, which is required to trigger the lifespan handler. The `TestClient` will not run the lifespan when instantiated directly; it must be used with a `with` statement to ensure the startup and shutdown events are called [2][4]. If you're u
  - cited: [(2, 'starlette/lifespan.md'), (4, 'starlette/testclient.md'), (5, 'fastapi/advanced/async-tests.md')] · flags: ['uncited_claim: You are missing the use of the `TestClient` as a context manager, which is requi'] · top retrieved: ['fastapi/advanced/testing-events.md', 'starlette/lifespan.md', 'starlette/lifespan.md']
- **q028** (lookup, dev): Where do I put the status_code parameter in FastAPI: on the decorator or on the function?
  - gold: On the decorator method (@app.get(..., status_code=...)), not on the path operation function.
  - system [answered]: The `status_code` parameter can be placed on the decorator (e.g., `@app.get(status_code=200)`) or on the function using a `Response` parameter, where the status code is set temporarily in the response object [2][3][5]. The decorator-based `status_code` is a parameter of the HTTP method decorator (li
  - cited: [(2, 'fastapi/tutorial/response-status-code.md'), (3, 'fastapi/advanced/custom-response.md'), (5, 'fastapi/advanced/response-change-status-code.md')] · flags: ['unsupported_citation [3]: The `status_code` parameter can be placed on the decorator (e.g., `@app.get(stat'] · top retrieved: ['fastapi/tutorial/first-steps.md', 'fastapi/tutorial/response-status-code.md', 'fastapi/advanced/custom-response.md']

### Answered a question the corpus cannot answer (should have abstained): 0

### Abstained on an answerable question: 3
- **q019** (lookup, heldout): What is the signature of Starlette's BackgroundTasks class and what is it for?
  - gold: BackgroundTasks(tasks=[]); it is used to add multiple background tasks to a response.
  - system [insufficient]: The passages do not provide the signature (i.e., the exact method list or parameter structure) of Starlette's `BackgroundTasks` class. They describe its usage in FastAPI, such as being used as a path operation function parameter and being automatically created and passed by FastAPI [1], and mention 
  - cited: [(1, 'fastapi/tutorial/background-tasks.md')] · flags: ['model_reported_insufficient'] · top retrieved: ['fastapi/tutorial/background-tasks.md', 'fastapi/advanced/advanced-dependencies.md', 'fastapi/async.md']
- **q026** (lookup, dev): How do I restrict a FastAPI path parameter to a fixed set of values?
  - gold: Create an Enum subclass that inherits from both str and Enum, and use it as the parameter's type; inheriting from str lets the docs render the values as strings.
  - system [insufficient]: 
  - cited: [] · flags: ['model_reported_insufficient'] · top retrieved: ['fastapi/tutorial/response-model.md', 'fastapi/tutorial/testing.md', 'fastapi/tutorial/dependencies/dependencies-in-path-operation-decorators.md']
- **q054** (multi_hop, dev): FastAPI's BackgroundTasks class comes from which package, and what is its constructor signature there?
  - gold: It comes directly from starlette.background; the Starlette signature is BackgroundTasks(tasks=[]).
  - system [insufficient]: The passages indicate that FastAPI's `BackgroundTasks` class comes from `starlette.background` as it is derived from `starlette.background.BackgroundTasks` [1]. However, the constructor signature of the `BackgroundTasks` class is not provided in any of the passages.
  - cited: [(1, 'fastapi/tutorial/background-tasks.md')] · flags: ['model_reported_insufficient'] · top retrieved: ['fastapi/tutorial/background-tasks.md', 'fastapi/advanced/advanced-dependencies.md', 'fastapi/reference/background.md']

### Citations judged NOT_SUPPORTED: 12
- **q004** (lookup, heldout): Which IPs does Uvicorn trust for proxy headers by default, and how do I trust everything?
  - gold: By default it trusts the $FORWARDED_ALLOW_IPS environment variable if set, otherwise 127.0.0.1. The literal '*' means trust everything.
  - system [answered]: By default, Uvicorn trusts the IP address `127.0.0.1` for proxy headers [1]. To trust everything, set `--forwarded-allow-ips="*"` to instruct Uvicorn to trust all incoming IPs [3][4].
  - cited: [(1, 'uvicorn/settings.md'), (3, 'uvicorn/deployment/index.md'), (4, 'fastapi/advanced/behind-a-proxy.md')] · flags: ['unsupported_citation [3]: To trust everything, set `--forwarded-allow-ips="*"` to instruct Uvicorn to trus'] · top retrieved: ['uvicorn/settings.md', 'fastapi/deployment/https.md', 'uvicorn/deployment/index.md']
- **q006** (lookup, heldout): What does Uvicorn's --ws-max-queue setting control and which protocol implementation supports it?
  - gold: It sets the maximum length of the WebSocket incoming message queue (default 32) and is only available with the websockets protocol implementation.
  - system [answered]: Uvicorn's `--ws-max-queue` setting controls the maximum length of the WebSocket incoming message queue. It is supported only with the `websockets` protocol implementation [1][2].
  - cited: [(1, 'uvicorn/settings.md'), (2, 'uvicorn/release-notes.md')] · flags: ["uncited_claim: Uvicorn's `--ws-max-queue` setting controls the maximum length of the WebSocket ", 'unsupported_citation [2]: It is supported only with the `websockets` protocol implementation.'] · top retrieved: ['uvicorn/settings.md', 'uvicorn/release-notes.md', 'uvicorn/concepts/websockets.md']
- **q008** (lookup, dev): Is the uvicorn.workers Gunicorn worker class still supported?
  - gold: No. The uvicorn.workers module is deprecated and will be removed; use the separate uvicorn-worker package instead.
  - system [answered]: No, the `uvicorn.workers` Gunicorn worker class is deprecated and will be removed in a future release. Users are advised to use the `uvicorn-worker` package instead [1][2][3].
  - cited: [(1, 'uvicorn/deployment/index.md'), (2, 'uvicorn/index.md'), (3, 'uvicorn/deployment/index.md')] · flags: ['uncited_claim: No, the `uvicorn.workers` Gunicorn worker class is deprecated and will be remove', 'unsupported_citation [3]: Users are advised to use the `uvicorn-worker` package instead.'] · top retrieved: ['uvicorn/deployment/index.md', 'uvicorn/index.md', 'uvicorn/deployment/index.md']
- **q010** (lookup, dev): What does --timeout-graceful-shutdown do in Uvicorn?
  - gold: It is the maximum number of seconds to wait for a graceful shutdown; after that the server starts terminating requests.
  - system [answered]: The `--timeout-graceful-shutdown` parameter sets the maximum number of seconds to wait for graceful shutdown. After this timeout, the server will start terminating requests. This ensures that responses and tasks complete within the configured timeout during shutdown [1][2][3].
  - cited: [(1, 'uvicorn/settings.md'), (2, 'uvicorn/release-notes.md'), (3, 'uvicorn/server-behavior.md')] · flags: ['uncited_claim: The `--timeout-graceful-shutdown` parameter sets the maximum number of seconds t', 'uncited_claim: After this timeout, the server will start terminating requests.', 'unsupported_citation [2]: This ensures that responses and tasks complete within the configured timeout dur'] · top retrieved: ['uvicorn/settings.md', 'uvicorn/release-notes.md', 'uvicorn/server-behavior.md']

### Ambiguity not surfaced: 4
- **q070** (ambiguous, dev): How do I enable HTTPS?
  - gold: Ambiguous: Uvicorn can terminate TLS itself with --ssl-keyfile/--ssl-certfile, the FastAPI deployment docs recommend a TLS termination proxy, and Starlette offers HTTPSRedirectMiddleware to force https; the answer should
  - system [insufficient]: The provided passages do not explain how to enable HTTPS in a FastAPI application. While [2] states that HTTPS is critical and [1] includes an HTTP 403 response with a problem detail, neither passage details the configuration or implementation steps for enabling HTTPS. The context mentions HTTPS in 
  - cited: [(1, 'rfc/rfc9457-problem-details.txt'), (2, 'fastapi/deployment/https.md')] · flags: ['model_reported_insufficient'] · top retrieved: ['rfc/rfc9457-problem-details.txt', 'fastapi/deployment/https.md', 'fastapi/deployment/server-workers.md']
- **q072** (ambiguous, dev): What does Upgrade mean?
  - gold: Ambiguous: 'Upgrade' is the HTTP header used to switch protocols (used by the WebSocket handshake) and also the 426 Upgrade Required status code in RFC 9110; the answer should mention both.
  - system [insufficient]: The provided context passages do not define or mention what "Upgrade" means. Therefore, the term cannot be interpreted from the given information.
  - cited: [] · flags: ['model_reported_insufficient'] · top retrieved: ['fastapi/deployment/index.md', 'fastapi/tutorial/bigger-applications.md', 'rfc/rfc9110-http-semantics.pdf']
- **q073** (ambiguous, heldout): How long is keep-alive?
  - gold: Ambiguous: Uvicorn's --timeout-keep-alive defaults to 5 seconds, while in HTTP/1.1 (RFC 9112) 'keep-alive' is a connection option for HTTP/1.0 persistence with no fixed duration; the answer should separate the two.
  - system [answered]: The keep-alive timeout is 5 seconds by default [1][4]. This timeout applies to connections that are kept alive, and if no new data is received within this period, the connection will be closed [1][4].
  - cited: [(1, 'uvicorn/settings.md'), (4, 'uvicorn/server-behavior.md')] · flags: [] · top retrieved: ['uvicorn/settings.md', 'rfc/rfc9112-http11.txt', 'rfc/rfc9112-http11.txt']
- **q074** (ambiguous, dev): Which middleware is included by default?
  - gold: Depends on the framework layer: Starlette (and therefore FastAPI) includes ServerErrorMiddleware and ExceptionMiddleware by default; nothing else (e.g. CORS, GZip, sessions) is added unless configured. A good answer stat
  - system [answered]: The Starlette application automatically includes two pieces of middleware by default: the `HTTPSRedirectMiddleware` and the `TrustedHostMiddleware` [5]. This is explicitly stated in the provided context [5].
  - cited: [(5, 'starlette/middleware.md')] · flags: [] · top retrieved: ['starlette/middleware.md', 'uvicorn/settings.md', 'starlette/middleware.md']

### Gold evidence not retrieved (retrieval miss): 10
- **q002** (lookup, dev): What happens when Uvicorn's --limit-concurrency limit is exceeded?
  - gold: Excess requests receive an immediate HTTP 503 response; they are not queued.
  - system [answered]: When Uvicorn's --limit-concurrency limit is exceeded, the excess requests receive a 503 error essentially immediately and are not held in the backlog or processed later [2]. This behavior is distinct from --backlog, which governs TCP connection queuing at the OS level and does not interact with conc
  - cited: [(1, 'uvicorn/server-behavior.md'), (2, 'uvicorn/server-behavior.md'), (4, 'uvicorn/server-behavior.md')] · flags: [] · top retrieved: ['uvicorn/server-behavior.md', 'uvicorn/server-behavior.md', 'uvicorn/deployment/index.md']
- **q003** (lookup, dev): How many worker processes does Uvicorn start if I don't pass --workers?
  - gold: It uses the $WEB_CONCURRENCY environment variable if set, otherwise 1. The option is not valid together with --reload.
  - system [answered]: If the `--workers` option is not passed, Uvicorn starts a single worker process by default. This is implied by the context that Uvicorn's default behavior without `--workers` is one process, as the `--workers` option is used to specify the number of worker processes, and the absence of such a specif
  - cited: [(5, 'uvicorn/deployment/index.md')] · flags: ['uncited_claim: If the `--workers` option is not passed, Uvicorn starts a single worker process '] · top retrieved: ['fastapi/deployment/server-workers.md', 'uvicorn/deployment/index.md', 'uvicorn/index.md']
- **q007** (lookup, dev): Why would I choose the httptools HTTP implementation in Uvicorn, and when can't I use it?
  - gold: httptools gives greater performance but is not compatible with PyPy.
  - system [answered]: You would choose the httptools HTTP implementation in Uvicorn for maximum performance, as it provides greater performance than h11 [1][2]. However, you can't use httptools when running under PyPy, as it is not compatible with PyPy [2]. Additionally, httptools requires the `uvicorn[standard]` extras 
  - cited: [(1, 'uvicorn/concepts/http-protocols.md'), (2, 'uvicorn/concepts/http-protocols.md')] · flags: [] · top retrieved: ['uvicorn/concepts/http-protocols.md', 'uvicorn/concepts/http-protocols.md', 'fastapi/deployment/server-workers.md']
- **q019** (lookup, heldout): What is the signature of Starlette's BackgroundTasks class and what is it for?
  - gold: BackgroundTasks(tasks=[]); it is used to add multiple background tasks to a response.
  - system [insufficient]: The passages do not provide the signature (i.e., the exact method list or parameter structure) of Starlette's `BackgroundTasks` class. They describe its usage in FastAPI, such as being used as a path operation function parameter and being automatically created and passed by FastAPI [1], and mention 
  - cited: [(1, 'fastapi/tutorial/background-tasks.md')] · flags: ['model_reported_insufficient'] · top retrieved: ['fastapi/tutorial/background-tasks.md', 'fastapi/advanced/advanced-dependencies.md', 'fastapi/async.md']

## fixed/hybrid/rerank (20260909-192000_fixed_hybrid_rerank)
### Wrong or partial answers (judge ≤3): 6
- **q004** (lookup, heldout): Which IPs does Uvicorn trust for proxy headers by default, and how do I trust everything?
  - gold: By default it trusts the $FORWARDED_ALLOW_IPS environment variable if set, otherwise 127.0.0.1. The literal '*' means trust everything.
  - system [answered]: By default, Uvicorn trusts no IPs for proxy headers, as it does not trust any client addresses unless explicitly configured [1][2][4]. To trust everything, you can set `--forwarded-allow-ips="*"` to instruct Uvicorn to trust all incoming IPs, but only if you know the proxies remove or properly handl
  - cited: [(1, 'uvicorn/deployment/index.md'), (2, 'fastapi/deployment/https.md'), (3, 'uvicorn/deployment/index.md'), (4, 'fastapi/advanced/behind-a-proxy.md')] · flags: [] · top retrieved: ['uvicorn/deployment/index.md', 'fastapi/deployment/https.md', 'uvicorn/deployment/index.md']
- **q007** (lookup, dev): Why would I choose the httptools HTTP implementation in Uvicorn, and when can't I use it?
  - gold: httptools gives greater performance but is not compatible with PyPy.
  - system [answered]: You would choose the httptools HTTP implementation for better performance compared to h11, as it uses a Python binding for the Node.js HTTP parser and offers greater performance [1][4]. However, you can't use httptools on platforms where it is not available, such as PyPy, since h11 is the only imple
  - cited: [(1, 'uvicorn/concepts/http-protocols.md'), (3, 'uvicorn/concepts/event-loop.md'), (4, 'uvicorn/installation.md')] · flags: ['unsupported_citation [4]: You would choose the httptools HTTP implementation for better performance compar', 'unsupported_citation [3]: Additionally, httptools is not available on Windows when using the `uvloop` even'] · top retrieved: ['uvicorn/concepts/http-protocols.md', 'uvicorn/concepts/websockets.md', 'uvicorn/concepts/event-loop.md']
- **q008** (lookup, dev): Is the uvicorn.workers Gunicorn worker class still supported?
  - gold: No. The uvicorn.workers module is deprecated and will be removed; use the separate uvicorn-worker package instead.
  - system [answered]: The `uvicorn.workers` Gunicorn worker class is deprecated and will be removed in a future release. Users are advised to use the `uvicorn-worker` package instead [2][5]. However, it is still functionally supported in current deployments as a transitional option [1][3].
  - cited: [(1, 'uvicorn/deployment/index.md'), (2, 'uvicorn/deployment/index.md'), (3, 'uvicorn/index.md'), (5, 'uvicorn/index.md')] · flags: ['uncited_claim: The `uvicorn.workers` Gunicorn worker class is deprecated and will be removed in', 'unsupported_citation [1]: However, it is still functionally supported in current deployments as a transiti', 'unsupported_citation [3]: However, it is still functionally supported in current deployments as a transiti'] · top retrieved: ['uvicorn/deployment/index.md', 'uvicorn/deployment/index.md', 'uvicorn/index.md']
- **q013** (lookup, dev): When does Starlette's GZipMiddleware compress a response?
  - gold: For any request whose Accept-Encoding header includes "gzip"; it handles both standard and streaming responses.
  - system [answered]: Starlette's GZipMiddleware compresses a response when the request includes `"gzip"` in the `Accept-Encoding` header. It also compresses streaming responses, but only if the response body is larger than the `minimum_size` threshold (default 500 bytes), and it skips compression for partial responses [
  - cited: [(1, 'starlette/middleware.md'), (2, 'starlette/release-notes.md'), (3, 'starlette/middleware.md'), (5, 'fastapi/advanced/middleware.md')] · flags: ['uncited_claim: Starlette\'s GZipMiddleware compresses a response when the request includes `"gzi'] · top retrieved: ['starlette/middleware.md', 'starlette/release-notes.md', 'starlette/middleware.md']

### Answered a question the corpus cannot answer (should have abstained): 0

### Abstained on an answerable question: 4
- **q026** (lookup, dev): How do I restrict a FastAPI path parameter to a fixed set of values?
  - gold: Create an Enum subclass that inherits from both str and Enum, and use it as the parameter's type; inheriting from str lets the docs render the values as strings.
  - system [insufficient]: 
  - cited: [] · flags: ['model_reported_insufficient'] · top retrieved: ['fastapi/tutorial/query-params.md', 'fastapi/advanced/path-operation-advanced-configuration.md', 'fastapi/tutorial/response-model.md']
- **q052** (multi_hop, dev): Uvicorn's --limit-concurrency rejects excess requests with a 503. What does a 503 mean per RFC 9110 and which header can tell clients when to retry?
  - gold: Uvicorn returns HTTP 503 immediately for requests over the concurrency limit. RFC 9110 defines 503 Service Unavailable as the server being temporarily unable to handle the request due to overload or maintenance, and the 
  - system [insufficient]: The provided passages do not specify what a 503 means per RFC 9110 nor which header informs clients when to retry. The passages describe Uvicorn's behavior with `--limit-concurrency` and 503 responses but do not include information on RFC 9110 definitions or retry headers.
  - cited: [] · flags: ['model_reported_insufficient'] · top retrieved: ['uvicorn/server-behavior.md', 'uvicorn/server-behavior.md', 'uvicorn/server-behavior.md']
- **q054** (multi_hop, dev): FastAPI's BackgroundTasks class comes from which package, and what is its constructor signature there?
  - gold: It comes directly from starlette.background; the Starlette signature is BackgroundTasks(tasks=[]).
  - system [insufficient]: The passages confirm that FastAPI's `BackgroundTasks` class comes from `starlette.background` as it is imported directly from `starlette.background` and is part of Starlette's background task functionality [1][2]. However, the constructor signature of `BackgroundTasks` is not specified in any of the
  - cited: [(1, 'fastapi/tutorial/background-tasks.md'), (2, 'fastapi/tutorial/background-tasks.md')] · flags: ['model_reported_insufficient'] · top retrieved: ['fastapi/tutorial/background-tasks.md', 'fastapi/tutorial/background-tasks.md', 'fastapi/reference/background.md']
- **q056** (multi_hop, heldout): If a WebSocket client sends a message bigger than Uvicorn's default --ws-max-size, which RFC 6455 close code describes that situation?
  - gold: Uvicorn's default limit is 16777216 bytes (16 MB); RFC 6455 defines close code 1009 for an endpoint terminating the connection because it received a message too big to process.
  - system [insufficient]: The passages do not specify which RFC 6455 close code corresponds to a message larger than Uvicorn's default --ws-max-size. While [2] discusses limits on message size and [3] mentions the --ws-max-size setting, neither identifies the specific RFC 6455 close code for such a scenario.
  - cited: [(2, 'rfc/rfc6455-websocket.html'), (3, 'uvicorn/settings.md')] · flags: ['model_reported_insufficient'] · top retrieved: ['uvicorn/concepts/websockets.md', 'rfc/rfc6455-websocket.html', 'uvicorn/settings.md']

### Citations judged NOT_SUPPORTED: 13
- **q002** (lookup, dev): What happens when Uvicorn's --limit-concurrency limit is exceeded?
  - gold: Excess requests receive an immediate HTTP 503 response; they are not queued.
  - system [answered]: When Uvicorn's `--limit-concurrency` limit is exceeded, the server responds immediately with a "503 Service Unavailable" error; the request is not queued and does not wait for a slot to free up [1][3]. This is because `--limit-concurrency` is an application-level gate that checks after a request's h
  - cited: [(1, 'uvicorn/server-behavior.md'), (3, 'uvicorn/server-behavior.md')] · flags: ["unsupported_citation [3]: When Uvicorn's `--limit-concurrency` limit is exceeded, the server responds imme"] · top retrieved: ['uvicorn/server-behavior.md', 'uvicorn/server-behavior.md', 'uvicorn/server-behavior.md']
- **q007** (lookup, dev): Why would I choose the httptools HTTP implementation in Uvicorn, and when can't I use it?
  - gold: httptools gives greater performance but is not compatible with PyPy.
  - system [answered]: You would choose the httptools HTTP implementation for better performance compared to h11, as it uses a Python binding for the Node.js HTTP parser and offers greater performance [1][4]. However, you can't use httptools on platforms where it is not available, such as PyPy, since h11 is the only imple
  - cited: [(1, 'uvicorn/concepts/http-protocols.md'), (3, 'uvicorn/concepts/event-loop.md'), (4, 'uvicorn/installation.md')] · flags: ['unsupported_citation [4]: You would choose the httptools HTTP implementation for better performance compar', 'unsupported_citation [3]: Additionally, httptools is not available on Windows when using the `uvloop` even'] · top retrieved: ['uvicorn/concepts/http-protocols.md', 'uvicorn/concepts/websockets.md', 'uvicorn/concepts/event-loop.md']
- **q008** (lookup, dev): Is the uvicorn.workers Gunicorn worker class still supported?
  - gold: No. The uvicorn.workers module is deprecated and will be removed; use the separate uvicorn-worker package instead.
  - system [answered]: The `uvicorn.workers` Gunicorn worker class is deprecated and will be removed in a future release. Users are advised to use the `uvicorn-worker` package instead [2][5]. However, it is still functionally supported in current deployments as a transitional option [1][3].
  - cited: [(1, 'uvicorn/deployment/index.md'), (2, 'uvicorn/deployment/index.md'), (3, 'uvicorn/index.md'), (5, 'uvicorn/index.md')] · flags: ['uncited_claim: The `uvicorn.workers` Gunicorn worker class is deprecated and will be removed in', 'unsupported_citation [1]: However, it is still functionally supported in current deployments as a transiti', 'unsupported_citation [3]: However, it is still functionally supported in current deployments as a transiti'] · top retrieved: ['uvicorn/deployment/index.md', 'uvicorn/deployment/index.md', 'uvicorn/index.md']
- **q023** (lookup, dev): Should I return or raise HTTPException in FastAPI?
  - gold: Raise it. HTTPException is a normal Python exception with extra API data, so you raise rather than return it.
  - system [answered]: You should raise, not return, an HTTPException in FastAPI. This is because HTTPException is a Python exception designed to terminate the request and send an error response to the client [1][5]. Returning it would not trigger the proper error handling or response, as exceptions in FastAPI are handled
  - cited: [(1, 'fastapi/tutorial/handling-errors.md'), (2, 'fastapi/reference/exceptions.md'), (3, 'fastapi/tutorial/dependencies/dependencies-with-yield.md'), (5, 'fastapi/tutorial/handling-errors.md')] · flags: ['uncited_claim: You should raise, not return, an HTTPException in FastAPI.', 'unsupported_citation [2]: Returning it would not trigger the proper error handling or response, as excepti'] · top retrieved: ['fastapi/tutorial/handling-errors.md', 'fastapi/reference/exceptions.md', 'fastapi/tutorial/dependencies/dependencies-with-yield.md']

### Ambiguity not surfaced: 2
- **q069** (ambiguous, heldout): How do I set the maximum size?
  - gold: Ambiguous: could be Uvicorn's WebSocket --ws-max-size, a FastAPI Query max_length, or HTTP 413 Content Too Large; the answer should name the interpretations.
  - system [insufficient]: I could not find enough information in the indexed documentation to answer this reliably.
  - cited: [] · flags: ['low_retrieval_confidence'] · top retrieved: ['starlette/requests.md', 'starlette/middleware.md', 'starlette/requests.md']
- **q070** (ambiguous, dev): How do I enable HTTPS?
  - gold: Ambiguous: Uvicorn can terminate TLS itself with --ssl-keyfile/--ssl-certfile, the FastAPI deployment docs recommend a TLS termination proxy, and Starlette offers HTTPSRedirectMiddleware to force https; the answer should
  - system [answered]: To enable HTTPS, the server must have certificates acquired from a third party, as certificates are not generated but obtained [1]. For developers, tools like Traefik can easily handle HTTPS configuration with Docker, Kubernetes, or cloud providers [2]. The setup often involves configuring a reverse
  - cited: [(1, 'fastapi/deployment/https.md'), (2, 'fastapi/deployment/docker.md'), (3, 'fastapi/deployment/https.md')] · flags: [] · top retrieved: ['fastapi/deployment/https.md', 'fastapi/deployment/docker.md', 'fastapi/deployment/https.md']

### Gold evidence not retrieved (retrieval miss): 15
- **q003** (lookup, dev): How many worker processes does Uvicorn start if I don't pass --workers?
  - gold: It uses the $WEB_CONCURRENCY environment variable if set, otherwise 1. The option is not valid together with --reload.
  - system [answered]: Uvicorn starts one worker process if the `--workers` option is not passed. This is the default behavior, as the `--workers` option is used to specify the number of worker processes, and without it, only a single process is launched [4].
  - cited: [(4, 'uvicorn/deployment/index.md')] · flags: ['uncited_claim: Uvicorn starts one worker process if the `--workers` option is not passed.'] · top retrieved: ['uvicorn/deployment/index.md', 'fastapi/deployment/server-workers.md', 'fastapi/deployment/server-workers.md']
- **q004** (lookup, heldout): Which IPs does Uvicorn trust for proxy headers by default, and how do I trust everything?
  - gold: By default it trusts the $FORWARDED_ALLOW_IPS environment variable if set, otherwise 127.0.0.1. The literal '*' means trust everything.
  - system [answered]: By default, Uvicorn trusts no IPs for proxy headers, as it does not trust any client addresses unless explicitly configured [1][2][4]. To trust everything, you can set `--forwarded-allow-ips="*"` to instruct Uvicorn to trust all incoming IPs, but only if you know the proxies remove or properly handl
  - cited: [(1, 'uvicorn/deployment/index.md'), (2, 'fastapi/deployment/https.md'), (3, 'uvicorn/deployment/index.md'), (4, 'fastapi/advanced/behind-a-proxy.md')] · flags: [] · top retrieved: ['uvicorn/deployment/index.md', 'fastapi/deployment/https.md', 'uvicorn/deployment/index.md']
- **q007** (lookup, dev): Why would I choose the httptools HTTP implementation in Uvicorn, and when can't I use it?
  - gold: httptools gives greater performance but is not compatible with PyPy.
  - system [answered]: You would choose the httptools HTTP implementation for better performance compared to h11, as it uses a Python binding for the Node.js HTTP parser and offers greater performance [1][4]. However, you can't use httptools on platforms where it is not available, such as PyPy, since h11 is the only imple
  - cited: [(1, 'uvicorn/concepts/http-protocols.md'), (3, 'uvicorn/concepts/event-loop.md'), (4, 'uvicorn/installation.md')] · flags: ['unsupported_citation [4]: You would choose the httptools HTTP implementation for better performance compar', 'unsupported_citation [3]: Additionally, httptools is not available on Windows when using the `uvloop` even'] · top retrieved: ['uvicorn/concepts/http-protocols.md', 'uvicorn/concepts/websockets.md', 'uvicorn/concepts/event-loop.md']
- **q013** (lookup, dev): When does Starlette's GZipMiddleware compress a response?
  - gold: For any request whose Accept-Encoding header includes "gzip"; it handles both standard and streaming responses.
  - system [answered]: Starlette's GZipMiddleware compresses a response when the request includes `"gzip"` in the `Accept-Encoding` header. It also compresses streaming responses, but only if the response body is larger than the `minimum_size` threshold (default 500 bytes), and it skips compression for partial responses [
  - cited: [(1, 'starlette/middleware.md'), (2, 'starlette/release-notes.md'), (3, 'starlette/middleware.md'), (5, 'fastapi/advanced/middleware.md')] · flags: ['uncited_claim: Starlette\'s GZipMiddleware compresses a response when the request includes `"gzi'] · top retrieved: ['starlette/middleware.md', 'starlette/release-notes.md', 'starlette/middleware.md']

## semantic/hybrid/rerank (20260909-194022_semantic_hybrid_rerank)
### Wrong or partial answers (judge ≤3): 7
- **q006** (lookup, heldout): What does Uvicorn's --ws-max-queue setting control and which protocol implementation supports it?
  - gold: It sets the maximum length of the WebSocket incoming message queue (default 32) and is only available with the websockets protocol implementation.
  - system [answered]: Uvicorn's `--ws-max-queue` setting controls the maximum number of WebSockets messages that can be queued for processing [5]. This setting is supported by the WebSockets protocol implementation, specifically the `websockets-sansio` protocol [1].
  - cited: [(1, 'uvicorn/concepts/websockets.md'), (5, 'uvicorn/release-notes.md')] · flags: [] · top retrieved: ['uvicorn/concepts/websockets.md', 'uvicorn/concepts/lifespan.md', 'uvicorn/concepts/http-protocols.md']
- **q007** (lookup, dev): Why would I choose the httptools HTTP implementation in Uvicorn, and when can't I use it?
  - gold: httptools gives greater performance but is not compatible with PyPy.
  - system [answered]: You would choose the httptools HTTP implementation in Uvicorn for greater performance compared to h11, as it is a Python binding for the Node.js HTTP parser and provides faster parsing of HTTP/1.1 requests [1][3]. However, you can't use httptools on PyPy, as it is not compatible with that Python imp
  - cited: [(1, 'uvicorn/concepts/http-protocols.md'), (3, 'uvicorn/installation.md')] · flags: ['unsupported_citation [3]: Additionally, httptools is not available on platforms where it is not installed,'] · top retrieved: ['uvicorn/concepts/http-protocols.md', 'uvicorn/concepts/event-loop.md', 'uvicorn/installation.md']
- **q014** (lookup, dev): Which two middleware does every Starlette application include by default?
  - gold: ServerErrorMiddleware (always the outermost layer; custom 500 page or traceback in debug) and ExceptionMiddleware (exception handlers).
  - system [answered]: The two middleware that every Starlette application includes by default are not explicitly named in the provided passages. While passage [1] states that "Every Starlette application automatically includes two pieces of middleware by default," it does not specify which ones. Therefore, the specific m
  - cited: [(1, 'starlette/middleware.md')] · flags: ['uncited_claim: The two middleware that every Starlette application includes by default are not ', 'uncited_claim: Therefore, the specific middleware classes are not identified in the text.'] · top retrieved: ['starlette/middleware.md', 'starlette/middleware.md', 'starlette/middleware.md']
- **q017** (lookup, heldout): How do I get the client's IP address and port from a Starlette Request?
  - gold: request.client.host gives the hostname or IP and request.client.port the port; request.client may be None.
  - system [answered]: You can get the client's IP address from the `Request` object using `request.client.host` or `request.client.ip`, and the port using `request.client.port` if available. These attributes are derived from the underlying ASGI scope and are accessible via the `Request` object in Starlette [2]. Note that
  - cited: [(2, 'starlette/requests.md')] · flags: ["uncited_claim: You can get the client's IP address from the `Request` object using `request.cli", 'unsupported_citation [2]: Note that `request.client` may not always be directly exposed; in some cases, th'] · top retrieved: ['fastapi/advanced/using-request-directly.md', 'starlette/requests.md', 'fastapi/tutorial/middleware.md']

### Answered a question the corpus cannot answer (should have abstained): 0

### Abstained on an answerable question: 3
- **q026** (lookup, dev): How do I restrict a FastAPI path parameter to a fixed set of values?
  - gold: Create an Enum subclass that inherits from both str and Enum, and use it as the parameter's type; inheriting from str lets the docs render the values as strings.
  - system [insufficient]: 
  - cited: [] · flags: ['model_reported_insufficient'] · top retrieved: ['fastapi/tutorial/query-params.md', 'fastapi/advanced/path-operation-advanced-configuration.md', 'fastapi/tutorial/body-multiple-params.md']
- **q052** (multi_hop, dev): Uvicorn's --limit-concurrency rejects excess requests with a 503. What does a 503 mean per RFC 9110 and which header can tell clients when to retry?
  - gold: Uvicorn returns HTTP 503 immediately for requests over the concurrency limit. RFC 9110 defines 503 Service Unavailable as the server being temporarily unable to handle the request due to overload or maintenance, and the 
  - system [insufficient]: The provided passages do not specify what a 503 error means per RFC 9110 nor which header informs clients when to retry. The passages discuss Uvicorn's behavior with `--limit-concurrency` and 503 responses but do not address RFC 9110 definitions or retry headers.
  - cited: [] · flags: ['model_reported_insufficient'] · top retrieved: ['uvicorn/settings.md', 'uvicorn/server-behavior.md', 'uvicorn/server-behavior.md']
- **q056** (multi_hop, heldout): If a WebSocket client sends a message bigger than Uvicorn's default --ws-max-size, which RFC 6455 close code describes that situation?
  - gold: Uvicorn's default limit is 16777216 bytes (16 MB); RFC 6455 defines close code 1009 for an endpoint terminating the connection because it received a message too big to process.
  - system [insufficient]: The passages do not specify which RFC 6455 close code applies when a WebSocket message exceeds the --ws-max-size limit. Therefore, the exact RFC 6455 close code cannot be determined from the provided context.
  - cited: [] · flags: ['model_reported_insufficient'] · top retrieved: ['uvicorn/settings.md', 'uvicorn/concepts/websockets.md', 'uvicorn/settings.md']

### Citations judged NOT_SUPPORTED: 13
- **q004** (lookup, heldout): Which IPs does Uvicorn trust for proxy headers by default, and how do I trust everything?
  - gold: By default it trusts the $FORWARDED_ALLOW_IPS environment variable if set, otherwise 127.0.0.1. The literal '*' means trust everything.
  - system [answered]: By default, Uvicorn trusts the IP address "127.0.0.1" for proxy headers, as this is the value used when the `$FORWARDED_ALLOW_IPS` environment variable is not set [5]. To trust everything, set the `--forwarded-allow-ips` CLI option to `"*"` to instruct Uvicorn to accept forwarded headers from any IP
  - cited: [(1, 'fastapi/advanced/behind-a-proxy.md'), (4, 'uvicorn/deployment/index.md'), (5, 'uvicorn/release-notes.md')] · flags: ['unsupported_citation [4]: To trust everything, set the `--forwarded-allow-ips` CLI option to `"*"` to inst'] · top retrieved: ['fastapi/advanced/behind-a-proxy.md', 'uvicorn/deployment/index.md', 'fastapi/deployment/https.md']
- **q007** (lookup, dev): Why would I choose the httptools HTTP implementation in Uvicorn, and when can't I use it?
  - gold: httptools gives greater performance but is not compatible with PyPy.
  - system [answered]: You would choose the httptools HTTP implementation in Uvicorn for greater performance compared to h11, as it is a Python binding for the Node.js HTTP parser and provides faster parsing of HTTP/1.1 requests [1][3]. However, you can't use httptools on PyPy, as it is not compatible with that Python imp
  - cited: [(1, 'uvicorn/concepts/http-protocols.md'), (3, 'uvicorn/installation.md')] · flags: ['unsupported_citation [3]: Additionally, httptools is not available on platforms where it is not installed,'] · top retrieved: ['uvicorn/concepts/http-protocols.md', 'uvicorn/concepts/event-loop.md', 'uvicorn/installation.md']
- **q008** (lookup, dev): Is the uvicorn.workers Gunicorn worker class still supported?
  - gold: No. The uvicorn.workers module is deprecated and will be removed; use the separate uvicorn-worker package instead.
  - system [answered]: No, the `uvicorn.workers` Gunicorn worker class is deprecated and will be removed in a future release. Users are advised to use the `uvicorn-worker` package instead [1][2][4].
  - cited: [(1, 'uvicorn/deployment/index.md'), (2, 'uvicorn/index.md'), (4, 'uvicorn/index.md')] · flags: ['uncited_claim: No, the `uvicorn.workers` Gunicorn worker class is deprecated and will be remove', 'unsupported_citation [2]: Users are advised to use the `uvicorn-worker` package instead.'] · top retrieved: ['uvicorn/deployment/index.md', 'uvicorn/index.md', 'uvicorn/deployment/index.md']
- **q009** (lookup, heldout): What is the default value of --reload-delay in Uvicorn?
  - gold: 0.25 seconds between reload checks.
  - system [answered]: The default value of `--reload-delay` in Uvicorn is 0.25 seconds. This is stated in the release notes for version 0.18.0, where the default for `reload_delay` was changed from `None` to `0.25` [1]. Additionally, the settings documentation confirms the default value of `0.25` for `--reload-delay` [2]
  - cited: [(1, 'uvicorn/release-notes.md'), (2, 'uvicorn/settings.md')] · flags: ['uncited_claim: The default value of `--reload-delay` in Uvicorn is 0.25 seconds.', 'unsupported_citation [1]: This is stated in the release notes for version 0.18.0, where the default for `r'] · top retrieved: ['uvicorn/release-notes.md', 'uvicorn/settings.md', 'uvicorn/installation.md']

### Ambiguity not surfaced: 4
- **q069** (ambiguous, heldout): How do I set the maximum size?
  - gold: Ambiguous: could be Uvicorn's WebSocket --ws-max-size, a FastAPI Query max_length, or HTTP 413 Content Too Large; the answer should name the interpretations.
  - system [insufficient]: I could not find enough information in the indexed documentation to answer this reliably.
  - cited: [] · flags: ['low_retrieval_confidence'] · top retrieved: ['starlette/routing.md', 'fastapi/tutorial/query-params-str-validations.md', 'starlette/middleware.md']
- **q070** (ambiguous, dev): How do I enable HTTPS?
  - gold: Ambiguous: Uvicorn can terminate TLS itself with --ssl-keyfile/--ssl-certfile, the FastAPI deployment docs recommend a TLS termination proxy, and Starlette offers HTTPSRedirectMiddleware to force https; the answer should
  - system [answered]: You enable HTTPS by acquiring a domain name, configuring an A record in DNS to point to your server's public IP address, and ensuring the server listens on port 443 for TLS connections during the TLS handshake [4][1]. The full setup may involve additional configuration depending on your deployment t
  - cited: [(1, 'fastapi/deployment/https.md'), (2, 'fastapi/deployment/https.md'), (4, 'fastapi/deployment/https.md'), (5, 'fastapi/deployment/https.md')] · flags: [] · top retrieved: ['fastapi/deployment/https.md', 'fastapi/deployment/https.md', 'rfc/rfc9110-http-semantics.pdf']
- **q073** (ambiguous, heldout): How long is keep-alive?
  - gold: Ambiguous: Uvicorn's --timeout-keep-alive defaults to 5 seconds, while in HTTP/1.1 (RFC 9112) 'keep-alive' is a connection option for HTTP/1.0 persistence with no fixed duration; the answer should separate the two.
  - system [answered]: The keep-alive timeout is 5 seconds by default [1][2]. This is the time after which a Keep-Alive connection will be closed if no new data is received.
  - cited: [(1, 'uvicorn/settings.md'), (2, 'uvicorn/server-behavior.md')] · flags: ['uncited_claim: This is the time after which a Keep-Alive connection will be closed if no new da'] · top retrieved: ['uvicorn/settings.md', 'uvicorn/server-behavior.md', 'fastapi/tutorial/server-sent-events.md']
- **q074** (ambiguous, dev): Which middleware is included by default?
  - gold: Depends on the framework layer: Starlette (and therefore FastAPI) includes ServerErrorMiddleware and ExceptionMiddleware by default; nothing else (e.g. CORS, GZip, sessions) is added unless configured. A good answer stat
  - system [answered]: The Starlette application automatically includes two pieces of middleware by default, as stated in passage [1]. The specific middleware classes are not named in the passage, but the default inclusion is confirmed [1].
  - cited: [(1, 'starlette/middleware.md')] · flags: [] · top retrieved: ['starlette/middleware.md', 'starlette/middleware.md', 'starlette/release-notes.md']

### Gold evidence not retrieved (retrieval miss): 13
- **q003** (lookup, dev): How many worker processes does Uvicorn start if I don't pass --workers?
  - gold: It uses the $WEB_CONCURRENCY environment variable if set, otherwise 1. The option is not valid together with --reload.
  - system [answered]: If the `--workers` option is not passed, Uvicorn starts a single worker process. This is because the default behavior of Uvicorn without the `--workers` argument is to run one process, as implied by the context that "running it once in one process" is the default setup [3][5].
  - cited: [(3, 'fastapi/deployment/server-workers.md'), (5, 'uvicorn/deployment/index.md')] · flags: ['uncited_claim: If the `--workers` option is not passed, Uvicorn starts a single worker process.'] · top retrieved: ['fastapi/deployment/server-workers.md', 'uvicorn/deployment/index.md', 'fastapi/deployment/server-workers.md']
- **q004** (lookup, heldout): Which IPs does Uvicorn trust for proxy headers by default, and how do I trust everything?
  - gold: By default it trusts the $FORWARDED_ALLOW_IPS environment variable if set, otherwise 127.0.0.1. The literal '*' means trust everything.
  - system [answered]: By default, Uvicorn trusts the IP address "127.0.0.1" for proxy headers, as this is the value used when the `$FORWARDED_ALLOW_IPS` environment variable is not set [5]. To trust everything, set the `--forwarded-allow-ips` CLI option to `"*"` to instruct Uvicorn to accept forwarded headers from any IP
  - cited: [(1, 'fastapi/advanced/behind-a-proxy.md'), (4, 'uvicorn/deployment/index.md'), (5, 'uvicorn/release-notes.md')] · flags: ['unsupported_citation [4]: To trust everything, set the `--forwarded-allow-ips` CLI option to `"*"` to inst'] · top retrieved: ['fastapi/advanced/behind-a-proxy.md', 'uvicorn/deployment/index.md', 'fastapi/deployment/https.md']
- **q006** (lookup, heldout): What does Uvicorn's --ws-max-queue setting control and which protocol implementation supports it?
  - gold: It sets the maximum length of the WebSocket incoming message queue (default 32) and is only available with the websockets protocol implementation.
  - system [answered]: Uvicorn's `--ws-max-queue` setting controls the maximum number of WebSockets messages that can be queued for processing [5]. This setting is supported by the WebSockets protocol implementation, specifically the `websockets-sansio` protocol [1].
  - cited: [(1, 'uvicorn/concepts/websockets.md'), (5, 'uvicorn/release-notes.md')] · flags: [] · top retrieved: ['uvicorn/concepts/websockets.md', 'uvicorn/concepts/lifespan.md', 'uvicorn/concepts/http-protocols.md']
- **q007** (lookup, dev): Why would I choose the httptools HTTP implementation in Uvicorn, and when can't I use it?
  - gold: httptools gives greater performance but is not compatible with PyPy.
  - system [answered]: You would choose the httptools HTTP implementation in Uvicorn for greater performance compared to h11, as it is a Python binding for the Node.js HTTP parser and provides faster parsing of HTTP/1.1 requests [1][3]. However, you can't use httptools on PyPy, as it is not compatible with that Python imp
  - cited: [(1, 'uvicorn/concepts/http-protocols.md'), (3, 'uvicorn/installation.md')] · flags: ['unsupported_citation [3]: Additionally, httptools is not available on platforms where it is not installed,'] · top retrieved: ['uvicorn/concepts/http-protocols.md', 'uvicorn/concepts/event-loop.md', 'uvicorn/installation.md']

