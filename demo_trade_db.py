import gspread
import pandas as pd
from datetime import datetime
from sheets_db import get_client
import bcrypt
import json

DEMO_SPREADSHEET_ID = "1X2gT0HT3iHLp512rq5b7ylCio9LGR0uyHPaGpGyEpas"
INITIAL_CASH = 1000000

def get_demo_spreadsheet():
    client = get_client()
    if not client:
        return None
    try:
        return client.open_by_key(DEMO_SPREADSHEET_ID)
    except Exception as e:
        print(f"Error opening demo spreadsheet: {e}")
        return None

def init_demo_db():
    sheet = get_demo_spreadsheet()
    if not sheet:
        return False
        
    try:
        # Check and create Users worksheet
        try:
            users_ws = sheet.worksheet("Users")
            # マイグレーション：ヘッダーチェックと列追加は省略
        except gspread.exceptions.WorksheetNotFound:
            users_ws = sheet.add_worksheet(title="Users", rows="100", cols="5")
            users_ws.insert_row(["Username", "Password_Hash", "Settings"], 1)

        # Check and create Portfolio worksheet
        try:
            portfolio_ws = sheet.worksheet("Portfolio")
            # 既存のものに "Username" がない可能性の対応はロジック側で吸収
        except gspread.exceptions.WorksheetNotFound:
            portfolio_ws = sheet.add_worksheet(title="Portfolio", rows="1000", cols="10")
            portfolio_ws.insert_row(["Username", "Ticker", "Company Name", "Average Price", "Quantity"], 1)

        # Check and create Transactions worksheet
        try:
            transactions_ws = sheet.worksheet("Transactions")
        except gspread.exceptions.WorksheetNotFound:
            transactions_ws = sheet.add_worksheet(title="Transactions", rows="5000", cols="10")
            transactions_ws.insert_row(["Username", "Timestamp", "Ticker", "Company Name", "Type", "Price", "Quantity", "Total Amount"], 1)

        # 管理者(mizukami)がいない場合は自動生成
        users_records = users_ws.get_all_records()
        df_users = pd.DataFrame(users_records)
        if df_users.empty or "Username" not in df_users.columns or "mizukami" not in df_users["Username"].values:
            hashed = hash_password("admin1234")
            default_settings = json.dumps({"theme": "dark", "role": "admin"})
            users_ws.append_row(["mizukami", hashed, default_settings])
            portfolio_ws.append_row(["mizukami", "CASH", "JPY Cash", 1.0, INITIAL_CASH])
            
            # 初回入金を取引履歴にも残す
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                transactions_ws = sheet.worksheet("Transactions")
                transactions_ws.append_row(["mizukami", now_str, "CASH", "Initial Deposit", "DEPOSIT", 1.0, INITIAL_CASH, INITIAL_CASH])
            except Exception as e:
                print(f"Error adding initial transaction: {e}")

        return True
    except Exception as e:
        print(f"Error initializing demo database: {e}")
        return False

# --- Auth Functions ---
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except:
        return False

def create_user(username, password):
    sheet = get_demo_spreadsheet()
    if not sheet:
        return False, "Database connection failed"
    try:
        users_ws = sheet.worksheet("Users")
        records = users_ws.get_all_records()
        df_users = pd.DataFrame(records)
        
        # ユーザーIDの重複チェック
        if not df_users.empty and "Username" in df_users.columns:
            if username in df_users["Username"].values:
                return False, "Username already exists"
                
        hashed = hash_password(password)
        default_settings = json.dumps({"theme": "dark", "default_model": "LightGBM"})
        users_ws.append_row([username, hashed, default_settings])
        
        # 新しいユーザーの初期資金(ポートフォリオ追加)
        portfolio_ws = sheet.worksheet("Portfolio")
        # ヘッダーが古い構造か確認
        headers = portfolio_ws.row_values(1)
        if "Username" not in headers:
            # マイグレーションとしてヘッダーと既存データを更新すべきだが、今回は追加の挙動に合わせるためシンプルに末尾に追加
            # 実運用では構造修正を走らせる
            pass
            
        portfolio_ws.append_row([username, "CASH", "JPY Cash", 1.0, INITIAL_CASH])
        
        # 初回入金を取引履歴にも残す
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            transactions_ws = sheet.worksheet("Transactions")
            transactions_ws.append_row([username, now_str, "CASH", "Initial Deposit", "DEPOSIT", 1.0, INITIAL_CASH, INITIAL_CASH])
        except Exception as e:
            print(f"Error adding initial tx: {e}")
            
        return True, "User created successfully"
    except Exception as e:
        return False, f"Error creating user: {str(e)}"

