from gdelt_db_saver import GdeltDBSaver

def bynary_find(urls, db_data):
    mid = len(urls) // 2
    if len(urls) == 1 or len(urls) == 0:
        return urls
    if db_data.filenames_bucket_exists(urls[mid:]) == True \
        and db_data.filenames_bucket_exists(urls[:mid]) == False:
        return bynary_find(urls[mid:], db_data)
    elif db_data.filenames_bucket_exists(urls[:mid]) == True \
        and db_data.filenames_bucket_exists(urls[mid:]) == False:
        return bynary_find(urls[:mid:], db_data)
    else:
        return urls


if __name__=='__main__':
    # import numpy as np

    # db = np.random.randint(900_000,1000_000, 10000)
    # # print(db)
    # collector_files = list(range(500_000,1000_000))
    # print(len(collector_files))

    # def if_exist(urls):
    #     return any(list(set(db) & set(urls)))

    # print(bynary_find(collector_files))
    examples = ['20240921094500.translation.gkg.csv']
    db_data = GdeltDBSaver()
    # print(db_data.filenames_bucket_exists(examples))
    print(bynary_find(examples, db_data))


    
