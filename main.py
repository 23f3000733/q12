import os
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# ---- Config -------------------------------------------------------------
EMAIL = os.getenv("USER_EMAIL", "23f3000733@ds.study.iitm.ac.in")  # <-- your logged-in address
ASSIGNED_ORIGIN = "https://app-vy6uoj.example.com"
EXAM_ORIGIN = os.getenv("EXAM_ORIGIN", "")  # the exam page's origin, e.g. https://exam.example.com

RATE_LIMIT = 14      # requests
WINDOW_SECONDS = 10  # per this many seconds

ALLOWED_ORIGINS = [o for o in (ASSIGNED_ORIGIN, EXAM_ORIGIN) if o]

app = FastAPI()


# ---- Middleware 3: per-client rate limiting (sliding window) -------------
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.hits = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        client_id = request.headers.get("X-Client-Id") or (
            request.client.host if request.client else "anonymous"
        )
        now = time.monotonic()
        q = self.hits[client_id]
        while q and now - q[0] >= WINDOW_SECONDS:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            retry = max(1, int(WINDOW_SECONDS - (now - q[0])) + 1)
            return JSONResponse(
                {"detail": "Too Many Requests"},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
        q.append(now)
        return await call_next(request)


# ---- Middleware 1: request context ---------------------------------------
class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# Order matters: the LAST one added is the OUTERMOST.
# CORS outermost -> handles preflight and decorates every response (incl. 429).
# Context next   -> 429 responses also carry X-Request-ID.
# Rate limit innermost.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # explicit list, no wildcard
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["X-Request-ID", "X-Client-Id", "Content-Type"],
    expose_headers=["X-Request-ID"],
)


@app.get("/ping")
async def ping(request: Request):
    return {"email": EMAIL, "request_id": request.state.request_id}