def verify_user(username, password):
    sheet = get_demo_spreadsheet()
    if not sheet:
        return False, "Database connection failed"
    try:
        users_ws = sheet.worksheet("Users")
        records = users_ws.get_all_records()
        df_users = pd.DataFrame(records)
        
        if df_users.empty or "Username" not in df_users.columns:
            return False, "No users found"
            
        user_row = df_users[df_users["Username"] == username]
        if user_row.empty:
            return False, "User not found"
            
        hashed = user_row["Password_Hash"].iloc[0]
        if check_password(password, hashed):
            return True, "Login successful"
        else:
            return False, "Incorrect password"
    except Exception as e:
        return False, f"Verification error: {str(e)}"

def get_all_users():
    sheet = get_demo_spreadsheet()
    if not sheet:
        return []
    try:
        users_ws = sheet.worksheet("Users")
        records = users_ws.get_all_records()
        df = pd.DataFrame(records)
        if not df.empty and "Username" in df.columns:
            return df["Username"].tolist()
        return []
    except:
        return []

def change_password(username, old_password, new_password, is_admin=False):
    sheet = get_demo_spreadsheet()
    if not sheet:
        return False, "Database connection failed"
    try:
        users_ws = sheet.worksheet("Users")
        records = users_ws.get_all_records()
        df_users = pd.DataFrame(records)
        if df_users.empty or "Username" not in df_users.columns:
            return False, "No users found"
        user_rows = df_users[df_users["Username"] == username]
        if user_rows.empty:
            return False, f"User {username} not found"
            
        row_idx = int(user_rows.index[0]) + 2
        
        # 一般ユーザーは旧パスワードの確認必須
        if not is_admin:
            hashed = user_rows["Password_Hash"].iloc[0]
            if not check_password(old_password, hashed):
                return False, "現在のパスワードが間違っています"
                
        # パスワード更新
        new_hashed = hash_password(new_password)
        # Headers check to find column index
        headers = users_ws.row_values(1)
        if "Password_Hash" in headers:
            col_idx = headers.index("Password_Hash") + 1
            users_ws.update_cell(row_idx, col_idx, new_hashed)
            return True, f"{username} のパスワードを更新しました"
        else:
            return False, "Database structure error"
    except Exception as e:
        return False, f"Password update error: {str(e)}"

def delete_user(target_username):
    # mizukami は消せない安全策
    if target_username == "mizukami":
        return False, "管理者(mizukami)は削除できません"
        
    sheet = get_demo_spreadsheet()
    if not sheet:
        return False, "Database connection failed"
    try:
        # Usersから削除 (下から検索して削除する)
        users_ws = sheet.worksheet("Users")
        users_df = pd.DataFrame(users_ws.get_all_records())
        if not users_df.empty and "Username" in users_df.columns:
            matches = users_df[users_df["Username"] == target_username]
            # 下から消すことでインデックスズレを防ぐ
            for idx in matches.index[::-1]:
                users_ws.delete_rows(int(idx) + 2)

        # Portfolioから削除
        port_ws = sheet.worksheet("Portfolio")
        port_df = pd.DataFrame(port_ws.get_all_records())
        if not port_df.empty and "Username" in port_df.columns:
            matches = port_df[port_df["Username"] == target_username]
            for idx in matches.index[::-1]:
                port_ws.delete_rows(int(idx) + 2)
                
        # Transactionsから削除
        tx_ws = sheet.worksheet("Transactions")
        tx_df = pd.DataFrame(tx_ws.get_all_records())
        if not tx_df.empty and "Username" in tx_df.columns:
            matches = tx_df[tx_df["Username"] == target_username]
            for idx in matches.index[::-1]:
                tx_ws.delete_rows(int(idx) + 2)

        return True, f"ユーザー {target_username} と関連データを完全に削除しました"
    except Exception as e:
        return False, f"Delete error: {str(e)}"

