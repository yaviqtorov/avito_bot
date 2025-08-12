from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup
import os

def check_new_ads(url: str):
    results = []

    options = Options()
    # options.add_argument("--headless")  # ← пока убрал, чтобы видеть браузер
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    # Подменяем User-Agent на обычный Chrome
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/115.0.0.0 Safari/537.36")

    driver_path = os.path.join(os.getcwd(), "chromedriver.exe")
    service = Service(driver_path)

    try:
        driver = webdriver.Chrome(service=service, options=options)
    except WebDriverException as e:
        print(f"Ошибка запуска браузера: {e}")
        return []

    try:
        driver.set_page_load_timeout(20)
        driver.get(url)

        # Ждём появления хотя бы одного объявления
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-marker="item"]'))
        )

        soup = BeautifulSoup(driver.page_source, "lxml")
        ads = soup.find_all("div", {"data-marker": "item"})

        for ad in ads[:5]:
            title_tag = ad.find("h3") or ad.find("span")
            title = title_tag.get_text(strip=True) if title_tag else "Без названия"

            price_tag = ad.find("meta", {"itemprop": "price"})
            price = price_tag.get("content") + " ₽" if price_tag else "Не указана"

            link_tag = ad.find("a", {"data-marker": "item-title"})
            if link_tag:
                link = "https://www.avito.ru" + link_tag.get("href")
            else:
                link = "Ссылка не найдена"

            results.append({"title": title, "price": price, "url": link})

    except TimeoutException:
        print("⏳ Объявления не загрузились за отведённое время.")
    except Exception as e:
        print(f"Ошибка при обработке {url}: {e}")
    finally:
        driver.quit()

    return results
