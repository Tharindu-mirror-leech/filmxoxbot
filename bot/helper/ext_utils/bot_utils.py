from re import findall as re_findall
from threading import Thread, Event
from time import time
from math import ceil
from html import escape
from psutil import virtual_memory, cpu_percent, disk_usage
from requests import head as rhead
from urllib.request import urlopen

from bot import download_dict, download_dict_lock, STATUS_LIMIT, botStartTime, DOWNLOAD_DIR, WEB_PINCODE, BASE_URL
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker

MAGNET_REGEX = r"magnet:\?xt=urn:btih:[a-zA-Z0-9]*"

URL_REGEX = r"(?:(?:https?|ftp):\/\/)?[\w/\-?=%.]+\.[\w/\-?=%.]+"

COUNT = 0
PAGE_NO = 1


class MirrorStatus:
    STATUS_UPLOADING = "📂𝕌𝕡𝕝𝕠𝕒𝕕🔺🔺....."
    STATUS_DOWNLOADING = "📂𝔻𝕠𝕨𝕟𝕝𝕠𝕒𝕕🔻🔻....."
    STATUS_CLONING = "🤶 ℂ𝕝𝕠𝕟𝕚𝕟𝕘..!. ♻️ "
    STATUS_WAITING = "😡 𝕎𝕒𝕚𝕥𝕚𝕟𝕘...📝 "
    STATUS_PAUSE = "🤷‍♀️ ℙ𝕦𝕤𝕙...⏸ "
    STATUS_ARCHIVING = "💝 𝔸𝕣𝕔𝕙𝕚𝕧𝕚𝕟𝕘...🔐 "
    STATUS_EXTRACTING = "💔 𝔼𝕩𝕥𝕣𝕒𝕔𝕥𝕚𝕟𝕘...📂"
    STATUS_SPLITTING = "💞 𝕊𝕡𝕝𝕚𝕥𝕥𝕚𝕟𝕘...✂️"
    STATUS_CHECKING = "ℂ𝕙𝕖𝕔𝕜𝕚𝕟𝕘𝕦𝕡...📝"
    STATUS_SEEDING = "𝕊𝕖𝕖𝕕𝕚𝕟𝕘...🌧"

SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']


class setInterval:
    def __init__(self, interval, action):
        self.interval = interval
        self.action = action
        self.stopEvent = Event()
        thread = Thread(target=self.__setInterval)
        thread.start()

    def __setInterval(self):
        nextTime = time() + self.interval
        while not self.stopEvent.wait(nextTime - time()):
            nextTime += self.interval
            self.action()

    def cancel(self):
        self.stopEvent.set()

def get_readable_file_size(size_in_bytes) -> str:
    if size_in_bytes is None:
        return '0B'
    index = 0
    while size_in_bytes >= 1024:
        size_in_bytes /= 1024
        index += 1
    try:
        return f'{round(size_in_bytes, 2)}{SIZE_UNITS[index]}'
    except IndexError:
        return 'File too large'

def getDownloadByGid(gid):
    with download_dict_lock:
        for dl in list(download_dict.values()):
            if dl.gid() == gid:
                return dl
    return None

def getAllDownload(req_status: str):
    with download_dict_lock:
        for dl in list(download_dict.values()):
            status = dl.status()
            if req_status in ['all', status]:
                return dl
    return None

def bt_selection_buttons(id_: str):
    if len(id_) > 20:
        gid = id_[:12]
    else:
        gid = id_

    pincode = ""
    for n in id_:
        if n.isdigit():
            pincode += str(n)
        if len(pincode) == 4:
            break

    buttons = ButtonMaker()
    if WEB_PINCODE:
        buttons.buildbutton("Select Files", f"{BASE_URL}/app/files/{id_}")
        buttons.sbutton("Pincode", f"btsel pin {gid} {pincode}")
    else:
        buttons.buildbutton("Select Files", f"{BASE_URL}/app/files/{id_}?pin_code={pincode}")
    buttons.sbutton("Done Selecting", f"btsel done {gid} {id_}")
    return buttons.build_menu(2)

def get_progress_bar_string(status):
    completed = status.processed_bytes() / 8
    total = status.size_raw() / 8
    p = 0 if total == 0 else round(completed * 100 / total)
    p = min(max(p, 0), 100)
    cFull = p // 8
    p_str = '🟨' * cFull
    p_str += '⬜️' * (12 - cFull)
    p_str = f"{p_str}"
    return p_str

