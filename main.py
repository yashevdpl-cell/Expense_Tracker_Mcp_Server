import aiosqlite
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from fastmcp import FastMCP

# ----------------------------------------------------
# 1. Initialize FastMCP Server
# ----------------------------------------------------
mcp = FastMCP(name="Expense Tracker")

# ----------------------------------------------------
# 2. File & Database Paths
# ----------------------------------------------------
BASE_DIR = Path(__file__).parent
CATEGORIES_PATH = BASE_DIR / "categories.json"

def get_db_path() -> Path:
    """
    Determine a writable path for the SQLite database.
    1. If DATABASE_PATH environment variable is set, use it.
    2. Try the local project directory (default for local development).
    3. If the directory is read-only (common in cloud container deployments like /app),
       fallback to the system temp directory (/tmp/expenses.db).
    """
    env_path = os.environ.get("DATABASE_PATH")
    if env_path:
        p = Path(env_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    local_db = BASE_DIR / "expenses.db"
    try:
        # Check if directory is writable
        test_file = BASE_DIR / ".write_test"
        test_file.touch()
        test_file.unlink()
        return local_db
    except (PermissionError, OSError):
        # Cloud containers (e.g. FastMCP Cloud) have a read-only /app, but /tmp is always writable
        return Path(tempfile.gettempdir()) / "expenses.db"

DB_PATH = get_db_path()

_db_initialized = False

async def ensure_db():
    """
    Asynchronously create the transactions table if it does not already exist,
    and ensure the subcategory and description columns are present.
    Runs once safely without blocking server startup.
    """
    global _db_initialized
    if _db_initialized:
        return

    async with aiosqlite.connect(DB_PATH) as conn:
        # Create table with all required columns
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                type TEXT NOT NULL,            -- 'expense' or 'income'
                category TEXT NOT NULL,        -- e.g. 'Food & Dining'
                subcategory TEXT DEFAULT '',   -- e.g. 'Groceries'
                amount REAL NOT NULL,          -- money amount
                description TEXT DEFAULT ''    -- full description/notes
            )
        """)

        # Ensure subcategory column exists if table existed previously
        async with conn.execute("PRAGMA table_info(transactions)") as cursor:
            rows = await cursor.fetchall()
            columns = [row[1] for row in rows]
            if "subcategory" not in columns:
                await conn.execute("ALTER TABLE transactions ADD COLUMN subcategory TEXT DEFAULT ''")

        await conn.commit()

    _db_initialized = True


# ----------------------------------------------------
# 3. MCP Resource: Categories & Subcategories Guide
# ----------------------------------------------------
# MCP Resources allow Claude to read context data directly.
@mcp.resource("categories://all")
async def get_categories_resource() -> str:
    """
    Returns the comprehensive JSON guide containing all expense and income
    categories, subcategories, and their detailed descriptions.
    """
    if CATEGORIES_PATH.exists():
        return CATEGORIES_PATH.read_text(encoding="utf-8")
    return json.dumps({"error": "categories.json file not found"})


# ----------------------------------------------------
# 4. Tool: List Available Categories & Subcategories
# ----------------------------------------------------
@mcp.tool
async def list_categories(category_type: str = "all") -> str:
    """
    View all available categories and their subcategories with descriptions.
    
    Parameters:
    - category_type: 'all', 'expense', or 'income'
    """
    if not CATEGORIES_PATH.exists():
        return "categories.json file not found."

    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    lines = []
    
    # Process Expense Categories
    if category_type.lower() in ["all", "expense"]:
        lines.append("=== 🔴 EXPENSE CATEGORIES & SUBCATEGORIES ===")
        for cat, details in data.get("expense_categories", {}).items():
            lines.append(f"\n📂 {cat} : {details.get('description', '')}")
            for sub, sub_desc in details.get("subcategories", {}).items():
                lines.append(f"   └── 🏷️ {sub} : {sub_desc}")

    # Process Income Categories
    if category_type.lower() in ["all", "income"]:
        lines.append("\n=== 🟢 INCOME CATEGORIES & SUBCATEGORIES ===")
        for cat, details in data.get("income_categories", {}).items():
            lines.append(f"\n📂 {cat} : {details.get('description', '')}")
            for sub, sub_desc in details.get("subcategories", {}).items():
                lines.append(f"   └── 🏷️ {sub} : {sub_desc}")

    return "\n".join(lines)


# ----------------------------------------------------
# 5. Tool: Add Expense (Asynchronous)
# ----------------------------------------------------
@mcp.tool
async def add_expense(
    amount: float,
    category: str,
    subcategory: str = "",
    description: str = "",
    date: str = ""
) -> str:
    """
    Record a new expense asynchronously with a category, subcategory, and detailed description.
    
    Parameters:
    - amount: Money spent (e.g. 250.00)
    - category: Main category (e.g. 'Food & Dining', 'Transportation & Commute')
    - subcategory: Subcategory (e.g. 'Groceries', 'Fuel & Petrol', 'Food Delivery')
    - description: Clear details about the expense (e.g. 'Bought 2kg apples & milk from supermarket')
    - date: Optional date YYYY-MM-DD (defaults to today's date if empty)
    """
    await ensure_db()
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            INSERT INTO transactions (date, type, category, subcategory, amount, description)
            VALUES (?, 'expense', ?, ?, ?, ?)
        """, (date, category, subcategory, amount, description))
        await conn.commit()
        new_id = cursor.lastrowid

    sub_info = f" > {subcategory}" if subcategory else ""
    desc_info = f" | Description: '{description}'" if description else ""
    return f"Expense recorded! ID: {new_id} | Amount: ₹{amount:.2f} | Category: {category}{sub_info}{desc_info} | Date: {date}"


