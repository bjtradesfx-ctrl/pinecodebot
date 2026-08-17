import os
import requests
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "YOUR_DISCORD_WEBHOOK_HERE")
CHART_URL = os.environ.get("TV_CHART_URL", "https://tr.tradingview.com/chart/0pL1VjCl/?symbol=FX%3AEURUSD")


def take_chart_screenshot(output_path="chart.png"):
    """Launches stealth Chromium to bypass bot checks and capture the TradingView chart."""
    with sync_playwright() as p:
        # Launch with flags that hide automation from TradingView/Cloudflare
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )

        # Emulate a real Windows desktop browser context
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            device_scale_factor=2
        )
        page = context.new_page()

        try:
            # Navigate to the chart layout and wait for network to settle
            page.goto(CHART_URL, wait_until="domcontentloaded", timeout=60000)

            # Give TradingView's heavy WebSockets and indicators 8 seconds to fully render candles
            page.wait_for_timeout(8000)

            # Take the screenshot
            page.screenshot(path=output_path, full_page=False)
        except Exception as e:
            print(f"Playwright rendering error: {e}")
        finally:
            browser.close()

    return output_path


@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No JSON payload received"}), 400

        ticker = data.get("ticker", "EURUSD")
        action = data.get("action", "ALERT UPDATE")
        price = data.get("price", "0.00")
        details = data.get("details", "No details provided")

        # Color routing: Red for Loss, Green for Profit/Entries
        embed_color = 3066993  # Default Green
        if "Loss" in details or "🛑" in details:
            embed_color = 15158332  # Red for Loss
        elif "Profit" in details or "✅" in details:
            embed_color = 3066993  # Green for Profit

        # Take screenshot with stealth browser
        screenshot_file = "chart.png"
        take_chart_screenshot(screenshot_file)

        # Build Discord payload
        payload = {
            "embeds": [{
                "title": f"🚨 {ticker} SCALPER BOT 🚨",
                "color": embed_color,
                "fields": [
                    {"name": "Event Type", "value": str(action).upper(), "inline": True},
                    {"name": "Price", "value": str(price), "inline": True},
                    {"name": "Trade Execution Details", "value": details, "inline": False}
                ],
                "image": {"url": "attachment://chart.png"},
                "footer": {"text": "Powered by PyCharm & Playwright"}
            }]
        }

        # Send multipart request with image attached to Discord
        if os.path.exists(screenshot_file):
            with open(screenshot_file, "rb") as img:
                files = {
                    "file": ("chart.png", img, "image/png")
                }
                response = requests.post(
                    DISCORD_WEBHOOK_URL,
                    data={"payload_json": requests.compat.json.dumps(payload)},
                    files=files
                )
                response.raise_for_status()

            # Clean up local file
            os.remove(screenshot_file)
        else:
            # Fallback if screenshot failed entirely: send text embed only
            response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
            response.raise_for_status()

        return jsonify({"status": "success", "message": "Signal + Chart Screenshot sent!"}), 200

    except Exception as e:
        print(f"Error processing webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)