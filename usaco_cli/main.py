from pyexpat import ErrorString

import requests as rq
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup as bs
from dotenv import load_dotenv
from getpass import getpass
from simple_term_menu import TerminalMenu

load_dotenv()


LOGIN_URL = "https://usaco.org/current/tpcm/login-session.php"
SUBMIT_URL = "https://usaco.org/current/tpcm/submit-solution.php"
STATUS_URL = "https://usaco.org/current/tpcm/status-update.php"
PROBLEM_URL = "https://usaco.org/index.php?page=viewproblem2&cpid="


LANGUAGES = {
    "c": 1,
    "cpp-11": 6,
    "cpp-17": 7,
    "java": 9,
    "python2": 3,
    "python3": 4,
}


class Color:
    RESET = "\033[0m"

    RED = "\033[31m"
    GREEN = "\033[32m"


s = rq.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0",
    "Accept-Language": "en-US,en;q=0.5",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "TE": "trailers",
})


def get_config_dir():
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "usaco-cli"
        else:
            return Path.home() / "AppData" / "Roaming" / "usaco-cli"

    else:
        return Path.home() / ".config" / "usaco-cli"


def create_config_file():
    dir = get_config_dir()

    uname = input("Enter usaco.org username: ")
    passwd = getpass("Enter usaco.org passwd: ")

    menu_options = list(LANGUAGES.keys())
    tm = TerminalMenu(menu_options, title="Select default language:")
    selected = tm.show()

    if selected is None:
        print("Selection cancelled. Exiting...")
        sys.exit(0)

    if isinstance(selected, int):
        language = menu_options[selected]
    else:
        # This fallback is just for Pyright's peace of mind
        language = menu_options[selected[0]]

    creds = {"uname": uname, "passwd": passwd, "language": LANGUAGES[language]}

    os.makedirs(dir, exist_ok=True)
    with open(os.path.join(dir, "config.json"), "w") as f:
        json.dump(creds, f, indent=4)

    # Allow only current user to acces file
    username = os.getlogin()
    path_str = str(os.path.join(dir, "config.json"))
    if os.name == "nt":
        subprocess.run(
            ["icacls", path_str, "/inheritance:r"], capture_output=True
        )
        subprocess.run(
            ["icacls", path_str, "/grant", f"{username}:F"], capture_output=True
        )
    else:
        os.chmod(path_str, 0o600)


def auth(uname, passwd):
    d = {"uname": uname, "password": passwd, "login": "Login"}

    r = s.post(url=LOGIN_URL, data=d)

    if str(r.status_code) != "200":
        print(f"""Something went wrong with auth\n
            Status code: {r.status_code}, 
            JSON: {r.json()}""")
        sys.exit(1)


def submit_problem(cpid, lang, filename):
    d = {
        "cpid": cpid,
        "language": lang,
        "solution-submit": "Submit Solution",
    }

    if not os.path.exists(filename):
        print("No such file")
        sys.exit(1)
    
    f = {"sourcefile": (filename, open(filename, "rb"), "text/x-c++src")}

    r = s.post(
        url=SUBMIT_URL,
        data=d,
        files=f,
        headers={
            "Referer": f"https://usaco.org/index.php?page=viewproblem2&cpid={cpid}",
            "Origin": "https://usaco.org",
        },
    )

    if str(r.status_code) != "200":
        print(f"""Something went wrong with submit\n
            Status code: {r.status_code}, 
            JSON: {r.json()}""")

    return r.text


def get_results(txt: str):
    match = re.search(r'data-sid="(\d+)"', txt)
    if match:
        sid = match.group(1)
    else:
        print("couldnt find submission id in response")
        sys.exit(1)

    while True:
        r = s.post(url=STATUS_URL, data={"sid": sid})

        if str(r.status_code) != "200":
            print(f"""Something went wrong with pulling the tests\n
                Status code: {r.status_code}, 
                JSON: {r.json()}""")
            sys.exit()
        data_dict = json.loads(str(r.text))
        current_status = data_dict["cd"]
        if current_status >= 0:
            break

        time.sleep(3)

    # parse output

    if data_dict["sc"] == "status-no":
        print(data_dict["sr"])
        error_lines = data_dict["output"].strip().split("\n")
        for line in error_lines[:15]:
            print(line)

        print("there may be more lines i just print the first 15")
        sys.exit(1)
    soup = bs(data_dict["jd"], "html.parser")

    correct = 0
    total = 0
    for i, link in enumerate(soup.find_all("a")):
        if "correct" in str(link["title"]).lower():
            print(f"{Color.GREEN} {i} {Color.RESET}")
            correct += 1
        else:
            print(f"{Color.RED} {i}{Color.RESET}")
        total += 1

    if total // 2 >= correct:
        print(f"{Color.RED}TOTAL: {correct}/{total}{Color.RESET}")
    else:
        print(f"{Color.GREEN}TOTAL: {correct}/{total}{Color.RESET}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="CLI tool for submitting problems to usaco.org"
    )

    action_group = parser.add_argument_group("Actions")
    action_group.add_argument(
        "--login",
        action="store_true",
        help="Force re-login to update or fix saved credentials",
    )

    submit_group = parser.add_argument_group("Submission Options")
    submit_group.add_argument("-f", "--file", type=str, help="File to submit")
    submit_group.add_argument(
        "-l", "--language", type=str, help="Language override"
    )
    submit_group.add_argument("-i", "--cpid", type=str, help="Problem ID")

    args = parser.parse_args()

    if not args.login:
        if not args.file or not args.cpid:
            parser.error(
                "The following arguments are required for submission: -f/--file, -i/--cpid\n"
                "Alternatively, run with --login to reset credentials."
            )

    return args


def show_title(cpid):
    r = s.get(
        url=PROBLEM_URL + cpid,
    )

    if str(r.status_code) != "200":
        print(f"""Something went wrong with accesing the problem\n
            Status code: {r.status_code}, 
            JSON: {r.json()}""")
        sys.exit(1)
    soup = bs(r.text, "html.parser")
    headings = soup.select("div.panel h2")

    print(headings[1].text)


def main():
    home = get_config_dir()
    conf_file = os.path.join(home, "config.json")

    if not os.path.exists(conf_file):
        create_config_file()
        print("Config Created")
        sys.exit(1)

    args = parse_args()
    if args.login:
        print("Resseting credentials")
        create_config_file()
        sys.exit(1)

    filepath = args.file
    lang = args.language
    cpid = args.cpid

    show_title(cpid)

    if lang:
        lang = LANGUAGES[str(lang)]

    with open(conf_file, "r") as f:
        creds = json.load(f)

    auth(uname=creds["uname"], passwd=creds["passwd"])

    if not lang:
        lang = creds["language"]
    txt = submit_problem(cpid=cpid, lang=lang, filename=filepath)

    get_results(txt=txt)


if __name__ == "__main__":
    main()