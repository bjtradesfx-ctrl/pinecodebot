import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1538899048839258162/LQ79MbfFTVkI7vlFNbmdkoLu4u_puQRCqr8IVS-NYyoXMVZ3MnpALYjEdJjm2xTHmELN")

@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No JSON payload received"}), 400

        ticker = data.get("ticker", "UNKNOWN")
        action = data.get("action", "ALERT UPDATE")
        price = data.get("price", "0.00")
        details = data.get("details", "No details provided")

        embed_color = 3066993  # Default Green
        if "Loss" in details or "🛑" in details:
            embed_color = 15158332  # Red for Loss
        elif "Profit" in details or "✅" in details:
            embed_color = 3066993  # Green for Profit

        discord_payload = {
            "embeds": [{
                "title": f"🚨 {ticker} SCALPER BOT 🚨",
                "color": embed_color,
                "fields": [
                    {"name": "Event Type", "value": str(action).upper(), "inline": True},
                    {"name": "Price", "value": str(price), "inline": True},
                    {"name": "Trade Execution Details", "value": details, "inline": False}
                ],
                "footer": {"text": "Powered by PyCharm & Flask"}
            }]
        }

        response = requests.post(DISCORD_WEBHOOK_URL, json=discord_payload)
        response.raise_for_status()

        return jsonify({"status": "success", "message": "Signal forwarded to Discord!"}), 200

    except Exception as e:
        print(f"Error processing webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)