import sqlite3
from datetime import date, timedelta
import os

DB_PATH = '/Users/nada/PycharmProjects/Hackstorm/agent/financial_assistant.db'
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

-- User Profile
CREATE TABLE Users (
    UserId        INTEGER PRIMARY KEY AUTOINCREMENT,
    Name          TEXT NOT NULL,
    Email         TEXT UNIQUE NOT NULL,
    Age           INTEGER NULL,
    Occupation    TEXT NULL,
    CreatedAt     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Accounts / Wallets
CREATE TABLE Accounts (
    AccountId     INTEGER PRIMARY KEY AUTOINCREMENT,
    UserId        INTEGER NOT NULL,
    AccountName   TEXT NOT NULL, -- e.g., 'Main Checking', 'Savings', 'Cash', 'Credit Card'
    AccountType   TEXT NOT NULL, -- e.g., 'Checking', 'Savings', 'Credit'
    Balance       NUMERIC NOT NULL DEFAULT 0.00,
    Currency      TEXT NOT NULL DEFAULT 'USD',
    CreatedAt     TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT FK_Accounts_User FOREIGN KEY (UserId) REFERENCES Users(UserId)
);

-- Transactions (Income, Spending, Transfer)
CREATE TABLE Transactions (
    TransactionId INTEGER PRIMARY KEY AUTOINCREMENT,
    AccountId     INTEGER NOT NULL,
    TxnType       TEXT NOT NULL, -- 'Income', 'Expense', 'Transfer'
    Amount        NUMERIC NOT NULL,
    Category      TEXT NULL,     -- 'Groceries', 'Rent', 'Salary', 'Entertainment'
    Description   TEXT NULL,
    TxnDate       TEXT NOT NULL DEFAULT (datetime('now')),
    ToAccountId   INTEGER NULL,  -- Used if TxnType is 'Transfer'
    CONSTRAINT FK_Transactions_Account FOREIGN KEY (AccountId) REFERENCES Accounts(AccountId),
    CONSTRAINT FK_Transactions_ToAccount FOREIGN KEY (ToAccountId) REFERENCES Accounts(AccountId)
);

-- Loans / Debts
CREATE TABLE Loans (
    LoanId        INTEGER PRIMARY KEY AUTOINCREMENT,
    UserId        INTEGER NOT NULL,
    LoanType      TEXT NOT NULL, -- 'Borrow' (user owes money), 'Lend' (user is owed money)
    Counterparty  TEXT NOT NULL, -- Person or institution
    Amount        NUMERIC NOT NULL,
    Remaining     NUMERIC NOT NULL,
    DueDate       TEXT NULL,
    Status        TEXT NOT NULL DEFAULT 'Active', -- 'Active', 'Paid'
    CreatedAt     TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT FK_Loans_User FOREIGN KEY (UserId) REFERENCES Users(UserId)
);

-- Budgets
CREATE TABLE Budgets (
    BudgetId      INTEGER PRIMARY KEY AUTOINCREMENT,
    UserId        INTEGER NOT NULL,
    Category      TEXT NOT NULL,
    MonthlyLimit  NUMERIC NOT NULL,
    CreatedAt     TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT FK_Budgets_User FOREIGN KEY (UserId) REFERENCES Users(UserId),
    CONSTRAINT UQ_Budgets_Category UNIQUE (UserId, Category)
);
"""

def reset_db(path: str = DB_PATH):
    if os.path.exists(path):
        os.remove(path)

def create_schema(conn: sqlite3.Connection):
    conn.executescript(SCHEMA_SQL)

def seed_data(conn: sqlite3.Connection):
    cur = conn.cursor()
    
    # 1. Insert User
    cur.execute(
        "INSERT INTO Users (Name, Email, Age, Occupation) VALUES (?, ?, ?, ?)",
        ("John Doe", "john.doe@example.com", 30, "Software Engineer")
    )
    user_id = cur.lastrowid

    # 2. Insert Accounts
    accounts = [
        (user_id, "Main Checking", "Checking", 4500.00, "USD"),
        (user_id, "Emergency Fund", "Savings", 12000.00, "USD"),
        (user_id, "Cash Wallet", "Cash", 250.00, "USD"),
        (user_id, "Travel Credit Card", "Credit", -1250.50, "USD")
    ]
    cur.executemany(
        """
        INSERT INTO Accounts (UserId, AccountName, AccountType, Balance, Currency)
        VALUES (?, ?, ?, ?, ?)
        """, accounts
    )
    
    # Get Account IDs
    acc_map = {row[0]: row[1] for row in cur.execute("SELECT AccountName, AccountId FROM Accounts").fetchall()}
    chk_id = acc_map["Main Checking"]
    sav_id = acc_map["Emergency Fund"]
    crd_id = acc_map["Travel Credit Card"]

    # 3. Insert Budgets
    budgets = [
        (user_id, "Groceries", 600.00),
        (user_id, "Dining Out", 300.00),
        (user_id, "Entertainment", 200.00),
        (user_id, "Transport", 150.00),
        (user_id, "Rent", 2000.00)
    ]
    cur.executemany(
        "INSERT INTO Budgets (UserId, Category, MonthlyLimit) VALUES (?, ?, ?)", budgets
    )

    # 4. Insert Transactions
    # Generate some dummy transactions for the last 30 days
    today = date.today()
    txns = [
        (chk_id, "Income", 5000.00, "Salary", "Monthly Salary", (today - timedelta(days=15)).isoformat(), None),
        (chk_id, "Expense", 2000.00, "Rent", "Monthly Rent Payment", (today - timedelta(days=14)).isoformat(), None),
        (chk_id, "Expense", 120.50, "Groceries", "Whole Foods", (today - timedelta(days=12)).isoformat(), None),
        (crd_id, "Expense", 45.00, "Dining Out", "Pizza Place", (today - timedelta(days=10)).isoformat(), None),
        (crd_id, "Expense", 15.99, "Entertainment", "Netflix Subscription", (today - timedelta(days=8)).isoformat(), None),
        (chk_id, "Expense", 30.00, "Transport", "Gas Station", (today - timedelta(days=5)).isoformat(), None),
        (chk_id, "Transfer", 500.00, "Savings", "Transfer to Emergency Fund", (today - timedelta(days=2)).isoformat(), sav_id),
        (chk_id, "Expense", 85.20, "Groceries", "Trader Joe's", (today - timedelta(days=1)).isoformat(), None),
        (crd_id, "Expense", 200.00, "Entertainment", "Concert Tickets", today.isoformat(), None)
    ]
    cur.executemany(
        """
        INSERT INTO Transactions (AccountId, TxnType, Amount, Category, Description, TxnDate, ToAccountId)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, txns
    )

    # 5. Insert Loans
    loans = [
        (user_id, "Borrow", "Alice", 500.00, 500.00, (today + timedelta(days=30)).isoformat(), "Active"),
        (user_id, "Lend", "Bob", 150.00, 150.00, (today + timedelta(days=14)).isoformat(), "Active")
    ]
    cur.executemany(
        """
        INSERT INTO Loans (UserId, LoanType, Counterparty, Amount, Remaining, DueDate, Status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, loans
    )

    conn.commit()

def main():
    reset_db(DB_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        create_schema(conn)
        seed_data(conn)
    print(f"Financial Assistant database created and seeded at: {DB_PATH}")

if __name__ == '__main__':
    main()
