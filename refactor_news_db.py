from datetime import timedelta
from gdelt_db_saver import GdeltDBSaver

if __name__ == '__main__':
    db_saver = GdeltDBSaver()
    db_saver.remove_old_records()
    db_saver.close()