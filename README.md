# Arabic Restaurant Ordering Agent (المساعد الذكي للمطاعم)

An AI-powered agentic system designed to handle restaurant orders in Arabic, providing a natural conversational experience for delivery and pickup orders.

## Overview

This project implements a multi-agent system that simulates a restaurant call center or WhatsApp ordering bot. It handles the entire customer journey from greeting to order confirmation, ensuring accurate data collection and a smooth user experience.

### Key Features
- **Arabic-First Design**: Optimized for Arabic nuances, dialects, and RTL support.
- **Multi-Agent Architecture**: Specialized agents for Greeting, Location, Ordering, and Checkout.
- **Context Management**: Efficiently handles long conversations and complex menus (100+ items).
- **Evaluation Framework**: Includes a robust testing suite with user simulation and LLM-based judging.

## Setup

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**
   Copy the example environment file and add your OpenRouter API key:
   ```bash
   cp .env.example .env
   # Edit .env and set OPENROUTER_API_KEY=your_key_here
   ```

## Usage

### Run the Agent
Start the interactive console to chat with the agent:

```bash
python main.py
```

### RTL Support (Right-to-Left)
To ensure optimal display of Arabic text in your terminal:

- **Standard (Default)**: Uses Unicode bidirectional marks. Best for modern terminals.
  ```bash
  python main.py
  ```

- **Fallback**: Reverses Arabic text for correct visual display in terminals with poor RTL support.
  ```bash
  python main.py --rtl fallback
  ```

## Development & Testing

See [tests/README.md](tests/README.md) for detailed instructions on running the evaluation suite.

### Quick Test Run
Run all automated scenarios to verify system performance:

```bash
python tests/run_eval.py
```

## Architecture

The system is built on a modular multi-agent architecture:

- **Agents**: `Greeting`, `Location`, `Order`, `Checkout`
- **Core**: Handles session state (`SessionStore`), logging, and tool execution.
- **Data**: Menu data stored in `data/menu.json`.

---
*Submitted for the Agent Engineer Take-Home Assessment by Sawt.*
