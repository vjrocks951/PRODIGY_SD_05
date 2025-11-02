"""
safescraper_gui_v2.py
Enhanced version:
 - Accepts single product URLs OR category pages
 - Detects automatically based on URL
 - Extracts: Title, Price, Rating, Availability, Link
 - Multi-page scraping for category pages
 - Save to CSV / Excel / SQLite / MySQL
"""

import threading
import requests
from bs4 import BeautifulSoup
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import sqlite3
import os

try:
    import mysql.connector
    MYSQL_AVAILABLE = True
except:
    MYSQL_AVAILABLE = False


def parse_rating(rating_class):
    mapping = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
    return mapping.get(rating_class, None)


def scrape_single_book(url):
    """Scrape details of a single book page."""
    data = []
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    title = soup.select_one(".product_main h1").text.strip()
    price = soup.select_one(".price_color").text.strip()
    rating_el = soup.select_one("p.star-rating")
    rating = None
    if rating_el:
        classes = rating_el.get("class", [])
        if len(classes) > 1:
            rating = parse_rating(classes[1])
    availability = soup.select_one("p.availability")
    availability = " ".join(availability.text.split()) if availability else ""
    data.append({
        "Title": title,
        "Price": price,
        "Rating": rating,
        "Availability": availability,
        "Page": 4,
        "Link": url
    })
    return data