# --- Portfolio & Trading Functions ---
def get_portfolio(username):
    sheet = get_demo_spreadsheet()
    if not sheet:
        return pd.DataFrame()
        
    try:
        portfolio_ws = sheet.worksheet("Portfolio")
        records = portfolio_ws.get_all_records()
        df = pd.DataFrame(records)
        if df.empty:
            return df
            
        # マイグレーション互換
        if "Username" not in df.columns:
            df["Username"] = "guest"
            
        return df[df["Username"] == username].copy()
    except Exception as e:
        print(f"Error fetching portfolio: {e}")
        return pd.DataFrame()

def get_transactions(username):
    sheet = get_demo_spreadsheet()
    if not sheet:
        return pd.DataFrame()
        
    try:
        transactions_ws = sheet.worksheet("Transactions")
        records = transactions_ws.get_all_records()
        df = pd.DataFrame(records)
        if df.empty:
            return df
            
        if "Username" not in df.columns:
            df["Username"] = "guest"
            
        return df[df["Username"] == username].copy()
    except Exception as e:
        print(f"Error fetching transactions: {e}")
        return pd.DataFrame()

def _update_cash(portfolio_ws, df_portfolio, username, amount_change):
    # amt_change > 0 means add cash, < 0 means reduce cash
    if "Username" not in df_portfolio.columns:
        df_portfolio["Username"] = "guest"
        
    user_rows = df_portfolio[df_portfolio["Username"] == username]
    cash_rows = user_rows[user_rows["Ticker"] == "CASH"]
    
    if not cash_rows.empty:
        # df_portfolio のインデックス + 2 が行番号
        idx = int(cash_rows.index[0]) + 2
        current_cash = float(cash_rows["Quantity"].iloc[0])
        new_cash = current_cash + amount_change
        
        # どの列にアップデートするかはヘッダーから判定
        headers = portfolio_ws.row_values(1)
        if "Quantity" in headers:
            col_idx = headers.index("Quantity") + 1
            portfolio_ws.update_cell(idx, col_idx, new_cash)
        return new_cash
    return 0

def add_cash(username, amount):
    sheet = get_demo_spreadsheet()
    if not sheet:
        return False, "Database connection failed"
        
    try:
        portfolio_ws = sheet.worksheet("Portfolio")
        transactions_ws = sheet.worksheet("Transactions")
        df_portfolio = pd.DataFrame(portfolio_ws.get_all_records())
        
        if df_portfolio.empty or "Username" not in df_portfolio.columns:
            # Portfolio is empty or old structure
            portfolio_ws.append_row([username, "CASH", "JPY Cash", 1.0, amount])
        else:
            user_rows = df_portfolio[df_portfolio["Username"] == username]
            if user_rows.empty or "CASH" not in user_rows["Ticker"].values:
                # User has no CASH row
                portfolio_ws.append_row([username, "CASH", "JPY Cash", 1.0, amount])
            else:
                # Update existing CASH
                _update_cash(portfolio_ws, df_portfolio, username, amount)
                
        # Log Transaction
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tx_headers = transactions_ws.row_values(1)
        if "Username" in tx_headers:
            transactions_ws.append_row([username, now_str, "CASH", "Deposit", "DEPOSIT", 1.0, amount, amount])
        else:
            transactions_ws.append_row([now_str, "CASH", "Deposit", "DEPOSIT", 1.0, amount, amount])
            
        return True, f"¥{amount:,.0f} の資金を入金しました"
    except Exception as e:
        return False, f"入金エラー: {str(e)}"

