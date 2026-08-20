# ruff: noqa: I001

import argparse
from dataclasses import dataclass
from getpass import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import TypedDict, cast

from bs4 import BeautifulSoup as bs
import requests as rq
from simple_term_menu import TerminalMenu


LOGIN_URL = "https://usaco.org/current/tpcm/login-session.php"
SUBMIT_URL = "https://usaco.org/current/tpcm/submit-solution.php"
STATUS_URL = "https://usaco.org/current/tpcm/status-update.php"
PROBLEM_URL = "https://usaco.org/index.php?page=viewproblem2&cpid="


LANGUAGES: dict[str, int] = {
    "c": 1,
    "cpp-11": 6,
    "cpp-17": 7,
    "java": 9,
    "python2": 3,
    "python3": 4,
}


class Config(TypedDict):
    uname: str
    passwd: str
    language: int


class StatusResponse(TypedDict):
    cd: int
    sc: str
    sr: str
    output: str
    jd: str


@dataclass
class CliArgs:
    login: bool
    file: str
    language: str | None
    cpid: str


class Color:
    RESET: str = "\033[0m"

    RED: str = "\033[31m"
    GREEN: str = "\033[32m"


s = rq.Session()
s.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0",
        "Accept-Language": "en-US,en;q=0.5",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "TE": "trailers",
    }
)


def get_config_dir() -> Path:
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "usaco-cli"
        else:
            return Path.home() / "AppData" / "Roaming" / "usaco-cli"

    else:
        return Path.home() / ".config" / "usaco-cli"


def create_config_file() -> None:
    config_dir = get_config_dir()

    uname = input("Enter usaco.org username: ")
    passwd = getpass("Enter usaco.org passwd: ")

    menu_options = list(LANGUAGES.keys())
    tm = TerminalMenu(menu_options, title="Select default language:")
    selected = tm.show()

    if selected is None:
        print("Selection cancelled. Exiting...")
        sys.exit(0)

    language = menu_options[selected]

    creds: Config = {"uname": uname, "passwd": passwd, "language": LANGUAGES[language]}

    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(creds, f, indent=4)

    # Allow only current user to acces file
    username = os.getlogin()
    path_str = str(os.path.join(config_dir, "config.json"))
    if os.name == "nt":
        _ = subprocess.run(
            ["icacls", path_str, "/inheritance:r"], capture_output=True, check=False
        )
        _ = subprocess.run(
            ["icacls", path_str, "/grant", f"{username}:F"],
            capture_output=True,
            check=False,
        )
    else:
        os.chmod(path_str, 0o600)


def auth(uname: str, passwd: str) -> None:
    d = {"uname": uname, "password": passwd, "login": "Login"}

    r = s.post(url=LOGIN_URL, data=d)

    if str(r.status_code) != "200":
        print(f"""Something went wrong with auth\n
            Status code: {r.status_code}, 
            JSON: {r.json()}""")
        sys.exit(1)


def submit_problem(cpid: str, lang: int, filename: str) -> str:
    d: dict[str, str] = {
        "cpid": cpid,
        "language": str(lang),
        "solution-submit": "Submit Solution",
    }

    if not os.path.exists(filename):
        print("No such file")
        sys.exit(1)

    with open(filename, "rb") as source_file:
        files = {"sourcefile": (filename, source_file, "text/x-c++src")}
        r = s.post(
            url=SUBMIT_URL,
            data=d,
            files=files,
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


def get_results(txt: str) -> None:
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
        data_dict = cast(StatusResponse, json.loads(r.text))
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
        sys.exit(0)
    soup = bs(data_dict["jd"], "html.parser")

    correct = 0
    total = 0
    for i, link in enumerate(soup.find_all("a")):
        if "correct" in str(link["title"]).lower():
            print(f"{Color.GREEN} {i + 1}) {link['title']} {Color.RESET}")
            correct += 1
        else:
            print(f"{Color.RED}{i}) {link['title']}{Color.RESET}")
        total += 1

    if total != correct:
        print(f"{Color.RED}TOTAL: {correct}/{total}{Color.RESET}")
    else:
        print(f"{Color.GREEN}TOTAL: {correct}/{total}{Color.RESET}")


def parse_args() -> CliArgs:
    parser = argparse.ArgumentParser(
        description="CLI tool for submitting problems to usaco.org"
    )

    action_group = parser.add_argument_group("Actions")
    _ = action_group.add_argument(
        "--login",
        action="store_true",
        help="Force re-login to update or fix saved credentials",
    )

    submit_group = parser.add_argument_group("Submission Options")
    _ = submit_group.add_argument("-f", "--file", type=str, help="File to submit")
    _ = submit_group.add_argument(
        "-l", "--language", type=str, choices=LANGUAGES.keys(), help="Language override"
    )
    _ = submit_group.add_argument("-i", "--cpid", type=str, help="Problem ID")

    namespace = parser.parse_args()
    args = CliArgs(
        login=cast(bool, namespace.login),
        file=cast(str, namespace.file),
        language=cast(str | None, namespace.language),
        cpid=cast(str, namespace.cpid),
    )

    if not args.login and (not args.file or not args.cpid):
        parser.error(
            "The following arguments are required for submission: -f/--file, -i/--cpid\n"
            + "Alternatively, run with --login to reset credentials."
        )

    return args


def show_title(cpid: str) -> None:
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


def main() -> None:

    # Try loading config file
    home = get_config_dir()
    conf_file = os.path.join(home, "config.json")

    # Create config file if nonexistent
    if not os.path.exists(conf_file):
        create_config_file()
        print("Config Created")
        sys.exit(0)

    # Parse arguments: login or problem type
    args = parse_args()
    if args.login:
        print("Resseting credentials")
        create_config_file()
        sys.exit(0)

    filepath = args.file
    lang = args.language
    cpid = args.cpid

    # Load credentials
    with open(conf_file, "r", encoding="utf-8") as f:
        creds = cast(Config, json.load(f))
    

    # If alternative language is proposed other than the default one load and parse it
    if lang:
        lang = LANGUAGES[str(lang)]
    else:
        lang = creds["language"]
    

    # Authenticate on usaco.org
    auth(uname=creds["uname"], passwd=creds["passwd"])

    # Submit problem and load 
    txt = submit_problem(cpid=cpid, lang=lang, filename=filepath)

    # Show problem title for better UX
    show_title(cpid)
    
    get_results(txt=txt)


if __name__ == "__main__":
    main()