def scrape_category(url, max_pages=None, progress_callback=None):
    """Scrape multiple pages of a category."""
    results = []
    page_num = 1
    while True:
        if page_num == 1:
            page_url = url
        else:
            if url.endswith("index.html"):
                base = url.rsplit("/", 1)[0]
                page_url = f"{base}/page-{page_num}.html"
            else:
                page_url = f"{url.rstrip('/')}/page-{page_num}.html"

        resp = requests.get(page_url, timeout=10)
        if resp.status_code == 404:
            break
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        products = soup.select("article.product_pod")
        if not products:
            break

        for prod in products:
            title = prod.h3.a.get("title", "").strip()
            price = prod.select_one("p.price_color").text.strip()
            rating_classes = prod.select_one("p.star-rating")
            rating = None
            if rating_classes:
                classes = rating_classes.get("class", [])
                if len(classes) > 1:
                    rating = parse_rating(classes[1])

            relative_link = prod.h3.a.get("href", "")
            product_link = requests.compat.urljoin(page_url, relative_link)

            # Get availability
            try:
                p_resp = requests.get(product_link, timeout=8)
                p_resp.raise_for_status()
                p_soup = BeautifulSoup(p_resp.text, "html.parser")
                avail_el = p_soup.select_one("p.availability")
                availability = " ".join(avail_el.text.split()) if avail_el else ""
            except:
                availability = ""

            results.append({
                "Title": title,
                "Price": price,
                "Rating": rating,
                "Availability": availability,
                "Page": page_num,
                "Link": product_link
            })

        if progress_callback:
            progress_callback(page_num)
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
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database}`")
    conn.database = database
    cursor.execute(f"DROP TABLE IF EXISTS `{table_name}`")
    cols = df.columns
    col_defs = ", ".join([f"`{c}` TEXT" for c in cols])
    cursor.execute(f"CREATE TABLE `{table_name}` ({col_defs})")
    insert_sql = f"INSERT INTO `{table_name}` ({', '.join(cols)}) VALUES ({', '.join(['%s']*len(cols))})"
    cursor.executemany(insert_sql, [tuple(str(x) for x in r) for r in df.values.tolist()])
    conn.commit()
    cursor.close()
    conn.close()


# --------------- GUI ---------------
class ScraperGUI:
    def __init__(self, root):
        self.root = root
        root.title("📘 Web Scraper — Book Info Extractor")
        root.geometry("720x520")
        root.resizable(False, False)

        self.results = []

        frame_top = ttk.LabelFrame(root, text="Scraping Settings")
        frame_top.place(x=10, y=10, width=700, height=180)

        ttk.Label(frame_top, text="Enter Book or Category URL:").place(x=10, y=10)
        self.url_var = tk.StringVar(value="http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html")
        ttk.Entry(frame_top, textvariable=self.url_var, width=86).place(x=10, y=35)

        ttk.Label(frame_top, text="Max Pages (category only):").place(x=10, y=70)
        self.max_pages_var = tk.StringVar()
        ttk.Entry(frame_top, textvariable=self.max_pages_var, width=10).place(x=180, y=70)

        ttk.Label(frame_top, text="Save As:").place(x=10, y=100)
        self.save_type = tk.StringVar(value="csv")
        ttk.Radiobutton(frame_top, text="CSV", variable=self.save_type, value="csv").place(x=70, y=100)
        ttk.Radiobutton(frame_top, text="Excel", variable=self.save_type, value="excel").place(x=130, y=100)
        ttk.Radiobutton(frame_top, text="SQLite", variable=self.save_type, value="sqlite").place(x=200, y=100)
        ttk.Radiobutton(frame_top, text="MySQL", variable=self.save_type, value="mysql").place(x=270, y=100)

        ttk.Button(root, text="Start", command=self.start_scrape).place(x=10, y=200, width=120, height=35)
        ttk.Button(root, text="Save", command=self.save_results).place(x=140, y=200, width=100, height=35)
        ttk.Button(root, text="Clear", command=self.clear_results).place(x=250, y=200, width=100, height=35)

        self.progress = ttk.Progressbar(root, orient="horizontal", length=680, mode="determinate")
        self.progress.place(x=10, y=250)
        self.status_text = tk.StringVar(value="Idle")
        ttk.Label(root, textvariable=self.status_text).place(x=10, y=280)

        cols = ("Title", "Price", "Rating", "Availability", "Page")
        self.tree = ttk.Treeview(root, columns=cols, show="headings", height=10)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=130 if c == "Title" else 90)
        self.tree.place(x=10, y=310)

    def start_scrape(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a URL")
            return
        self.results = []
        self.tree.delete(*self.tree.get_children())
        self.status_text.set("Scraping started...")
        self.progress["value"] = 0

        threading.Thread(target=self._scrape_thread, args=(url,), daemon=True).start()

    def _scrape_thread(self, url):
        try:
            if "catalogue/" in url and url.endswith(".html"):
                # Single book
                data = scrape_single_book(url)
            else:
                maxp = int(self.max_pages_var.get()) if self.max_pages_var.get().isdigit() else None
                data = scrape_category(url, maxp, progress_callback=lambda p: self.root.after(0, lambda: self.progress.step(10)))

            self.results = data
            self.root.after(0, self._show_results)
            self.root.after(0, lambda: self.status_text.set(f"Done. {len(data)} items found."))
            self.root.after(0, lambda: self.progress.config(value=100))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Scraping failed: {e}"))
            self.root.after(0, lambda: self.status_text.set("Error occurred."))

    def _show_results(self):
        for item in self.results:
            self.tree.insert("", "end", values=(item["Title"], item["Price"], item["Rating"], item["Availability"], item["Page"]))

    def save_results(self):
        if not self.results:
            messagebox.showinfo("No data", "Run the scraper first.")
            return
        df = pd.DataFrame(self.results)
        stype = self.save_type.get()
        try:
            if stype == "csv":
                fp = filedialog.asksaveasfilename(defaultextension=".csv")
                if fp:
                    save_to_csv(df, fp)
            elif stype == "excel":
                fp = filedialog.asksaveasfilename(defaultextension=".xlsx")
                if fp:
                    save_to_excel(df, fp)
            elif stype == "sqlite":
                fp = filedialog.asksaveasfilename(defaultextension=".db")
                if fp:
                    save_to_sqlite(df, fp)
            elif stype == "mysql":
                messagebox.showinfo("MySQL", "Add credentials logic if needed.")
            messagebox.showinfo("Success", f"Saved successfully as {stype.upper()}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def clear_results(self):
        self.results = []
        self.tree.delete(*self.tree.get_children())
        self.status_text.set("Cleared.")
        self.progress["value"] = 0


if __name__ == "__main__":
    root = tk.Tk()
    app = ScraperGUI(root)
    root.mainloop()
