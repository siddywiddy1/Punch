from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from datetime import datetime

from punch.sanitizer import sanitize_and_frame

logger = logging.getLogger("punch.browser")

# Default CDP endpoint when Chrome is launched with --remote-debugging-port=9222
_DEFAULT_CDP_URL = "http://127.0.0.1:9222"


class BrowserManager:
    def __init__(self, screenshots_dir: str = "data/screenshots", cdp_url: str | None = None):
        self.screenshots_dir = screenshots_dir
        self.cdp_url = cdp_url
        self._browser = None
        self._playwright = None
        self._mode = None  # "cdp" or "headless"

    @property
    def is_running(self) -> bool:
        return self._browser is not None

    async def start(self):
        from playwright.async_api import async_playwright
        Path(self.screenshots_dir).mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()

        # Try CDP connection first if configured
        if self.cdp_url:
            try:
                self._browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url)
                self._mode = "cdp"
                logger.info(f"Connected to Chrome via CDP at {self.cdp_url}")
                return
            except Exception as e:
                logger.warning(f"Failed to connect to Chrome via CDP ({self.cdp_url}): {e}")
                logger.info("Falling back to headless Chromium")

        self._browser = await self._playwright.chromium.launch(headless=True)
        self._mode = "headless"
        logger.info("Browser started (headless Chromium)")

    async def stop(self):
        if self._browser:
            if self._mode == "cdp":
                # Don't close the user's actual Chrome — just disconnect
                self._browser = None
            else:
                await self._browser.close()
                self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Browser stopped")

    async def new_page(self):
        if not self._browser:
            await self.start()

        if self._mode == "cdp":
            # Use existing browser context (user's real Chrome profile)
            contexts = self._browser.contexts
            if contexts:
                return await contexts[0].new_page()
            # Fallback: create a new context
            context = await self._browser.new_context()
            return await context.new_page()

        context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )
        return await context.new_page()

    async def screenshot(self, page, name: str | None = None) -> str:
        if not name:
            name = f"screenshot_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
        path = Path(self.screenshots_dir) / name
        await page.screenshot(path=str(path))
        return str(path)

    async def navigate(self, url: str) -> dict:
        """Navigate to a URL, take screenshot, return page info."""
        page = await self.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            title = await page.title()
            screenshot_path = await self.screenshot(page)
            content = await page.content()
            return {
                "url": page.url,
                "title": title,
                "screenshot": screenshot_path,
                "content_length": len(content),
            }
        finally:
            await page.close()

    async def execute_script(self, url: str, script: str) -> dict:
        """Navigate to URL and execute JavaScript."""
        page = await self.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            result = await page.evaluate(script)
            screenshot_path = await self.screenshot(page)
            return {
                "url": page.url,
                "result": result,
                "screenshot": screenshot_path,
            }
        finally:
            await page.close()

    async def fill_form(self, url: str, fields: dict[str, str], submit_selector: str | None = None) -> dict:
        """Navigate to URL, fill form fields, optionally submit."""
        page = await self.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            for selector, value in fields.items():
                await page.fill(selector, value)
            if submit_selector:
                await page.click(submit_selector)
                await page.wait_for_load_state("networkidle")
            screenshot_path = await self.screenshot(page)
            return {
                "url": page.url,
                "screenshot": screenshot_path,
            }
        finally:
            await page.close()

    async def scrape_text(self, url: str, selector: str = "body",
                          sanitize: bool = True) -> str:
        """Navigate to URL and extract text content.

        When sanitize=True (default), the scraped content is sanitized
        to defend against prompt injection and wrapped in data delimiters.
        """
        page = await self.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            element = await page.query_selector(selector)
            if element:
                text = await element.inner_text()
                if sanitize:
                    return sanitize_and_frame(text, source=url)
                return text
            return ""
        finally:
            await page.close()
