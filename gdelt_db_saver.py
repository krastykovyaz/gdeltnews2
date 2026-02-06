import sqlite3
# from gdelt_parser import GdeltParser
from datetime import timedelta
from telegram_message import send_message
from telegram_poster import send_media_post_tg
from read_pages import process_url
from datetime import datetime
import config
import time


class GdeltDBSaver:
    def __init__(self, db_name="gdelt_data.db"):
        self.db_name = db_name
        self.conn = sqlite3.connect(db_name)
        self.c = self.conn.cursor()
        self.c.execute('PRAGMA journal_mode=WAL;')
        config.logging.info('Connected to the database: %s', db_name)
        self.create_table()
        self.create_filenames_table()

    # Create the table if it doesn't exist
    def create_table(self):
        self.c.execute('''
            CREATE TABLE IF NOT EXISTS gdelt_data (
                date TEXT, 
                link TEXT UNIQUE, 
                source TEXT, 
                en INTEGER, 
                filename TEXT, 
                is_posted TEXT, 
                record_time TEXT
            )
        ''')
        self.conn.commit()
        config.logging.info('Table gdelt_data created or already exists.')

    # Create a table for storing filenames if it doesn't exist
    def create_filenames_table(self):
        self.c.execute('''
            CREATE TABLE IF NOT EXISTS filenames (
                filename TEXT UNIQUE,
                url_filename TEXT, 
                record_time TEXT
            )
        ''')
        self.conn.commit()
        config.logging.info('Table filenames created or already exists.')

    # Check if the filenames already exist in the database
    def filename_exists(self, filename):
        self.c.execute('SELECT 1 FROM filenames WHERE filename = ?', (filename,))
        exists = self.c.fetchone() is not None
        config.logging.info('Checked filename %s, exists: %s', filename, exists)
        return exists

    def url_filename_exists(self, url_filename):
        self.c.execute('SELECT 1 FROM filenames WHERE url_filename = ?', (url_filename,))
        exists = self.c.fetchone() is not None
        config.logging.info('Checked url_filename %s, exists: %s', url_filename, exists)
        return exists

    # Check if the filenames already exist in the database
    def filenames_bucket_exists(self, filenames):
        filenames = tuple(filenames)
        self.c.execute(f"SELECT * FROM filenames WHERE filename in {filenames}")
        exists = self.c.fetchone() is not None
        config.logging.info('Checked filenames bucket %s, exists: %s', len(filenames), exists)
        return exists

    # Check if the link already exists in the database
    def link_exists(self, link):
        self.c.execute('SELECT 1 FROM gdelt_data WHERE link = ?', (link,))
        exists = self.c.fetchone() is not None
        config.logging.info('Checked link %s, exists: %s', link, exists)
        return exists

    # Save a new filename into the database
    def save_filename(self, url_filename, filename):
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.c.execute('INSERT INTO filenames (filename, url_filename, record_time) VALUES (?, ?, ?)', (filename, url_filename, current_time))
            self.conn.commit()
            config.logging.info('Saved url_filename: %s, filename: %s', url_filename, filename)
        except sqlite3.IntegrityError:
            config.logging.warning('Filename %s already exists, skipping.', filename)

    # Save data to SQLite with duplicate check
    def save_data(self, data_lines):
        for line in data_lines:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if not self.link_exists(line['link']):
                try:
                    self.c.execute('''
                        INSERT INTO gdelt_data (date, link, source, en, filename, is_posted, record_time)
                        VALUES (?, ?, ?, ?, ?, 'new', ?)
                    ''', (line['date'], line['link'], line['source'], line['en'], line['filename'], current_time))
                    self.conn.commit()
                    config.logging.info('Saved link: %s', line['link'])
                except sqlite3.IntegrityError:
                    config.logging.warning('Failed to insert %s due to IntegrityError (duplicate link).', line['link'])
            else:
                config.logging.info('Link %s already exists in the database, skipping.', line['link'])

    # Method to get one 'new' line from the database and update it to 'posted'
    def mark_as_posted(self):
        try:
            self.c.execute('SELECT rowid, * FROM gdelt_data WHERE is_posted = "new" LIMIT 1')
            row = self.c.fetchone()

            if row:
                rowid = row[0]  # Get the rowid (primary key)
                
                config.logging.info('Updating link %s to "posted"...', row[2])  # row[2] is the link
                self.c.execute('UPDATE gdelt_data SET is_posted = "posted" WHERE rowid = ?', (rowid,))
                self.conn.commit()
                for channel in config.TELEGRAM_CHANNELS:
                    # send_message(chat_id=channel, text=row[2])
                    procced_url = process_url(row[2])
                    send_media_post_tg(procced_url, channel)
                    time.sleep(1)
                return row
            else:
                config.logging.info("No 'new' records found.")
                return None
        except sqlite3.OperationalError as e:
            config.logging.error(f"SQLite error: {e}")
        finally:
            # Ensure that the connection is closed properly
            self.conn.close()

    def get_all_filenames(self):
        self.c.execute('SELECT filename FROM gdelt_data')
        filenames = self.c.fetchall()  # This will return a list of tuples
        config.logging.info('Retrieved all filenames from the database.')
        return set([filename[0] for filename in filenames])  # Extract the first element of each tuple

    def get_all_not_posted(self):
        self.c.execute("SELECT filename FROM gdelt_data WHERE is_posted = 'new'")
        new_posts = self.c.fetchall()  # This will return a list of tuples
        config.logging.info('Retrieved all new (not posted) entries from the database.')
        return new_posts  # Extract the first element of each tuple

    # Close the database connection
    def close(self):
        self.conn.close()
        config.logging.info('Closed the database connection.')

    def remove_old_records(self):
        try:
            # Calculate the datetime for one day ago
            one_day_ago = datetime.now() - timedelta(days=0)
            one_day_ago_str = one_day_ago.strftime('%Y-%m-%d %H:%M:%S')

            # Delete records older than one day
            self.c.execute('DELETE FROM gdelt_data WHERE record_time < ?', (one_day_ago_str,))
            self.conn.commit()
            config.logging.info('Deleted records older than one day.')
        except sqlite3.OperationalError as e:
            config.logging.error(f"SQLite error while deleting old records: {e}")
        finally:
            # Ensure the connection is not closed here as other methods might need it
            pass

if __name__ == '__main__':
    # Initialize database saver and perform operations
    db_saver = GdeltDBSaver()

    # You can place other operations here, such as saving data or marking posts

    # Close the database connection at the end
    db_saver.close()