def get_readable_message():
    with download_dict_lock:
        msg = ""
        if STATUS_LIMIT is not None:
            tasks = len(download_dict)
            global pages
            pages = ceil(tasks/STATUS_LIMIT)
            if PAGE_NO > pages and pages != 0:
                globals()['COUNT'] -= STATUS_LIMIT
                globals()['PAGE_NO'] -= 1
            
        for index, download in enumerate(list(download_dict.values())[COUNT:], start=1):
            #msg += "\n"
            msg += f"\n<b>┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓</b>"
            msg += f"\n┃  <a  href='{download.message.link}'>{download.status()}</a> "
            msg += f"\n<b>┃  {get_progress_bar_string(download)} {download.progress()}</b>"
            #msg += f"\n<b>┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓ </b>"
            msg += f"\n<b>┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫</b>"
            if download.status() not in [MirrorStatus.STATUS_SPLITTING, MirrorStatus.STATUS_SEEDING]:
                msg += f"\n┃  📡 ℙ𝕣𝕠𝕔𝕖𝕤𝕤𝕖𝕕➽ {get_readable_file_size(download.processed_bytes())} of {download.size()}"
                msg += f"\n┃  🚀 𝕊𝕡𝕖𝕖𝕕➽ {download.speed()} | ⏳𝔼𝕥𝕒➽ {download.eta()}"
                if hasattr(download, 'seeders_num'):
                    try:
                        msg += f"\n┃  🍃 𝕊𝕖𝕖𝕕𝕖𝕣𝕤➽ {download.seeders_num()} | 💬 𝕃𝕖𝕖𝕔𝕙𝕖𝕣𝕤➽  {download.leechers_num()}"
                    except:
                        pass
                msg += f"\n┃ 📌ℕ𝕒𝕞𝕖➽ <code>{escape(str(download.name()))}</code>"
                #msg += f"\n<b> ━━━━━━━━━━━━━━━━━━━━━━━━━━━━ </b>"
                msg += f"\n<b>┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫</b>"
            elif download.status() == MirrorStatus.STATUS_SEEDING:
                msg += f"\n<b>┃  📦 𝕊𝕚𝕫𝕖➽ </b>{download.size()}"
                msg += f"\n<b>┃ 📯 𝕊𝕡𝕖𝕖𝕕➽ </b>{download.upload_speed()}"
                msg += f" | <b>┃ 👰 𝕌𝕡𝕝𝕠𝕒𝕕𝕖𝕕➽ </b>{download.uploaded_bytes()}"
                msg += f"\n<b>┃ 👁️‍🗨️ ℝ𝕒𝕥𝕚𝕠➽ </b>{download.ratio()}"
                msg += f" | <b>┃ ⏳ 𝔼𝕥𝕒➽ </b>{download.seeding_time()}"
            else:
                msg += f"\n📦 𝕊𝕚𝕫𝕖➽ {download.size()}"
            msg += f"\n┃ ❌𝕋𝕠𝕜𝕖𝕟➽ <code>/{BotCommands.CancelMirror} {download.gid()}</code>"
            #msg += f"\n┃ ❌Token➽ /{[BotCommands.CancelMirror_download.gid()]}"
            #msg += f"\n<b> ━━━━━━━━━━━━━━━━━━━━━━━━━━━━ </b>"
            msg += f"\n<b>┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛</b>"
            #msg += "\n"
            if STATUS_LIMIT is not None and index == STATUS_LIMIT:
                break
        if len(msg) == 0:
            return None, None
        dl_speed = 0
        up_speed = 0
        for download in list(download_dict.values()):
            if download.status() == MirrorStatus.STATUS_DOWNLOADING:
                spd = download.speed()
                if 'K' in spd:
                    dl_speed += float(spd.split('K')[0]) * 1024
                elif 'M' in spd:
                    dl_speed += float(spd.split('M')[0]) * 1048576
            elif download.status() == MirrorStatus.STATUS_UPLOADING:
                spd = download.speed()
                if 'KB/s' in spd:
                    up_speed += float(spd.split('K')[0]) * 1024
                elif 'MB/s' in spd:
                    up_speed += float(spd.split('M')[0]) * 1048576
            elif download.status() == MirrorStatus.STATUS_SEEDING:
                spd = download.upload_speed()
                if 'K' in spd:
                    up_speed += float(spd.split('K')[0]) * 1024
                elif 'M' in spd:
                    up_speed += float(spd.split('M')[0]) * 1048576
       #bmsg = f"\n<b>┏━━━━━━━━━━━•❅•°•❈•━━━━━━━━━━━┓</b>"
        bmsg = f"\n<b>╭───────────────────────────╮</b>"
        bmsg = f"\n<b>╭────────────•❅•°•❈•───────────╮</b>"
        bmsg += f"\n<b>      🖥️ ℂ𝕡𝕦➮ </b> {cpu_percent()}% ❖ <b>📀𝔽𝕣𝕖𝕖➮ </b> {get_readable_file_size(disk_usage(DOWNLOAD_DIR).free)}"
        bmsg += f"\n<b>      🎮 ℝ𝕒𝕞➮ </b> {virtual_memory().percent}% ❖ <b>🌋𝕌𝕡𝕥𝕚𝕞𝕖➮ </b> {get_readable_time(time() - botStartTime)}"
        bmsg += f"\n<b>      🔽𝔻𝕃➮ </b> {get_readable_file_size(dl_speed)}/s🔻 ❖ <b>🔼𝕌𝕃➮ </b> {get_readable_file_size(up_speed)}/s🔺"
        #bmsg += f"\n<b>┗━━━━━━━━━━━•❅•°•❈•━━━━━━━━━━━┛</b>"
        #bmsg += f"\n<b>╰───────────────────────────╯</b>"
        bmsg += f"\n<b>╰────────────•❅•°•❈•───────────╯</b>"
        bmsg += f"\n<b> 🍀⚡️𝔻𝕠𝕨𝕟𝕝𝕠𝕕𝕤👉 /status [𝚜𝚎𝚎 𝚊𝚕𝚕]</b>"
        if STATUS_LIMIT is not None and tasks > STATUS_LIMIT:
            msg += f"<b>Page:</b> {PAGE_NO}/{pages} | <b>Tasks:</b> {tasks}\n"
            buttons = ButtonMaker()
            buttons.sbutton("Previous", "status pre")
            buttons.sbutton("Next", "status nex")
            button = buttons.build_menu(2)
            return msg + bmsg, button
        return msg + bmsg, ""

