import requests
from bs4 import BeautifulSoup
import pandas as pd
import tkinter as tk
from tkinter import messagebox, ttk
from threading import Thread

# ---------------- Web Scraping Function ---------------- #
def scrape_amazon(url, status_label):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.5"
    }

    products = []
    page = 1
    status_label.config(text="Scraping in progress... Please wait ⏳")
    
    while True:
        paged_url = f"{url}&page={page}"
        res = requests.get(paged_url, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # Find product containers
        results = soup.find_all("div", {"data-component-type": "s-search-result"})
        if not results:
            break
        
        for item in results:
            title = item.h2.text.strip() if item.h2 else "N/A"
            price = item.find("span", "a-price-whole")
            price = price.text.strip() if price else "N/A"
            rating = item.find("span", class_="a-icon-alt")
            rating = rating.text.strip() if rating else "N/A"
            availability = "In stock" if "Prime" in item.text else "Check on site"
            
            products.append({
                "Title": title,
                "Price": price,
                "Rating": rating,
                "Availability": availability
            })
        
        page += 1
        if page > 3:  # Limit to 3 pages for demo
            break

    # Save to Excel
    if products:
        df = pd.DataFrame(products)
        df.to_excel("amazon_products.xlsx", index=False)
        status_label.config(text=f"✅ Scraping complete! {len(products)} products saved to amazon_products.xlsx")
    else:
        status_label.config(text="❌ No data found. Please check the URL.")

# ---------------- Tkinter GUI ---------------- #
def start_scraping():
    url = url_entry.get()
    if not url:
        messagebox.showwarning("Input Required", "Please enter an Amazon URL.")
        return
    
    # Run scraping in a separate thread to prevent freezing
    Thread(target=scrape_amazon, args=(url, status_label)).start()

# GUI setup
root = tk.Tk()
root.title("Amazon Web Scraper")
root.geometry("600x400")
root.config(bg="#f4f4f4")

title_label = tk.Label(root, text="📦 Amazon Product Scraper", font=("Arial", 20, "bold"), bg="#f4f4f4", fg="#232f3e")
title_label.pack(pady=20)

url_label = tk.Label(root, text="Enter Amazon Product Search URL:", font=("Arial", 12), bg="#f4f4f4")
url_label.pack()

url_entry = tk.Entry(root, width=70, font=("Arial", 11))
url_entry.pack(pady=10)
url_entry.insert(0, "https://www.amazon.in/s?k=books")  # Default example

scrape_btn = tk.Button(root, text="Start Scraping", font=("Arial", 12, "bold"), bg="#ff9900", fg="white", command=start_scraping)
scrape_btn.pack(pady=20)

status_label = tk.Label(root, text="", font=("Arial", 11), bg="#f4f4f4", fg="green")
status_label.pack(pady=10)

footer = tk.Label(root, text="Developed by Vijay Kumar | Python Web Scraping Project", font=("Arial", 9), bg="#f4f4f4", fg="#555")
footer.pack(side="bottom", pady=10)

root.mainloop()
