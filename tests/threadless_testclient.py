from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Any

import anyio
import httpx
from starlette.types import ASGIApp


async def _run_anyio_sync_inline(  # noqa: ANN001, ANN202
    func,
    *args,
    abandon_on_cancel: bool = False,
    cancellable: bool | None = None,
    limiter=None,
):
    del abandon_on_cancel, cancellable, limiter
    return func(*args)


async def _run_asyncio_to_thread_inline(func, /, *args, **kwargs):  # noqa: ANN001, ANN202
    return func(*args, **kwargs)


async def _run_in_threadpool_inline(func, *args, **kwargs):  # noqa: ANN001, ANN202
    return func(*args, **kwargs)


class _InlineAsyncFile:
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        self._file = open(*args, **kwargs)  # noqa: SIM115

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        del exc_type, exc, tb
        self._file.close()

    async def read(self, size: int = -1):
        return self._file.read(size)

    async def write(self, data):  # noqa: ANN001, ANN202
        return self._file.write(data)

    async def seek(self, offset: int, whence: int = 0):
        return self._file.seek(offset, whence)

    async def close(self) -> None:
        self._file.close()


async def _open_file_inline(*args, **kwargs) -> _InlineAsyncFile:  # noqa: ANN002, ANN003
    return _InlineAsyncFile(*args, **kwargs)


class ThreadlessTestClient:
    __test__ = False

    def __init__(
        self,
        app: ASGIApp,
        base_url: str = "http://testserver",
        raise_server_exceptions: bool = True,
        root_path: str = "",
        backend: str = "asyncio",
        backend_options: dict[str, Any] | None = None,
        cookies: httpx._types.CookieTypes | None = None,
        headers: dict[str, str] | None = None,
        follow_redirects: bool = True,
        client: tuple[str, int] = ("testclient", 50000),
    ) -> None:
        del backend, backend_options
        self.app = app
        self.base_url = base_url
        self.raise_server_exceptions = raise_server_exceptions
        self.root_path = root_path
        self.follow_redirects = follow_redirects
        self.client = client
        self.cookies = httpx.Cookies(cookies)
        self.headers = {"user-agent": "testclient"}
        if headers:
            self.headers.update(headers)

    def __enter__(self) -> ThreadlessTestClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        del exc_type, exc, tb

    def request(
        self,
        method: str,
        url: httpx._types.URLTypes,
        *,
        content: httpx._types.RequestContent | None = None,
        data: httpx._types.RequestData | None = None,
        files: httpx._types.RequestFiles | None = None,
        json: Any = None,
        params: httpx._types.QueryParamTypes | None = None,
        headers: httpx._types.HeaderTypes | None = None,
        cookies: httpx._types.CookieTypes | None = None,
        auth: httpx._types.AuthTypes | httpx._client.UseClientDefault = httpx.USE_CLIENT_DEFAULT,
        follow_redirects: bool | httpx._client.UseClientDefault = httpx.USE_CLIENT_DEFAULT,
        timeout: (
            httpx._types.TimeoutTypes | httpx._client.UseClientDefault
        ) = httpx.USE_CLIENT_DEFAULT,
        extensions: dict[str, Any] | None = None,
    ) -> httpx.Response:
        del timeout, extensions

        async def _send() -> httpx.Response:
            transport = httpx.ASGITransport(
                app=self.app,
                raise_app_exceptions=self.raise_server_exceptions,
                root_path=self.root_path,
                client=self.client,
            )
            resolved_follow_redirects = (
                self.follow_redirects
                if follow_redirects is httpx.USE_CLIENT_DEFAULT
                else bool(follow_redirects)
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self.base_url,
                headers=self.headers,
                cookies=self.cookies,
                follow_redirects=resolved_follow_redirects,
            ) as client:
                response = await client.request(
                    method,
                    url,
                    content=content,
                    data=data,
                    files=files,
                    json=json,
                    params=params,
                    headers=headers,
                    cookies=cookies,
                    auth=auth,
                )
                await response.aread()
                self.cookies.update(client.cookies)
                return response

        return asyncio.run(_send())

    def get(self, url: httpx._types.URLTypes, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: httpx._types.URLTypes, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)


def install_threadless_testclient() -> None:
    import fastapi.concurrency
    import fastapi.dependencies.utils
    import fastapi.routing
    import fastapi.testclient
    import starlette._exception_handler
    import starlette.background
    import starlette.concurrency
    import starlette.endpoints
    import starlette.middleware.errors
    import starlette.routing
    import starlette.testclient

    setattr(anyio, "open_file", _open_file_inline)
    setattr(anyio.to_thread, "run_sync", _run_anyio_sync_inline)
    setattr(asyncio, "to_thread", _run_asyncio_to_thread_inline)

    for module in (
        fastapi.concurrency,
        fastapi.dependencies.utils,
        fastapi.routing,
        starlette._exception_handler,
        starlette.background,
        starlette.concurrency,
        starlette.endpoints,
        starlette.middleware.errors,
        starlette.routing,
    ):
        setattr(module, "run_in_threadpool", _run_in_threadpool_inline)

    setattr(fastapi.testclient, "TestClient", ThreadlessTestClient)
    setattr(starlette.testclient, "TestClient", ThreadlessTestClient)


__all__ = ["ThreadlessTestClient", "install_threadless_testclient"]
