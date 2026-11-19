# 💰 Expense & Income Tracker MCP Server

A personal finance MCP (Model Context Protocol) server built using [FastMCP](https://github.com/jlowin/fastmcp). It enables AI assistants (like Claude) to record, organize, analyze, and manage your expenses and income directly through natural conversations, backed by an asynchronous SQLite database (`aiosqlite`) for high-concurrency multi-user access.

---

## 🚀 Features

### 🛠️ MCP Tools
- **`add_expense`**: Record an expense with amount, category, subcategory, description, and date.
- **`add_income`**: Record salary, freelance income, bonuses, refunds, etc.
- **`show_all_transactions`**: View transactions formatted cleanly with filters (`all`, `expense`, or `income`).
- **`edit_transaction`**: Update any field of an existing transaction by ID.
- **`delete_transaction`**: Remove any transaction by ID.
- **`get_balance_summary`**: Instantly calculate total income, total expenses, and current net balance.
- **`list_categories`**: View the full hierarchy of supported expense and income categories with explanations.
- **`reset_id_counter`**: Renumbers existing records sequentially starting from 1 to eliminate gaps left by deleted test data.

### 📚 MCP Resource
- **`categories://all`**: Exposes [categories.json](categories.json) to AI assistants so they can automatically categorize user purchases and income into clear categories and subcategories.

---

## 📂 Project Structure

```text
├── categories.json      # Resource: Hierarchy of categories & subcategories with descriptions
├── main.py              # Main FastMCP server definition, tools, and SQLite storage
├── pyproject.toml       # Python project configuration and dependencies
├── requirements.txt     # Standard requirements file for cloud deployment
├── .gitignore           # Git ignore rules for venv, cache, and local databases
└── README.md            # Project documentation
```

---

## 💻 Local Setup & Development

### 1. Clone the repository
```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
```

### 2. Install dependencies with `uv`
```bash
uv sync
```
*(Or with pip: `pip install -r requirements.txt`)*

### 3. Run the server locally
```bash
uv run python main.py
```
By default, the server starts on `http://0.0.0.0:8000/sse`.

---

## ☁️ FastMCP Cloud Deployment

1. Push this repository to your **GitHub** account.
2. Log in to [FastMCP Cloud / Prefect Horizon](https://horizon.prefect.io).
3. Connect your GitHub repository.
4. Set the server target:
   - **File / Object**: `main.py:mcp`
5. Once deployed, FastMCP Cloud will provide you with your public remote MCP URL (e.g., `https://.../sse`).

---

## 🔌 Connecting to Claude Desktop

### For Remote Server (FastMCP Cloud / SSE)
Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "expense-tracker": {
      "url": "https://<your-fastmcp-cloud-url>/sse"
    }
  }
}
```

### For Local Execution (Stdio mode)
```json
{
  "mcpServers": {
    "expense-tracker": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "fastmcp",
        "python",
        "/path/to/main.py"
      ]
    }
  }
}
```

---

## 🔒 Privacy Note
Your personal financial database file (`expenses.db`) is ignored by `.gitignore` and is **never** committed or pushed to GitHub.
