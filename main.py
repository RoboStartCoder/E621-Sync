import json
import math
import os
import time

import requests
from pathlib import Path

import schedule
from requests.auth import HTTPBasicAuth

ROOT: Path
TIMER: int
DELETE_BLACKLISTED: bool
DELETE_DUPLICATES: bool
AUTH: HTTPBasicAuth

headers = {'user-agent': 'hydrusBatchSauce/corposim'}
extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
config_template = {
  "authentication": {
    "username": "",
    "api_key": ""
  },
  "auto_delete": {
    "blacklisted": True,
    "duplicates": True
  },
  "root_dir": "",
  "sync_timer": 3600
}

def load_config():
    global AUTH, TIMER, DELETE_BLACKLISTED, DELETE_DUPLICATES, ROOT
    try:
        with open(f"config.json", "x", encoding="utf-8") as f:
            json.dump({}, f, indent=4, ensure_ascii=False)
    except FileExistsError:
        pass
    with open(f'config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
        ROOT = Path(config["root_dir"])

        if not ROOT.exists() or not ROOT.is_dir():
            print("[ROOT Directory failed] Check ROOT_DIR path in config.json")
            exit(1)

        AUTH = HTTPBasicAuth(config["authentication"]["username"], config["authentication"]["api_key"])

        auth_test = requests.get("https://e621.net/users/me.json", headers=headers, auth=AUTH)
        if auth_test.status_code != 200 or auth_test.json()["name"] == "Anonymous":
            print("[Authentication failed] Check API_KEY and USERNAME in config.json")
            exit(1)

        DELETE_BLACKLISTED = config["auto_delete"]["blacklisted"]
        DELETE_DUPLICATES = config["auto_delete"]["duplicates"]

        TIMER = config["sync_timer"]


def load_all_local(directory: Path):
    result = []
    bad = []
    for file in directory.iterdir():
        if file.suffix.lower() in extensions:
            result.append(str(file.relative_to(directory)))
        else:
            bad.append(str(file))
    return result, bad


def load_all_remote():
    result = []
    posts = []
    for i in range(math.ceil(
            requests.get("https://e621.net/users/me.json", headers=headers, auth=AUTH).json()["favorite_count"] / 320)):
        posts.extend(
            requests.get(f"https://e621.net/favorites.json?limit=320&page={i + 1}", headers=headers, auth=AUTH).json()[
                "posts"])
    for image in posts:
        result.append(image["id"])
    return result


def load_manifest():
    path = ROOT.joinpath("manifest.json")

    try:
        with open(path, "x", encoding="utf-8") as f:
            json.dump({}, f, indent=4, ensure_ascii=False)
    except FileExistsError:
        pass

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def add_manifest(manifest: dict, data: dict, directory: Path):
    manifest.update(data)
    update_manifest(manifest, directory)


def delete_manifest(manifest: dict, file_: int, directory: Path):
    manifest.pop(file_, None)
    update_manifest(manifest, directory)


def update_manifest(manifest: dict, directory: Path):
    with open(directory.joinpath("manifest.json"), 'w', encoding='utf-8') as file:
        json.dump(manifest, file, indent=4, ensure_ascii=False)


def find_local_only(local: list[str], manifest: dict):
    return list(set(local) - set(manifest))


def find_remote_only(remote: list[int], manifest: dict):
    return list(set(remote) - set(manifest.values()))


def find_local_deleted(local: list[str], manifest: dict) -> list[str]:
    return list(set(manifest) - set(local))


def find_remote_deleted(remote: list[int], manifest: dict):
    return list(set(manifest.values()) - set(remote))


def delete_local(file: str, directory: Path):
    os.remove(directory.joinpath(file))


def delete_remote(id_: int):
    requests.delete(f"https://e621.net/favorites/{id_}.json")


def add_local(id_: int, directory: Path, filename: str = ""):
    url = requests.get(f"https://e621.net/posts/{id_}.json", headers=headers, auth=AUTH).json()["post"]["file"]["url"]
    if url is None:
        return None
    response = requests.get(url, stream=True)
    response.raise_for_status()

    with open(directory.joinpath(f"{id_ if filename == "" else filename}.{url.split(".")[-1]}"), 'wb') as file:
        for chunk in response.iter_content(chunk_size=8192):
            file.write(chunk)
    return directory.joinpath(f"{id_ if filename == "" else filename}.{url.split(".")[-1]}")


def add_remote(id_: int):
    requests.post("https://e621.net/favorites.json", json={"post_id": id_}, headers=headers, auth=AUTH)


def find_post(img: str):
    r = requests.post("https://e621.net/iqdb_queries.json", files={'file': (open(ROOT.joinpath(img), 'rb'))},
                      headers=headers, auth=AUTH)
    try:
        return int(r.json()[0]['post_id']), str(r.json()[0]["post"]["posts"]['tag_string']).split(" ")
    except:
        raise FileNotFoundError


def get_user_blacklisted():
    return str(
        requests.get("https://e621.net/users/me.json", headers=headers, auth=AUTH).json()["blacklisted_tags"]).split(
        "\n")


def sync_pools(directory: Path) -> list[int]:
    ids_in_pools: list[int] = []

    pools_pattern = list(directory.rglob("*.pool"))
    for pp in pools_pattern:
        name = pp.name.split('.')[0]
        new_pool = {
            "id": int(name),
            "manifest": {}
        }
        with open(pp.parent.joinpath("pool.json"), 'w', encoding='utf-8') as file:
            json.dump(new_pool, file, indent=4, ensure_ascii=False)
        os.remove(pp)

    pools = list(directory.rglob("pool.json"))
    for pool in pools:
        with open(pool, 'r', encoding='utf-8') as file:
            data = json.loads(file.read().strip())
            manifest = data["manifest"]
            id_ = data["id"]

            remote: list[int] = requests.get(f"https://e621.net/pools/{id_}.json", headers=headers, auth=AUTH).json()[
                "post_ids"]
            remote_only: list[int] = find_remote_only(remote, manifest)
            for post in remote_only:
                local_post = add_local(post, pool.parent, str(remote.index(post) + 1))
                if local_post is None:
                    print(f"[Pool element fail] {post} <{id_}>")
                    continue
                add_remote(post)
                print(f"[Pool element add] {local_post.relative_to(directory)} ({post}) <{id_}>")
                manifest.update({f"{local_post.name}": post})
        with open(pool, 'w', encoding='utf-8') as file:
            json.dump({"id": id_, "manifest": manifest}, file, indent=4, ensure_ascii=False)
        for post_id in manifest.values():
            ids_in_pools.append(post_id)
    return ids_in_pools


def sync():
    print("[INFO] Synchronization started...")
    print("[INFO] Syncing pools...\n")
    ids_in_pools = sync_pools(ROOT)
    print("[INFO] Pools done!\n")
    print("[INFO] Prepare to sync ungrouped posts\n")

    local, bad = load_all_local(ROOT)
    remote = load_all_remote()
    manifest = load_manifest()

    blacklisted = get_user_blacklisted()

    print("Unsupported:", *bad, sep='\n- ', end='\n\n')
    print(
        f"Blacklisted{" (Images with there tags will be deleted)" if DELETE_BLACKLISTED else " (Auto delete images with blacklisted tags disabled)"}:",
        *blacklisted, sep='\n- ', end='\n\n')

    not_found = []

    print("[INFO] Syncing ungrouped posts...\n")

    local_deleted = find_local_deleted(local, manifest)
    print("Local Deleted:", *local_deleted, sep='\n- ', end='\n\n')
    for file_ in local_deleted:
        delete_remote(manifest[file_])
        print(f"[Local deleted] {file_} ({manifest[file_]})")
        time.sleep(0.5)

    remote_deleted = find_remote_deleted(remote, manifest)
    print("Remote Deleted:", *remote_deleted, sep='\n- ', end='\n\n')
    for id_ in remote_deleted:
        file_ = [k for k, v in manifest.items() if v == id_][0]
        delete_local(file_, ROOT)
        print(f"[Local deleted] {file_} ({id_})")
        time.sleep(0.5)

    local_only = find_local_only(local, manifest)
    print("Local Only:", *local_only, sep='\n- ', end='\n\n')
    for file_ in local_only:
        try:
            id_, tags_ = find_post(file_)
            if id_ in manifest.values() or id_ in ids_in_pools:
                if DELETE_DUPLICATES:
                    delete_local(file_, ROOT)
                print(f"[Duplicate{" deleted" if DELETE_DUPLICATES else " found"}] {file_} ({id_})")
                continue
            if set(blacklisted) & set(tags_):
                if DELETE_BLACKLISTED:
                    delete_local(file_, ROOT)
                print(
                    f"[Blacklisted{" deleted" if DELETE_DUPLICATES else " found"}] {file_} ({id_}) <{set(blacklisted) & set(tags_)}>")
                continue
            add_remote(id_)
            print(f"[Remote add] {file_} ({id_})")
            add_manifest(manifest, {file_: id_}, ROOT)
        except FileNotFoundError:
            print(f"[Not found] {file_}")
            not_found.append(file_)
        time.sleep(0.5)

    remote_only = set(find_remote_only(remote, manifest)) - set(ids_in_pools)
    print("Remote Only:", *remote_only, sep='\n- ', end='\n\n')
    for id_ in remote_only:
        if id_ in ids_in_pools:
            continue
        res = add_local(id_, ROOT)
        if res is not None:
            print(f"[Local add] {res.name} ({id_})")
            add_manifest(manifest, {f"{res.name}": id_}, ROOT)
        else:
            print(f"[Local fail] {id_}")
        time.sleep(0.5)

    print("[INFO] Ungrouped posts done!\n")
    print("[INFO] Sync complete!")


def do_sync():
    try:
        sync()
    except Exception as e:
        pass

if __name__ == '__main__':
    print("[INFO] Preparing, please wait...")
    load_config()
    schedule.every(TIMER).seconds.do(do_sync)
    do_sync()

    while True:
        schedule.run_pending()
        time.sleep(1)
