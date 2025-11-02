Features

🔍 Scrapes book title, price, rating, and availability

⚡ Fast and lightweight using requests and BeautifulSoup

🧠 Handles missing or dynamic HTML data gracefully

💾 Can be extended to save output in CSV/Excel format

🖥️ Perfect for beginners exploring web scraping concepts

🧰 Tech Stack

Programming Language: Python

Libraries Used:

requests – To send HTTP requests

beautifulsoup4 – To parse and extract HTML data

🧩 Installation

Clone or Download the project folder.

Install the required Python libraries:

pip install requests beautifulsoup4


Open the Python file in any IDE (e.g., VS Code, PyCharm, Thonny).

🧠 How It Works

Enter or replace the Amazon book URL in the script:

url = "https://www.amazon.in/dp/B08N5WRWNW"


Run the program.

The script fetches and displays details like:

📚 Book Details Extracted from Amazon:
Title: The Psychology of Money
Price: ₹285
Rating: 4.6 out of 5 stars
Availability: In stock