def buy_stock(username, ticker, company_name, price, quantity):
    sheet = get_demo_spreadsheet()
    if not sheet:
        return False, "Database connection failed"
        
    try:
        portfolio_ws = sheet.worksheet("Portfolio")
        transactions_ws = sheet.worksheet("Transactions")
        df_portfolio = pd.DataFrame(portfolio_ws.get_all_records())
        
        if "Username" not in df_portfolio.columns:
            df_portfolio["Username"] = "guest"
            
        total_cost = price * quantity
        
        # Check cash balance
        user_rows = df_portfolio[df_portfolio["Username"] == username]
        cash = 0
        if not user_rows.empty and "CASH" in user_rows["Ticker"].values:
            cash = float(user_rows[user_rows["Ticker"] == "CASH"]["Quantity"].iloc[0])
            
        if cash < total_cost:
            return False, f"Insufficient cash (Required: {total_cost:,.0f}, Available: {cash:,.0f})"
            
        # Deduct cash
        _update_cash(portfolio_ws, df_portfolio, username, -total_cost)
        
        # Update Portfolio
        ticker_rows = user_rows[user_rows["Ticker"] == ticker]
        headers = portfolio_ws.row_values(1)
        col_price = headers.index("Average Price") + 1 if "Average Price" in headers else 4
        col_qty = headers.index("Quantity") + 1 if "Quantity" in headers else 5
        
        if not ticker_rows.empty:
            idx = int(ticker_rows.index[0]) + 2
            current_qty = int(ticker_rows["Quantity"].iloc[0])
            current_avg_price = float(ticker_rows["Average Price"].iloc[0])
            
            new_qty = current_qty + quantity
            new_avg_price = ((current_qty * current_avg_price) + total_cost) / new_qty
            
            portfolio_ws.update_cell(idx, col_price, new_avg_price)
            portfolio_ws.update_cell(idx, col_qty, new_qty)
        else:
            # 構造に合わせて追加
            if "Username" in headers:
                portfolio_ws.append_row([username, ticker, company_name, price, quantity])
            else:
                portfolio_ws.append_row([ticker, company_name, price, quantity]) # 互換用
            
        # Log Transaction
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tx_headers = transactions_ws.row_values(1)
        if "Username" in tx_headers:
            transactions_ws.append_row([username, now_str, ticker, company_name, "BUY", price, quantity, total_cost])
        else:
            transactions_ws.append_row([now_str, ticker, company_name, "BUY", price, quantity, total_cost])
        
        return True, "Success"
    except Exception as e:
        return False, f"Error: {str(e)}"

def sell_stock(username, ticker, company_name, price, quantity):
    sheet = get_demo_spreadsheet()
    if not sheet:
        return False, "Database connection failed"
        
    try:
        portfolio_ws = sheet.worksheet("Portfolio")
        transactions_ws = sheet.worksheet("Transactions")
        df_portfolio = pd.DataFrame(portfolio_ws.get_all_records())
        
        if "Username" not in df_portfolio.columns:
            df_portfolio["Username"] = "guest"
            
        user_rows = df_portfolio[df_portfolio["Username"] == username]
        
        # Check if user has enough stock
        if user_rows.empty or ticker not in user_rows["Ticker"].values:
            return False, f"You don't own any shares of {ticker}"
            
        ticker_rows = user_rows[user_rows["Ticker"] == ticker]
        current_qty = int(ticker_rows["Quantity"].iloc[0])
        if current_qty < quantity:
            return False, f"Insufficient shares (Owned: {current_qty}, Selling: {quantity})"
            
        idx = int(ticker_rows.index[0]) + 2
        total_revenue = price * quantity
        
        # Add cash
        _update_cash(portfolio_ws, df_portfolio, username, total_revenue)
        
        # Update Portfolio
        new_qty = current_qty - quantity
        headers = portfolio_ws.row_values(1)
        col_qty = headers.index("Quantity") + 1 if "Quantity" in headers else 5
        
        if new_qty == 0:
            portfolio_ws.delete_rows(idx)
        else:
            portfolio_ws.update_cell(idx, col_qty, new_qty)
        
        # Log Transaction
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tx_headers = transactions_ws.row_values(1)
        if "Username" in tx_headers:
            transactions_ws.append_row([username, now_str, ticker, company_name, "SELL", price, quantity, total_revenue])
        else:
            transactions_ws.append_row([now_str, ticker, company_name, "SELL", price, quantity, total_revenue])
        
        return True, "Success"
    except Exception as e:
        return False, f"Error: {str(e)}"