# ----------------------------------------------------
# 6. Tool: Add Income / Credit (Asynchronous)
# ----------------------------------------------------
@mcp.tool
async def add_income(
    amount: float,
    category: str = "Employment",
    subcategory: str = "Monthly Salary",
    description: str = "",
    date: str = ""
) -> str:
    """
    Record money received asynchronously (salary, freelance, investments, refund, etc.) with description.
    
    Parameters:
    - amount: Money received (e.g. 50000.00)
    - category: Main income category (e.g. 'Employment', 'Freelance & Side Business')
    - subcategory: Subcategory (e.g. 'Monthly Salary', 'Client Projects')
    - description: Clear details about the income (e.g. 'Received monthly salary from company')
    - date: Optional date YYYY-MM-DD (defaults to today's date if empty)
    """
    await ensure_db()
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            INSERT INTO transactions (date, type, category, subcategory, amount, description)
            VALUES (?, 'income', ?, ?, ?, ?)
        """, (date, category, subcategory, amount, description))
        await conn.commit()
        new_id = cursor.lastrowid

    sub_info = f" > {subcategory}" if subcategory else ""
    desc_info = f" | Description: '{description}'" if description else ""
    return f"Income recorded! ID: {new_id} | Amount: ₹{amount:.2f} | Category: {category}{sub_info}{desc_info} | Date: {date}"


# ----------------------------------------------------
# 7. Tool: Show All Transactions / Expenses (Asynchronous)
# ----------------------------------------------------
@mcp.tool
async def show_all_transactions(filter_type: str = "all") -> str:
    """
    View transactions stored in the database asynchronously with category, subcategory, and description.
    
    Parameters:
    - filter_type: 'all' to see everything, 'expense' for expenses only, or 'income' for income only.
    """
    await ensure_db()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if filter_type.lower() in ["expense", "income"]:
            async with conn.execute(
                "SELECT * FROM transactions WHERE type = ? ORDER BY date DESC, id DESC", 
                (filter_type.lower(),)
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with conn.execute(
                "SELECT * FROM transactions ORDER BY date DESC, id DESC"
            ) as cursor:
                rows = await cursor.fetchall()

    if not rows:
        return f"No records found for filter: '{filter_type}'."

    output = [
        f"=== TRANSACTIONS LIST ({filter_type.upper()}) ===",
        "-" * 65,
    ]
    for row in rows:
        tag = "🔴 [EXPENSE]" if row["type"] == "expense" else "🟢 [INCOME] "
        sub = f" > {row['subcategory']}" if row["subcategory"] else ""
        desc = row["description"] if row["description"] else "No description provided"
        
        output.append(
            f"ID #{row['id']} | {tag} | Date: {row['date']} | Amount: ₹{row['amount']:.2f}\n"
            f"  Category:    {row['category']}{sub}\n"
            f"  Description: {desc}\n"
            + ("-" * 65)
        )

    return "\n".join(output)


# ----------------------------------------------------
# 8. Tool: Edit Transaction (Asynchronous)
# ----------------------------------------------------
@mcp.tool
async def edit_transaction(
    transaction_id: int,
    amount: float = None,
    category: str = None,
    subcategory: str = None,
    description: str = None,
    date: str = None,
    transaction_type: str = None
) -> str:
    """
    Edit/update an existing transaction asynchronously by its ID number.
    Only the provided fields will be modified.
    """
    await ensure_db()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)) as cursor:
            record = await cursor.fetchone()
            if not record:
                return f"Error: Transaction ID {transaction_id} does not exist."

        # Keep old value if a parameter was not passed
        updated_amount = amount if amount is not None else record["amount"]
        updated_category = category if category is not None else record["category"]
        updated_subcategory = subcategory if subcategory is not None else record["subcategory"]
        updated_desc = description if description is not None else record["description"]
        updated_date = date if date is not None else record["date"]
        updated_type = transaction_type.lower() if transaction_type is not None else record["type"]

        await conn.execute("""
            UPDATE transactions
            SET amount = ?, category = ?, subcategory = ?, description = ?, date = ?, type = ?
            WHERE id = ?
        """, (updated_amount, updated_category, updated_subcategory, updated_desc, updated_date, updated_type, transaction_id))
        await conn.commit()

    return f"Transaction ID {transaction_id} updated successfully!"


# ----------------------------------------------------
# 9. Tool: Delete Transaction (Asynchronous)
# ----------------------------------------------------
@mcp.tool
async def delete_transaction(transaction_id: int) -> str:
    """
    Delete a transaction asynchronously by its ID number.
    """
    await ensure_db()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)) as cursor:
            if not await cursor.fetchone():
                return f"Error: Transaction ID {transaction_id} not found."

        await conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        await conn.commit()

    return f"Transaction ID {transaction_id} deleted successfully."


# ----------------------------------------------------
# 10. Tool: Reset ID Counter / Renumber Transactions (Asynchronous)
# ----------------------------------------------------
@mcp.tool
async def reset_id_counter(renumber_existing: bool = True) -> str:
    """
    Reset the auto-increment ID counter asynchronously.
    
    Parameters:
    - renumber_existing: 
        If True (default): Renumbers all current transactions sequentially starting
        from ID 1 (e.g. 1, 2, 3...) so there are no gaps from deleted test records,
        and sets the next new transaction to start right after.
        If False: Leaves existing IDs untouched, but resets the counter so the next
        transaction uses the current highest ID + 1 instead of skipping numbers.
    """
    await ensure_db()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT id FROM transactions ORDER BY id ASC") as cursor:
            rows = await cursor.fetchall()

        if not rows:
            # Table is completely empty, reset sqlite auto-increment sequence to 0
            await conn.execute("DELETE FROM sqlite_sequence WHERE name = 'transactions'")
            await conn.commit()
            return "All test transactions were deleted. ID counter is completely reset to 0! The next transaction will start at ID 1."

        if renumber_existing:
            # Re-insert existing rows cleanly so IDs start sequentially from 1
            await conn.execute("""
                CREATE TEMPORARY TABLE temp_tx AS 
                SELECT date, type, category, subcategory, amount, description 
                FROM transactions ORDER BY id ASC
            """)
            await conn.execute("DELETE FROM transactions")
            await conn.execute("DELETE FROM sqlite_sequence WHERE name = 'transactions'")
            await conn.execute("""
                INSERT INTO transactions (date, type, category, subcategory, amount, description)
                SELECT date, type, category, subcategory, amount, description FROM temp_tx
            """)
            await conn.execute("DROP TABLE temp_tx")
            await conn.commit()

            async with conn.execute("SELECT MAX(id) FROM transactions") as cursor:
                row = await cursor.fetchone()
                new_max = row[0] or 0
            return f"Reset complete! Renumbered all {len(rows)} existing transactions starting from ID 1. Next new transaction will be ID {new_max + 1}."
        else:
            # Just set the sequence counter to the current highest ID
            async with conn.execute("SELECT MAX(id) FROM transactions") as cursor:
                row = await cursor.fetchone()
                max_id = row[0] or 0
            await conn.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'transactions'", (max_id,))
            await conn.commit()
            return f"ID counter adjusted to current highest ID ({max_id}). Next new transaction will be ID {max_id + 1}."


# ----------------------------------------------------
# 11. Tool: Financial Balance Summary (Asynchronous)
# ----------------------------------------------------
@mcp.tool
async def get_balance_summary() -> str:
    """
    Calculate and display total income, total expenses, and net remaining balance asynchronously.
    """
    await ensure_db()
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT SUM(amount) FROM transactions WHERE type = 'income'") as cursor:
            row = await cursor.fetchone()
            total_income = row[0] or 0.0

        async with conn.execute("SELECT SUM(amount) FROM transactions WHERE type = 'expense'") as cursor:
            row = await cursor.fetchone()
            total_expense = row[0] or 0.0

        balance = total_income - total_expense

    return (
        f"=== Financial Summary ===\n"
        f"🟢 Total Income:   ₹{total_income:.2f}\n"
        f"🔴 Total Expenses: ₹{total_expense:.2f}\n"
        f"💰 Net Balance:    ₹{balance:.2f}"
    )


# ----------------------------------------------------
# 12. Server Runner
# ----------------------------------------------------
if __name__ == "__main__":
    # Run the FastMCP server
    mcp.run(
        transport="sse",     # Enables HTTP/SSE network transport
        host="0.0.0.0",      # Binds to all network interfaces for remote access
        port=8000            # Port number
    )
