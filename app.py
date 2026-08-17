import os
import json
import threading
import requests
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# Environment Variables
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "YOUR_DISCORD_WEBHOOK_HERE")
CHART_URL = os.environ.get("TV_CHART_URL", "https://tr.tradingview.com/chart/0pL1VjCl/?symbol=FX%3AEURUSD")


def process_alert_in_background(ticker, action, price, details):
    """Downloads the native TradingView snapshot to get the exact watermark and framing."""
    screenshot_file = f"chart_{ticker}.png"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )

            # accept_downloads=True is REQUIRED to intercept TradingView's native image export
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                accept_downloads=True
            )
            page = context.new_page()

            print(f"Loading chart for {ticker}...")
            page.goto(CHART_URL, wait_until="load", timeout=60000)

            # Wait for indicators and candles to render
            page.wait_for_timeout(8000)

            # Reset chart scale to default auto (matches the exact zoom in your reference image)
            page.keyboard.press("Alt+R")
            page.wait_for_timeout(1000)

            # ATTEMPT NATIVE SNAPSHOT (The exact format with watermark and logo)
            try:
                with page.expect_download(timeout=10000) as download_info:
                    # 1. Click the Camera icon on the top right
                    page.locator(
                        'button[aria-label="Take a snapshot"], button[data-name="take-snapshot"], #header-toolbar-screenshot').first.click()
                    page.wait_for_timeout(1000)

                    # 2. Click "Download image" from the dropdown menu
                    page.locator(
                        '[data-name="save-chart-image"], :text("Download image"), :text("Save chart image")').first.click()

                # Save the cleanly exported file
                download = download_info.value
                download.save_as(screenshot_file)
                print("Native TradingView snapshot downloaded successfully!")

            except Exception as native_e:
                print(f"Native snapshot failed, using fallback: {native_e}")
                # FALLBACK: Fullscreen manual crop if TradingView's UI blocks the button
                page.keyboard.press("Shift+F")
                page.wait_for_timeout(1500)
                page.screenshot(path=screenshot_file)

            browser.close()

        # Build the copyable plain-text signal format
        formatted_details = details.replace("SL:", "**SL:**").replace("TP:", "**TP:**")

        signal_text = (
            f"**PAIR:** {ticker}\n"
            f"**ACTION:** {str(action).upper()}\n"
            f"**ENTRY:** {formatted_details}"
        )

        payload = {
            "content": signal_text
        }

        # Send text and image to Discord
        with open(screenshot_file, "rb") as img:
            files = {"files[0]": (screenshot_file, img, "image/png")}
            requests.post(
                DISCORD_WEBHOOK_URL,
                data={"payload_json": json.dumps(payload)},
                files=files
            )
            print("Successfully sent signal to Discord.")

    except Exception as e:
        print(f"Background Process Error: {e}")
        # Fallback text if screenshot pipeline completely fails
        formatted_details = details.replace("SL:", "**SL:**").replace("TP:", "**TP:**")
        fallback_text = (
            f"**PAIR:** {ticker}\n"
            f"**ACTION:** {str(action).upper()}\n"
            f"**ENTRY:** {formatted_details}\n"
            f"*(Screenshot capture failed: {e})*"
        )
        requests.post(DISCORD_WEBHOOK_URL, json={"content": fallback_text})

    finally:
        # Clean up local image file
        if os.path.exists(screenshot_file):
            os.remove(screenshot_file)


@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON payload received"}), 400

        ticker = data.get("ticker", "UNKNOWN")
        action = data.get("action", "ALERT UPDATE")
        price = data.get("price", "0.00")
        details = data.get("details", "No details")

        # Process in background thread to avoid webhook timeouts
        threading.Thread(
            target=process_alert_in_background,
            args=(ticker, action, price, details)
        ).start()

        return jsonify({"status": "success", "message": "Signal processing"}), 200

    except Exception as e:
        print(f"Webhook Error: {e}")
        return jsonify({"error": str(e)}), 400


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)