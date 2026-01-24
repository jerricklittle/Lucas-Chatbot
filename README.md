# Custom Chatbot

This is a simple Flask-based chatbot template using the OpenAI API.

## Structure

- `chatbot.py`: Chat wrapper for OpenAI
- `app.py`: Flask web server with POST endpoint
- `.env`: API key (edit this in Codespace)
- `.devcontainer/`: GitHub Codespace config

## Quick Start

### 1. Make a copy of .env.example called .env

```bash
cp .env.example .env
```

### 2. Paste your API Key in the .env file

```txt
OPENAI_API_KEY=your-api-key-here
```

### 3. Run the app from the Run/Debug extension

Click on the menu on left (Run button with Bug icon) amd click the Run Flask button.

