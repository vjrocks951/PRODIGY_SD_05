"""
safescraper_gui.py

Tkinter GUI scraper for BooksToScrape (demo site).
Features:
 - Multi-page scraping (pagination)
 - Extracts: Title, Price, Rating, Availability
 - Save to: CSV, Excel (.xlsx), SQLite, MySQL (optional)
 - Progress bar and status updates
"""

import threading
import time
import requests
from bs4 import BeautifulSoup
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import sqlite3
import os

# Optional MySQL import (only needed if user chooses MySQL)
try:
    import mysql.connector
    MYSQL_AVAILABLE = True
except Exception:
    MYSQL_AVAILABLE = False

# --------------- Scraping logic (BooksToScrape example) ---------------
def parse_rating(rating_class):
    # BooksToScrape stores rating in class name like "star-rating Three"
    mapping = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
    return mapping.get(rating_class, None)

def scrape_books_toscrape(start_url, max_pages=None, progress_callback=None, stop_flag=lambda: False):
    """
    Scrapes BooksToScrape starting from start_url.
    - max_pages: number of pages to follow (None -> follow until last)
    - progress_callback(current_page, total_pages_estimate) -> called to update UI
    - stop_flag() -> if returns True, stops early
    Returns: list of dicts with keys: Title, Price, Rating, Availability, Page, Link
    """
    results = []
    page_num = 1
    url = start_url.rstrip('/')
    # If user provided entry to catalog page, fine. BooksToScrape page pattern: page-#.html
    while True:
        if stop_flag():
            break

        # Determine page URL
        if page_num == 1:
            page_url = url
        else:
            # try common pagination form: replace 'index.html' or append 'page-X.html'
            if url.endswith("index.html"):
                base = url.rsplit('/', 1)[0]
                page_url = f"{base}/page-{page_num}.html"
            else:
                page_url = f"{url.rstrip('/')}/page-{page_num}.html"

        try:
            resp = requests.get(page_url, timeout=10)
            if resp.status_code == 404:
                # no more pages
                break
            resp.raise_for_status()
        except Exception as e:
            # stop on network error
            raise RuntimeError(f"Failed to fetch page {page_num} ({page_url}): {e}")

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract products
        products = soup.select("article.product_pod")
        if not products:
            # nothing found — likely done
            break

        for prod in products:
            title = prod.h3.a.get("title", "").strip()
            price_el = prod.select_one("p.price_color")
            price = price_el.text.strip() if price_el else ""
            rating_classes = prod.select_one("p.star-rating")
            rating = None
            if rating_classes:
                classes = rating_classes.get("class", [])
                # class example: ['star-rating', 'Three']
                if len(classes) > 1:
                    rating = parse_rating(classes[1])
            # availability not in product_pod on listing page; attempt to follow link to product page
            relative_link = prod.h3.a.get("href", "")
            # normalize link
            if relative_link.startswith("../"):
                # BooksToScrape uses ../.. links from categories
                product_link = requests.compat.urljoin(page_url, relative_link)
            else:
                product_link = requests.compat.urljoin(page_url, relative_link)

            # Try to fetch availability from product page (safer)
            availability = ""
            try:
                p_resp = requests.get(product_link, timeout=8)
                p_resp.raise_for_status()
                p_soup = BeautifulSoup(p_resp.text, "html.parser")
                avail_el = p_soup.select_one("p.availability")
                if avail_el:
                    availability = " ".join(avail_el.text.split())
            except:
                availability = ""  # keep blank if failure

            results.append({
                "Title": title,
                "Price": price,
                "Rating": rating,
                "Availability": availability,
                "Page": page_num,
                "Link": product_link
            })

        # update progress (we don't know total pages up front for BooksToScrape, so send page_num)
        if progress_callback:
            progress_callback(page_num, None)

        page_num += 1
        if max_pages and page_num > max_pages:
            break

    return results

# --------------- Storage helpers ---------------
def save_to_csv(df, filepath):
    df.to_csv(filepath, index=False, encoding="utf-8")
def save_to_excel(df, filepath):
    df.to_excel(filepath, index=False, engine="openpyxl")
def save_to_sqlite(df, filepath, table_name="products"):
    conn = sqlite3.connect(filepath)
    df.to_sql(table_name, conn, if_exists="replace", index=False)
    conn.close()

