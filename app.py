from flask import Flask, request, jsonify, render_template
from chatbot import ask_chatbot
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__, template_folder="templates")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(force=True)
        print("Received input:", data)
        user_input = data.get("message", "")
        response = ask_chatbot(user_input)
        return jsonify({"response": response})
    except Exception as e:
        print("❌ Error:", e)
        return jsonify({"response": "An error occurred processing your message."}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
