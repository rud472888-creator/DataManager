import os
from collections.abc import Iterator
from threading import Thread
from time import sleep
from typing import Any

import pytest
import uvicorn

from app.api.server import create_app

playwright_sync = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def server_url(tmp_path_factory) -> Iterator[str]:
    root = tmp_path_factory.mktemp("console")
    os.environ["FDM_DATABASE_PATH"] = str(root / "fdm.sqlite3")
    os.environ["FDM_DATA_DIR"] = str(root / "data")
    config = uvicorn.Config(
        create_app(),
        host="127.0.0.1",
        port=8765,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        sleep(0.05)

    yield "http://127.0.0.1:8765"

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def page() -> Iterator[Any]:
    with playwright_sync.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        yield page
        browser.close()


def test_console_home_create_job_and_no_file_input(page: Any, server_url: str) -> None:
    page.goto(server_url)

    page.get_by_role("heading", name="Footage Data Manager").wait_for()
    page.get_by_role("link", name="New offload job").click()
    page.get_by_role("button", name="Create job request").click()

    page.get_by_text("Job request queued by the local runtime.").wait_for()
    page.get_by_text("Field Test - QUEUED").wait_for()
    assert page.locator("input[type=file]").count() == 0


def test_console_mobile_primary_action(page: Any, server_url: str) -> None:
    page.set_viewport_size({"width": 390, "height": 760})
    page.goto(server_url)

    cta = page.get_by_role("link", name="New offload job")
    cta.wait_for()

    assert cta.bounding_box() is not None
    page.get_by_text("local runtime performs file work").wait_for()


def test_console_reload_keeps_job_visible(page: Any, server_url: str) -> None:
    page.goto(server_url)
    page.get_by_role("button", name="Create job request").click()
    page.get_by_text("Field Test - QUEUED").wait_for()

    page.reload()

    page.get_by_text("Field Test - QUEUED").wait_for()
