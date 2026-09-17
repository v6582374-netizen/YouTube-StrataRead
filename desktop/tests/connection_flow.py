"""UI regression: run with uv run --with playwright python desktop/tests/connection_flow.py.

Requires a running Vite server and a Playwright Chromium installation.
Only the native bridge is faked; the actual application is loaded.
"""

import asyncio
import os

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        )
        page = await browser.new_page()
        await page.add_init_script(
            """window.__TAURI_INTERNALS__ = {invoke: async (cmd) => { if(cmd==='connection_status') {await new Promise(r=>setTimeout(r,1500)); return {configured:false,authorized:false,subscription_count:0}} if(cmd==='configure_connection') {await new Promise(r=>setTimeout(r,300)); if (!window.saveAttempted) {window.saveAttempted=true; throw 'Automic Vault could not save the Google OAuth client'} return {configured:true,authorized:false,subscription_count:0}} if(cmd==='library_list') return {assets:[]}; if(cmd==='library_snapshot') return {workspace:{label:'Local'},counts:{}}; if(cmd==='plugin:event|listen') return 1; return {}; }, transformCallback:()=>1, unregisterCallback:()=>{}}; window.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};"""
        )
        await page.goto("http://127.0.0.1:1420")
        await page.get_by_role("button", name="连接 YouTube", exact=True).click()
        await page.wait_for_timeout(100)
        immediate = await page.get_by_role("dialog").is_visible()
        await page.get_by_role("dialog").wait_for()
        await page.get_by_label("Google OAuth Client ID").fill("fixture")
        await page.get_by_label("Google OAuth Client Secret").fill("fixture")
        await page.get_by_role("button", name="保存到 Automic Vault", exact=True).click()
        assert await page.get_by_role("button", name="正在保存…", exact=True).is_disabled()
        assert await page.get_by_role("dialog").get_by_role("status").is_visible()
        await page.wait_for_timeout(500)
        error = (
            await page.get_by_role("dialog")
            .get_by_text("Automic Vault could not save", exact=False)
            .count()
        )
        print({"immediate_dialog": immediate, "visible_save_error": bool(error)})
        assert immediate and error
        await page.get_by_role("button", name="保存到 Automic Vault", exact=True).click()
        await page.get_by_role("button", name="在浏览器中授权并导入订阅").wait_for()
        assert await page.get_by_role("dialog").get_by_text("凭据已保存", exact=False).is_visible()
        print({"successful_save_advances_to_authorization": True})
        await browser.close()


asyncio.run(main())
