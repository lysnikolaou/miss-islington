import aiohttp
import asyncio
import os
import sys
import traceback
import cachetools

from aiohttp import web

from gidgethub import aiohttp as gh_aiohttp
from gidgethub import routing
from gidgethub import sansio


from . import backport_pr
from . import delete_branch
from . import status_change

router = routing.Router(backport_pr.router, delete_branch.router, status_change.router)

cache = cachetools.LRUCache(maxsize=500)

import sentry_sdk

sentry_sdk.init(os.environ.get("SENTRY_DSN"))


async def main(request):
    try:
        body = await request.read()

        secret = os.environ.get("GH_SECRET")
        event = sansio.Event.from_http(request.headers, body, secret=secret)
        print("GH delivery ID", event.delivery_id, file=sys.stderr)
        if event.event == "ping":
            return web.Response(status=200)
        oauth_token = os.environ.get("GH_AUTH")
        async with aiohttp.ClientSession() as session:
            gh = gh_aiohttp.GitHubAPI(
                session, "python/cpython", oauth_token=oauth_token, cache=cache
            )
            # Give GitHub some time to reach internal consistency.
            await asyncio.sleep(1)
            await router.dispatch(event, gh)
            try:
                print(
                    f"""\
GH requests remaining: {gh.rate_limit.remaining}/{gh.rate_limit.limit}, \
reset time: {gh.rate_limit.reset_datetime:%b-%d-%Y %H:%M:%S %Z}, \
oauth token length {len(oauth_token)}, \
last 4 digits {oauth_token[-4:]}, \
GH delivery ID {event.delivery_id} \
"""
                )
            except AttributeError:
                pass
        return web.Response(status=200)
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        return web.Response(status=500)


if __name__ == "__main__":  # pragma: no cover
    app = web.Application()
    app.router.add_post("/", main)
    port = os.environ.get("PORT")
    if port is not None:
        port = int(port)

    web.run_app(app, port=port)
