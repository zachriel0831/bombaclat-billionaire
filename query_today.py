"""
Daily DB Analysis Script
Queries t_relay_events and t_x_posts for today's data from news_relay MySQL database.
"""
import sys
from datetime import date

# Load credentials from .env
DB_HOST = "127.0.0.1"
DB_PORT = 3306
DB_USER = "root"
DB_PASSWORD = "root"
DB_NAME = "news_relay"

try:
    import mysql.connector
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "mysql-connector-python", "--break-system-packages", "-q"])
    import mysql.connector

def connect():
    return mysql.connector.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, connection_timeout=10
    )

def query_relay_events(conn):
    cur = conn.cursor(dictionary=True)
    print("\n" + "="*60)
    print("TABLE: t_relay_events  (today's rows)")
    print("="*60)

    # Check table exists
    cur.execute("SHOW TABLES LIKE 't_relay_events'")
    if not cur.fetchone():
        print("  [!] Table t_relay_events does NOT exist.")
        return []

    # Total count
    cur.execute("SELECT COUNT(*) AS cnt FROM t_relay_events WHERE created_at >= CURDATE()")
    total = cur.fetchone()["cnt"]
    print(f"\n  Total rows today: {total}")

    if total == 0:
        print("  No data found for today.")
        return []

    # Breakdown by source
    cur.execute("""
        SELECT source, COUNT(*) AS cnt
        FROM t_relay_events
        WHERE created_at >= CURDATE()
        GROUP BY source
        ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    print("\n  Breakdown by source:")
    for r in rows:
        print(f"    {r['source']:40s}  {r['cnt']:5d}")

    # Latest 10 titles
    cur.execute("""
        SELECT id, source, title, created_at
        FROM t_relay_events
        WHERE created_at >= CURDATE()
        ORDER BY created_at DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    print("\n  Latest 10 titles:")
    all_rows = rows
    for r in rows:
        title = (r.get("title") or "")[:100]
        print(f"    [{r['created_at']}] ({r['source']}) {title}")

    # Fetch ALL for analysis
    cur.execute("""
        SELECT source, title, created_at
        FROM t_relay_events
        WHERE created_at >= CURDATE()
        ORDER BY created_at DESC
        LIMIT 300
    """)
    return cur.fetchall()

def query_x_posts(conn):
    cur = conn.cursor(dictionary=True)
    print("\n" + "="*60)
    print("TABLE: t_x_posts  (today's rows)")
    print("="*60)

    # Check table exists
    cur.execute("SHOW TABLES LIKE 't_x_posts'")
    if not cur.fetchone():
        print("  [!] Table t_x_posts does NOT exist.")
        return []

    # Discover columns
    cur.execute("DESCRIBE t_x_posts")
    cols = {r["Field"]: r for r in cur.fetchall()}
    print(f"\n  Columns: {list(cols.keys())}")

    # Detect handle/author column
    handle_col = None
    for candidate in ["author_handle", "handle", "username", "screen_name", "account", "author", "user_handle", "x_handle"]:
        if candidate in cols:
            handle_col = candidate
            break

    # Detect text column
    text_col = None
    for candidate in ["post_text", "text", "content", "tweet_text", "body", "message", "full_text"]:
        if candidate in cols:
            text_col = candidate
            break

    print(f"  Using handle_col={handle_col}, text_col={text_col}")

    # Total count
    cur.execute("SELECT COUNT(*) AS cnt FROM t_x_posts WHERE created_at >= CURDATE()")
    total = cur.fetchone()["cnt"]
    print(f"\n  Total rows today: {total}")

    if total == 0:
        print("  No data found for today.")
        return []

    # Breakdown by author/handle (if column found)
    if handle_col:
        cur.execute(f"""
            SELECT `{handle_col}`, COUNT(*) AS cnt
            FROM t_x_posts
            WHERE created_at >= CURDATE()
            GROUP BY `{handle_col}`
            ORDER BY cnt DESC
        """)
        rows = cur.fetchall()
        print(f"\n  Breakdown by {handle_col}:")
        for r in rows:
            handle = r.get(handle_col) or "(unknown)"
            print(f"    {str(handle):40s}  {r['cnt']:5d}")

    # Latest 10 posts
    select_cols = "id, created_at"
    if handle_col: select_cols += f", `{handle_col}`"
    if text_col:   select_cols += f", `{text_col}`"

    cur.execute(f"""
        SELECT {select_cols}
        FROM t_x_posts
        WHERE created_at >= CURDATE()
        ORDER BY created_at DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    print("\n  Latest 10 posts:")
    for r in rows:
        handle = str(r.get(handle_col, "(unknown)")) if handle_col else "(unknown)"
        text = (r.get(text_col) or "")[:120] if text_col else str(r)
        print(f"    [{r['created_at']}] @{handle}: {text}")

    # Fetch ALL for analysis
    cur.execute(f"""
        SELECT {select_cols}
        FROM t_x_posts
        WHERE created_at >= CURDATE()
        ORDER BY created_at DESC
        LIMIT 200
    """)
    return cur.fetchall()

def main():
    print(f"\n{'#'*60}")
    print(f"  Daily DB Analysis — {date.today()}")
    print(f"{'#'*60}")

    try:
        conn = connect()
        print(f"\n  Connected to MySQL: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    except Exception as e:
        print(f"\n  [ERROR] Cannot connect to MySQL: {e}")
        sys.exit(1)

    events = query_relay_events(conn)
    posts  = query_x_posts(conn)
    conn.close()

    # ---- Summary Analysis ----
    print("\n" + "="*60)
    print("ANALYSIS SUMMARY")
    print("="*60)

    # News themes
    news_titles = [r["title"] for r in events if r.get("title") and
                   not str(r.get("source","")).startswith("yfinance")]
    yfinance_titles = [r["title"] for r in events if
                       str(r.get("source","")).startswith("yfinance")]

    print(f"\n[News Events]  Total: {len(news_titles)}")
    if news_titles:
        for t in news_titles[:20]:
            print(f"  • {t[:110]}")

    print(f"\n[Market Data / yfinance]  Total: {len(yfinance_titles)}")
    if yfinance_titles:
        for t in yfinance_titles[:20]:
            print(f"  • {t[:110]}")

    print(f"\n[X Posts]  Total: {len(posts)}")
    if posts:
        for p in posts[:20]:
            # Try common handle/text keys
            handle = next((p[k] for k in ["author_handle","handle","username","screen_name","account","author","user_handle","x_handle"] if k in p), "(unknown)")
            text   = next((p[k] for k in ["post_text","text","content","tweet_text","body","message","full_text"] if k in p), str(p))
            text = (text or "")[:110]
            print(f"  @{handle}: {text}")

    print("\n" + "="*60)
    print("Done.")

if __name__ == "__main__":
    main()
