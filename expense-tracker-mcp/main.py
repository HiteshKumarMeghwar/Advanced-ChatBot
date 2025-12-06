from fastmcp import FastMCP
import os
import sqlite3

# database path
DB_PATH = os.path.join(os.path.dirname(__file__), "expenses.db")

# categories path
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

# create a FastMCP server instance
mcp = FastMCP("ExpenseTracker")


def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.execute(
        """CREATE TABLE IF NOT EXISTS expenses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            subcategory TEXT DEFAULT '',
            note TEXT DEFAULT '',
            type TEXT DEFAULT 'debit'
        )
        """
        )


init_db()


# tools

@mcp.tool
def add_expense(date, amount, category, subcategory="", note=""):
    """Add a new expense entry to the database."""
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
            (date, amount, category, subcategory, note)
        )
        c.commit()
        return {"status": "OK", "id": cur.lastrowid}

@mcp.tool
def list_expenses(start_date, end_date):
    """List all expense entries within an inclusive date range."""
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            """
            SELECT id, data, amount, category, subcategory, note
            FROM expenses
            WHERE date BETWEEN ? AND ?
            ORDER BY id ASC
            """,
            (start_date, end_date)
        )
        c.commit()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    
@mcp.tool
def summarize(start_date, end_date, category=None):
    """Summarize expenses by category within an inclusive date range."""
    with sqlite3.connect(DB_PATH) as c:
        query = (
            """
            SELECT category, SUM(amount) AS total_amount
            FROM expenses
            WHERE date BETWEEN ? AND ?
            """
        )
        params = [start_date, end_date]

        if category:
            query += "AND category = ?"
            params.append(category)

        query += "GROUP BY category ORDER BY category ASC"

        cur = c.execute(query, params)
        c.commit()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

@mcp.resource("expense://categories", mime_type="application/json")
def categories():
    # Read fresh each time so you can edit the file without restarting
    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        return f.read()


@mcp.tool
def edit_expense(id, date=None, amount=None, category=None, subcategory=None, note=None):
    """Edit an existing expense entry by ID."""
    with sqlite3.connect(DB_PATH) as c:
        # Build dynamic update query
        fields = []
        values = []

        if date:
            fields.append("date = ?")
            values.append(date)

        if amount:
            fields.append("amount = ?")
            values.append(amount)

        if category:
            fields.append("category = ?")
            values.append(category)

        if subcategory:
            fields.append("subcategory = ?")
            values.append(subcategory)

        if note:
            fields.append("note = ?")
            values.append(note)

        if not fields:
            return {"status": "NO_CHANGES", "message": "Nothing to update"}

        values.append(id)
        query = f"UPDATE expenses SET {', '.join(fields)} WHERE id = ?"

        c.execute(query, values)
        c.commit()

        return {"status": "OK", "updated_id": id}


@mcp.tool
def delete_expense(id):
    """Delete an expense entry by ID."""
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute("DELETE FROM expenses WHERE id = ?", (id,))
        c.commit()

        if cur.rowcount == 0:
            return {"status": "NOT_FOUND", "id": id}

        return {"status": "OK", "deleted_id": id}


@mcp.tool
def add_credit_expense(date, amount, category, subcategory="", note=""):
    """Add a credit (incoming money) entry to the database."""
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            """
            INSERT INTO expenses(date, amount, category, subcategory, note, type)
            VALUES (?, ?, ?, ?, ?, 'credit')
            """,
            (date, amount, category, subcategory, note)
        )
        return {"status": "OK", "id": cur.lastrowid, "type": "credit"}



if __name__ == "__main__":
    # run the server
    mcp.run()
