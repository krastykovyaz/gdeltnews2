import requests
import json
import config

def send_message(chat_id: int,
                 text: str,
                 parse_mode: str = None,
                 buttons: list or None = None,
                 inline_keyboard: list or None = None,
                 one_time_keyboard: bool = True,
                 resize_keyboard: bool = True,
                 remove_keyboard: bool = False,):
    payload = {
        "chat_id": chat_id,
        "text": text[:4095],
        "reply_markup": {
            "remove_keyboard": remove_keyboard
        }
    }

    if parse_mode:
        payload.update({"parse_mode": parse_mode})

    if buttons:
        # TODO hardcode
        keyboards = [[{"text": text}] for text in buttons]
        payload["reply_markup"].update({
            "keyboard": keyboards,
            "resize_keyboard": resize_keyboard,
            "one_time_keyboard": one_time_keyboard
        })

    if inline_keyboard:
        payload["reply_markup"].update({"inline_keyboard": inline_keyboard})

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.get("https://api.telegram.org/bot{}/sendMessage".format(config.TELEGRAM_TOKEN), headers=headers, data=json.dumps(payload))

    response = response.json()

    res = response.get("ok")
    print(response)

    # маскирование текста
    payload["text"] = "*******"


if __name__=='__main__':
    
    send_message(
            chat_id=config.TELEGRAM_CHANNELS[2],
        text='toto') 