def save_to_mysql(df, host, port, user, password, database, table_name="products"):
    if not MYSQL_AVAILABLE:
        raise RuntimeError("mysql-connector-python not installed.")
    conn = mysql.connector.connect(host=host, port=port, user=user, password=password)
    cursor = conn.cursor()
    # create database if not exists
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database}`")
    conn.database = database
    # create table dynamically (simple)
    cols = df.columns
    # drop table if exists and create fresh
    cursor.execute(f"DROP TABLE IF EXISTS `{table_name}`")
    # construct create statement with TEXT columns for simplicity
    col_defs = ", ".join([f"`{c}` TEXT" for c in cols])
    create_sql = f"CREATE TABLE `{table_name}` ({col_defs})"
    cursor.execute(create_sql)
    # insert rows
    insert_sql = f"INSERT INTO `{table_name}` ({', '.join([f'`{c}`' for c in cols])}) VALUES ({', '.join(['%s']*len(cols))})"
    rows = [tuple(str(x) for x in r) for r in df.values.tolist()]
    cursor.executemany(insert_sql, rows)
    conn.commit()
    cursor.close()
    conn.close()

# --------------- GUI ---------------
class ScraperGUI:
    def __init__(self, root):
        self.root = root
        root.title("Web Scraper — Product Extractor (BooksToScrape demo)")
        root.geometry("720x520")
        root.resizable(False, False)

        self.stop_event = False
        self.results = []

        # Frame: Input
        frame_top = ttk.LabelFrame(root, text="Scrape Settings")
        frame_top.place(x=10, y=10, width=700, height=180)

        ttk.Label(frame_top, text="Start URL (BooksToScrape category/page):").place(x=10, y=10)
        self.url_var = tk.StringVar(value="http://books.toscrape.com/catalogue/category/books/science_22/index.html")
        ttk.Entry(frame_top, textvariable=self.url_var, width=86).place(x=10, y=35)

        ttk.Label(frame_top, text="Max Pages (leave blank to follow until end):").place(x=10, y=65)
        self.max_pages_var = tk.StringVar()
        ttk.Entry(frame_top, textvariable=self.max_pages_var, width=10).place(x=260, y=65)

        # Storage options
        ttk.Label(frame_top, text="Save As:").place(x=10, y=100)
        self.save_type = tk.StringVar(value="csv")
        ttk.Radiobutton(frame_top, text="CSV", variable=self.save_type, value="csv").place(x=70, y=100)
        ttk.Radiobutton(frame_top, text="Excel (.xlsx)", variable=self.save_type, value="excel").place(x=140, y=100)
        ttk.Radiobutton(frame_top, text="SQLite (.db)", variable=self.save_type, value="sqlite").place(x=260, y=100)
        ttk.Radiobutton(frame_top, text="MySQL", variable=self.save_type, value="mysql").place(x=350, y=100)

        # MySQL credential area (hidden unless chosen)
        self.mysql_frame = ttk.Frame(frame_top)
        self.mysql_frame.place(x=10, y=125)
        ttk.Label(self.mysql_frame, text="MySQL Host:").grid(row=0, column=0, sticky="w")
        self.mysql_host = tk.StringVar(value="localhost")
        ttk.Entry(self.mysql_frame, textvariable=self.mysql_host, width=12).grid(row=0, column=1, padx=5)
        ttk.Label(self.mysql_frame, text="Port:").grid(row=0, column=2, sticky="w")
        self.mysql_port = tk.StringVar(value="3306")
        ttk.Entry(self.mysql_frame, textvariable=self.mysql_port, width=6).grid(row=0, column=3, padx=5)
        ttk.Label(self.mysql_frame, text="User:").grid(row=0, column=4, sticky="w")
        self.mysql_user = tk.StringVar(value="root")
        ttk.Entry(self.mysql_frame, textvariable=self.mysql_user, width=10).grid(row=0, column=5, padx=5)
        ttk.Label(self.mysql_frame, text="Password:").grid(row=1, column=0, sticky="w")
        self.mysql_pass = tk.StringVar(value="")
        ttk.Entry(self.mysql_frame, textvariable=self.mysql_pass, width=12, show="*").grid(row=1, column=1, padx=5)
        ttk.Label(self.mysql_frame, text="Database:").grid(row=1, column=2, sticky="w")
        self.mysql_db = tk.StringVar(value="scraper_db")
        ttk.Entry(self.mysql_frame, textvariable=self.mysql_db, width=12).grid(row=1, column=3, padx=5)
        self.mysql_frame.place_forget()  # hide initially

        # Buttons
        ttk.Button(root, text="Start Scraping", command=self.start_scrape).place(x=10, y=200, width=140, height=35)
        ttk.Button(root, text="Stop", command=self.request_stop).place(x=160, y=200, width=80, height=35)
        ttk.Button(root, text="Save Results", command=self.save_results).place(x=250, y=200, width=120, height=35)
        ttk.Button(root, text="Open Folder", command=self.open_folder).place(x=380, y=200, width=100, height=35)
        ttk.Button(root, text="Clear Results", command=self.clear_results).place(x=490, y=200, width=120, height=35)

        # Progress and status
        self.progress = ttk.Progressbar(root, orient="horizontal", length=680, mode="determinate")
        self.progress.place(x=10, y=250)
        self.status_text = tk.StringVar(value="Idle")
        ttk.Label(root, textvariable=self.status_text).place(x=10, y=280)

        # Results table preview (simple)
        cols = ("Title", "Price", "Rating", "Availability", "Page")
        self.tree = ttk.Treeview(root, columns=cols, show="headings", height=10)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=130 if c=="Title" else 90, anchor="w")
        self.tree.place(x=10, y=310)

        # Bind save type change to show/hide mysql frame
        self.save_type.trace_add("write", self.on_save_type_change)

        # Internal
        self.output_folder = os.path.abspath(".")
        self.scrape_thread = None

    def on_save_type_change(self, *args):
        if self.save_type.get() == "mysql":
            self.mysql_frame.place(x=10, y=125)
        else:
            self.mysql_frame.place_forget()

    def request_stop(self):
        self.stop_event = True
        self.status_text.set("Stopping...")

    def start_scrape(self):
        if self.scrape_thread and self.scrape_thread.is_alive():
            messagebox.showinfo("Already running", "A scraping job is already in progress.")
            return
        start_url = self.url_var.get().strip()
        if not start_url:
            messagebox.showerror("Input error", "Please enter a start URL.")
            return
        max_pages = None
        if self.max_pages_var.get().strip().isdigit():
            max_pages = int(self.max_pages_var.get().strip())

        # reset state
        self.stop_event = False
        self.results = []
        self.tree.delete(*self.tree.get_children())
        self.progress["value"] = 0
        self.status_text.set("Starting...")

        # run in thread
        self.scrape_thread = threading.Thread(target=self._run_scrape,
                                              args=(start_url, max_pages),
                                              daemon=True)
        self.scrape_thread.start()

    def _run_scrape(self, start_url, max_pages):
        try:
            def progress_cb(current_page, _):
                # This callback runs in worker thread — use after() to update UI
                self.root.after(0, lambda: self.status_text.set(f"Scraped pages: {current_page}"))
                # increase progress in small increments
                self.root.after(0, lambda: self.progress.step(10))

            self.root.after(0, lambda: self.status_text.set("Scraping in progress..."))
            data = scrape_books_toscrape(start_url, max_pages=max_pages,
                                         progress_callback=progress_cb,
                                         stop_flag=lambda: self.stop_event)
            self.results = data
            # populate treeview (in main thread)
            self.root.after(0, self._populate_preview)
            self.root.after(0, lambda: self.status_text.set(f"Scraping finished. {len(data)} items found."))
            self.root.after(0, lambda: self.progress.config(value=100))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Scraping failed: {e}"))
            self.root.after(0, lambda: self.status_text.set("Error during scraping"))

    def _populate_preview(self):
        self.tree.delete(*self.tree.get_children())
        for item in self.results[:200]:  # show first 200 items for preview
            self.tree.insert("", "end", values=(item["Title"][:60], item["Price"], item["Rating"], item["Availability"][:30], item["Page"]))

    def save_results(self):
        if not self.results:
            messagebox.showinfo("No data", "No results to save. Run a scrape first.")
            return
        df = pd.DataFrame(self.results)
        stype = self.save_type.get()
        try:
            if stype == "csv":
                filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files","*.csv")])
                if not filepath: return
                save_to_csv(df, filepath)
                messagebox.showinfo("Saved", f"Saved CSV to:\n{filepath}")
            elif stype == "excel":
                filepath = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files","*.xlsx")])
                if not filepath: return
                save_to_excel(df, filepath)
                messagebox.showinfo("Saved", f"Saved Excel to:\n{filepath}")
            elif stype == "sqlite":
                filepath = filedialog.asksaveasfilename(defaultextension=".db", filetypes=[("SQLite DB","*.db")])
                if not filepath: return
                save_to_sqlite(df, filepath)
                messagebox.showinfo("Saved", f"Saved SQLite DB to:\n{filepath}")
            elif stype == "mysql":
                if not MYSQL_AVAILABLE:
                    messagebox.showerror("MySQL unavailable", "mysql-connector-python not installed.")
                    return
                # get credentials
                host = self.mysql_host.get().strip()
                port = int(self.mysql_port.get().strip() or 3306)
                user = self.mysql_user.get().strip()
                password = self.mysql_pass.get()
                database = self.mysql_db.get().strip() or "scraper_db"
                # perform save
                save_to_mysql(df, host, port, user, password, database)
                messagebox.showinfo("Saved", f"Saved to MySQL database `{database}` on {host}:{port}")
            else:
                messagebox.showerror("Unknown", "Unknown save type.")
        except Exception as e:
            messagebox.showerror("Save error", f"Failed to save: {e}")

    def open_folder(self):
        # open current directory in file explorer
        try:
            path = os.path.abspath(".")
            if os.name == 'nt':
                os.startfile(path)
            elif os.name == 'posix':
                os.system(f'xdg-open "{path}"')
        except Exception:
            messagebox.showinfo("Open folder", f"Folder: {os.path.abspath('.')}")

    def clear_results(self):
        self.results = []
        self.tree.delete(*self.tree.get_children())
        self.status_text.set("Cleared results")
        self.progress["value"] = 0

# --------------- Run ---------------
if __name__ == "__main__":
    root = tk.Tk()
    app = ScraperGUI(root)
    root.mainloop()
