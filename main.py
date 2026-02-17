import time
from gdelt_parser import GdeltParser  # Assuming this is where your GdeltParser is defined
from gdelt_db_saver import GdeltDBSaver  # Assuming this is where your GdeltDBSaver is defined


def collect_and_update(delta_date_start=1, interval=60):
    # Instantiate the GdeltParser and GdeltDBSaver
    
    while True:
        
        print("Collecting new data...")
        # Collect data with GdeltParser
        db_saver = GdeltDBSaver()
        if len(db_saver.get_all_not_posted()) < 5:
            parser = GdeltParser(delta_date_start)
        # Fetch and update one record in the database
        print("Checking for 'new' records to update...")
        db_saver = GdeltDBSaver()
        updated_row = db_saver.mark_as_posted()
        db_saver.close()

        if updated_row:
            print(f"Updated entry: {updated_row}")
        else:
            print("No new entries to mark as 'posted'.")
        
        # Wait for the specified interval before the next run
        print(f"Sleeping for {interval} seconds...")
        time.sleep(interval)


if __name__ == "__main__":
    collect_and_update(delta_date_start=1, interval=60)  # Adjust delta_date_start and interval as needed
