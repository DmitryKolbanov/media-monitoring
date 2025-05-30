from typing import List, Dict, Union
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
import time
import requests

SCROLL_PAUSE_TIME = 0.5
PARSE_INTERVAL = 5  # Парсим каждые 5 скроллов

# Инициализация
months = {
    'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04',
    'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08',
    'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12'
}

today = datetime.today()
yesterday = today - timedelta(days=1)

DATE_RANGE = ["2025-04-15", "2025-05-06"]
class RIAParser:
    def __init__(self, url, driver, date_range, pattern=None, headers = None):
        self.url = url
        self.driver = driver
        self.headers = headers
        self.TIMEOUT = 0.1
        self.date_start, self.date_end = date_range
        self.source_name = "РИА новости"
        self.window = None

        self.pattern_key_words = None

        if pattern:
            self.pattern_key_words = pattern
        print(self.pattern_key_words)
        self.news: List[Dict] = []
        # self.processed_urls = set()
        self.session = requests.Session()  # Используем сессию для повторных запросов
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def __parse_date(self, date_str: str) -> Union[datetime.date, None]:
        """Парсит дату из различных форматов"""
        date_str = date_str.strip()

        if re.match(r'^\d{2}:\d{2}$', date_str):
            return today.date(), date_str

        try:
            if date_str.startswith('Вчера'):
                return yesterday.date(), date_str.split(",")[1].strip()

            if ',' in date_str:
                date_part, time_part = date_str.split(',', 1)
                date_part = date_part.strip()

                if ' ' in date_part:
                    day, month_name = date_part.split()
                    if month_name in months:
                        month = months[month_name]
                        year = today.year
                        return datetime.strptime(f'{day}-{month}-{year}', '%d-%m-%Y').date(), date_str.split(",")[1].strip()

        except Exception as e:
            print(f"Ошибка парсинга даты: {date_str} - {e}")
        return None

    def __extract_news_items(self, html: str, flag_parse_all = False) -> List[Dict]:
        if flag_parse_all:
            processed_urls = set() # МНОЖЕСТВО ++++++++++++++++++++++++++++++++++++
        else:
            processed_urls = None
        # Скользящее окно по html
        if not flag_parse_all and self.window is not None:
            html_len = len(html)
            html = html[self.window:]
            self.window = html_len

        if self.window is None:
            self.window = len(html)
        """Извлекает новости из HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        items = soup.find_all('div', class_='list-item')
        extracted = []

        for item in items:
            date_div = item.find('div', {'data-type': 'date'})
            links = item.find_all('a')

            if not date_div or len(links) < 2:
                continue

            url = links[1].get('href')
            if flag_parse_all and type(processed_urls) is set and url in processed_urls:
                continue

            date_str = date_div.text.strip()

            article_date, time_hour_min = self.__parse_date(date_str)

            if article_date < self.date_start:
                return extracted, False  # Прекращаем обработку, если дата слишком ранняя

            if article_date > self.date_end:
                continue

            title = links[1].text.strip()
            if not title:
                meta_title = item.find('meta', itemprop='name')
                if meta_title:
                    title = meta_title.get('content', '').strip()

            if not title:
                title = links[0].text.strip()

            if self.pattern_key_words:
                if not re.search(self.pattern_key_words, title.lower()):
                    continue

            extracted.append({
                "url": url,
                "title": title,
                "date_publication": str(article_date.strftime('%Y-%m-%d')),
                "content": None,
                "source": self.source_name
            })
            if flag_parse_all:
                processed_urls.add(url)


        return extracted, True  # while продолжает работать

    def __scroll_and_load(self):
        """Выполняет скроллинг и загрузку контента"""
        scroll_count = 0
        continue_loading = True

        while continue_loading:
            element = None
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, "div.list-more.color-btn-second-hover")
            except:
                pass

            if element:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});",
                                           element)
                self.driver.execute_script("arguments[0].click();", element)
            else:
                self.driver.execute_script("window.scrollBy({top: 1500, left: 0, behavior: 'smooth'});")

            scroll_count += 1
            time.sleep(SCROLL_PAUSE_TIME)

            if scroll_count % PARSE_INTERVAL == 0:
                _, continue_loading = self.__extract_news_items(self.driver.page_source)

        new_items, _ = self.__extract_news_items(self.driver.page_source, True)
        self.news.extend(new_items)



    def __run(self):
        """Основной метод запуска парсера"""
        self.driver.get(self.url)
        self.__scroll_and_load()
        return self.news


    def __parse_news_page(self, url: str) -> tuple:
        """Парсинг полного текста новости через requests и BeautifulSoup"""
        try:
            response = self.session.get(url, headers=self.headers)
            response.raise_for_status()  # Проверяем успешность запроса
            soup = BeautifulSoup(response.text, 'html.parser')

            # Извлекаем заголовок
            title_elem = soup.find('div', class_='article__title')
            title = title_elem.text.strip() if title_elem else ""

            # Извлекаем основной текст
            text_blocks = soup.find_all('div', class_='article__text')
            content = '\n'.join([p.text.strip() for p in text_blocks if p.text.strip()])

            return title, content

        except Exception as e:
            return None, None

    def news_page(self): # public
        news_urls = self.__run()
        for item in news_urls:
            try:
                title, content = self.__parse_news_page(item['url'])
                item['content'] = content
            except Exception as e:
                print(f"{e}")
        return self.news

# if __name__ == "__main__":
#     url = "https://ria.ru/economy/"
#     driver = webdriver.Chrome()
#     date_start = datetime.strptime(
#         DATE_RANGE[0].strip(), "%Y-%m-%d").date()
#     date_end = datetime.strptime(
#         DATE_RANGE[1].strip(), "%Y-%m-%d").date()
#     parser = RIAParser(url=url, date_range = (date_start, date_end), driver=driver)
#     result = parser.run()
#     print(f"Найдено новостей: {len(result)}")
#     for item in result:  # Выводим первые 5 для примера
#         print(item)