def turn(data):
    try:
        with download_dict_lock:
            global COUNT, PAGE_NO
            if data[1] == "nex":
                if PAGE_NO == pages:
                    COUNT = 0
                    PAGE_NO = 1
                else:
                    COUNT += STATUS_LIMIT
                    PAGE_NO += 1
            elif data[1] == "pre":
                if PAGE_NO == 1:
                    COUNT = STATUS_LIMIT * (pages - 1)
                    PAGE_NO = pages
                else:
                    COUNT -= STATUS_LIMIT
                    PAGE_NO -= 1
        return True
    except:
        return False

def get_readable_time(seconds: int) -> str:
    result = ''
    (days, remainder) = divmod(seconds, 86400)
    days = int(days)
    if days != 0:
        result += f'{days}d'
    (hours, remainder) = divmod(remainder, 3600)
    hours = int(hours)
    if hours != 0:
        result += f'{hours}h'
    (minutes, seconds) = divmod(remainder, 60)
    minutes = int(minutes)
    if minutes != 0:
        result += f'{minutes}m'
    seconds = int(seconds)
    result += f'{seconds}s'
    return result

def is_url(url: str):
    url = re_findall(URL_REGEX, url)
    return bool(url)

def is_gdrive_link(url: str):
    return "drive.google.com" in url

def is_mega_link(url: str):
    return "mega.nz" in url or "mega.co.nz" in url

def get_mega_link_type(url: str):
    if "folder" in url:
        return "folder"
    elif "file" in url:
        return "file"
    elif "/#F!" in url:
        return "folder"
    return "file"

def is_magnet(url: str):
    magnet = re_findall(MAGNET_REGEX, url)
    return bool(magnet)

def new_thread(fn):
    """To use as decorator to make a function call threaded.
    Needs import
    from threading import Thread"""

    def wrapper(*args, **kwargs):
        thread = Thread(target=fn, args=args, kwargs=kwargs)
        thread.start()
        return thread

    return wrapper

def get_content_type(link: str) -> str:
    try:
        res = rhead(link, allow_redirects=True, timeout=5, headers = {'user-agent': 'Wget/1.12'})
        content_type = res.headers.get('content-type')
    except:
        try:
            res = urlopen(link, timeout=5)
            info = res.info()
            content_type = info.get_content_type()
        except:
            content_type = None
    return content_type
