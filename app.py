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
    """Takes a fullscreen, close-up screenshot and sends a formatted plain-text signal."""
    screenshot_file = f"chart_{ticker}.png"

    try:
        # 1. Launch Playwright Headless Browser
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()

            print(f"Loading chart for {ticker}...")
            page.goto(CHART_URL, wait_until="load", timeout=60000)

            # Wait for indicators and candles to render
            page.wait_for_timeout(8000)

            # Fullscreen mode: hides sidebars, header, and watchlists
            page.keyboard.press("Shift+F")
            page.wait_for_timeout(1000)

            # Reset chart scale to default auto
            page.keyboard.press("Alt+R")
            page.wait_for_timeout(500)

            # Zoom in to make the entry candle and strategy box clearly visible
            for _ in range(2):
                page.keyboard.press("Control+ArrowUp")
                page.wait_for_timeout(200)

            # Take the focused screenshot
            page.screenshot(path=screenshot_file)
            browser.close()
            print("Screenshot captured successfully!")

        # 2. Build the copyable plain-text signal format
        formatted_details = details.replace("SL:", "**SL:**").replace("TP:", "**TP:**")

        signal_text = (
            f"**PAIR:** {ticker}\n"
            f"**ACTION:** {str(action).upper()}\n"
            f"**ENTRY:** {formatted_details}"
        )

        payload = {
            "content": signal_text
        }

        # 3. Send text and image to Discord
        with open(screenshot_file, "rb") as img:
            files = {"files[0]": (screenshot_file, img, "image/png")}
            requests.post(
                DISCORD_WEBHOOK_URL,
                data={"payload_json": json.dumps(payload)},
                files=files
            )
            print("Successfully sent signal to Discord.")

    except Exception as e:
        print(f"Screenshot Error: {e}")
        # Fallback text if the screenshot fails
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