import os
import requests
from tqdm import tqdm
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from io import BytesIO
from zipfile import ZipFile
import config
from gdelt_db_saver import GdeltDBSaver
from find_news_in_db import bynary_find

class GdeltParser:
    def __init__(self, delta_date_start):
        
        self.urls = config.gdelt_urls
        self.year = config.YEAR
        self.most_sources = config.most_sources
        self.delta_date_start = delta_date_start
        config.logging.info('Initialized GdeltParser with delta_date_start: %s', self.delta_date_start)
        self.collector = self.parse_gdelt_lines()  # Collect the list of URLs
        self.lines = self.process_zip_files_sequentially(self.collector[::-1])  # Process all the ZIP files sequentially
        self.remove_duplicates()

    # Функция для скачивания файла
    @staticmethod
    def file_downloader(url_of_file_to_download, file_name):
        try:
            config.logging.info('Downloading file from URL: %s', url_of_file_to_download)
            response = requests.get(url_of_file_to_download, timeout=5)
            response.raise_for_status()  # Raise an HTTPError for bad requests
            with open(file_name, 'wb') as f:
                f.write(response.content)
            config.logging.info('Downloaded file: %s', file_name)
            return response.text
        except requests.RequestException as e:
            config.logging.error('Error downloading %s: %s', url_of_file_to_download, e)
            return None

    # Функция для рефакторинга времени
    @staticmethod
    def refactor_time(dtime):
        try:
            date_part = dtime[:14]
            dt = datetime.strptime(date_part, "%Y%m%d%H%M%S")
            return dt
        except:
            config.logging.warning('Could not refactor time for: %s', dtime)
            return np.NaN

    # Парсинг строки
    @staticmethod
    def parse_line(ln, bucket, bucket_date):
        news_line = {}
        for item in ln.split('\t'):
            if 'http' in item and 'link' not in news_line:
                news_line['link'] = item
                news_line['source'] = news_line['link'].split('/')[2]
            elif len(item) == 14 and item.isdigit():  # 14 digits is date
                news_line['date'] = bucket_date
        if 'source' not in news_line:
            config.logging.info('No source found in line: %s', ln)
            return None
        ln_lower = ln.lower() 
        if not any(k in ln_lower for k in config.KEYWORDS):
            config.logging.info('No Key words in line: %s', ln)
            return None
        news_line['en'] = True if ('.com' in news_line['source'] or '.uk' in news_line['source']) else False
        news_line['filename'] = bucket
        return news_line

    # Обработка ZIP файлов
    def process_zip_file(self, urls):
        news_lines = []
        try:
            db_saver = GdeltDBSaver()
            if any(urls):
                start_url = urls[0]
                urls = [url for url in urls if not db_saver.url_filename_exists(url)]
                urls.append(start_url)
                i = 0
                for url in tqdm(urls, desc="Processing files"):
                    config.logging.info('Processing ZIP file from URL: %s', url)
                    response = requests.get(url, timeout=10)
                    response.raise_for_status()

                    with ZipFile(BytesIO(response.content)) as z:
                        filenames = bynary_find(z.namelist(), db_saver)
                        for filename in filenames:
                            if not db_saver.filename_exists(filename):
                                all_lines = []
                                
                                # Проверяем временной интервал, чтобы обрабатывать только актуальные файлы
                                date_time = self.refactor_time(filename.split('.')[0])
                                if date_time > datetime.now() - timedelta(self.delta_date_start):
                                    config.logging.info('Processing file: %s with date: %s', filename, date_time)
                                    with z.open(filename) as f:
                                        for line in f:
                                            try:
                                                line = line.decode('utf-8').strip()
                                            except UnicodeDecodeError:
                                                line = line.decode('latin-1').strip()

                                            parsed_line = self.parse_line(line, filename, date_time)
                                            if parsed_line is not None and parsed_line['source'] in set(self.most_sources):
                                                all_lines.append(parsed_line)

                                if all_lines:
                                    config.logging.info('Saving data for file: %s', filename)
                                    db_saver.save_data(all_lines)
                                    news_lines.extend(all_lines)

                            db_saver.save_filename(url, filename)  # Save filename after processing
                            config.logging.info('Saved filename: %s', filename)
                    
                    if i % 1_000 == 0:
                        db_saver = GdeltDBSaver()
                        unposted_count = len(db_saver.get_all_not_posted())
                        config.logging.info('Unposted entries count: %d', unposted_count)
                        if unposted_count > 5:
                            config.logging.info('Breaking the loop as unposted entries exceeded 5.')
                            return news_lines
                    i += 1

        except requests.RequestException as e:
            config.logging.error('Failed to download or process %s: %s', url, e)

        return news_lines

    # Sequential processing of ZIP files
    def process_zip_files_sequentially(self, urls):
        all_lines = self.process_zip_file(urls)
        return all_lines

    def parse_gdelt_lines(self):
        collector = []
        # Скачиваем файлы masterfilelist и ищем актуальные zip-файлы
        for url, file_name in self.urls:
            file_content = self.file_downloader(url, file_name)
            if file_content:
                config.logging.info('Processing masterfile: %s', file_name)
                with open(file_name, 'r') as f:
                    lines = f.readlines()
                for line in tqdm(lines, desc=f"Collecting files from {url}"):
                    if self.year in line:
                        file_to_upload = line.strip().split(' ')[-1]
                        collector.append(file_to_upload)
                        config.logging.info('File to upload: %s', file_to_upload)
        return collector

    def remove_duplicates(self):
        unique_lines = {}
        for line in self.lines:
            if line['link'] not in unique_lines:
                unique_lines[line['link']] = line
        config.logging.info('Removed duplicates, final line count: %d', len(unique_lines))
        self.lines = list(unique_lines.values())


if __name__ == '__main__':
    db_saver = GdeltDBSaver()
    config.logging.info('Starting GDELT parser...')
    gp = GdeltParser(7, db_saver)

    df = pd.DataFrame([line for line in gp.lines])
    config.logging.info('Parsed data frame head: \n%s', df.head())
    print(df.head())
