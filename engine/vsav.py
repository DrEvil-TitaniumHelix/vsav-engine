"""
vsav.py - VASSAL save-file codec. Game-agnostic.

A .vsav is a zip of three entries: moduledata, savedata, and savedGame.
savedGame is obfuscated as "!VCSK" + 2-hex-digit XOR key + hex-encoded body.
The key is read from the header on decode; encode takes it as a parameter
(each module writes saves with its own key — Westwall uses 0xA3).
"""
import zipfile


def decode_saved(raw: str) -> str:
    assert raw.startswith("!VCSK"), "not an obfuscated VASSAL save"
    key = int(raw[5:7], 16)
    body = raw[7:]
    return bytes(int(body[i:i + 2], 16) ^ key for i in range(0, len(body), 2)).decode("latin-1")


def encode_saved(plain: str, key: int) -> str:
    return "!VCSK" + f"{key:02x}" + "".join(f"{b ^ key:02x}" for b in plain.encode("latin-1"))


def save_key(path) -> int:
    """The XOR key a given .vsav was written with."""
    with zipfile.ZipFile(path) as z:
        return int(z.read("savedGame")[5:7], 16)


def read_vsav(path):
    with zipfile.ZipFile(path) as z:
        return (decode_saved(z.read("savedGame").decode("latin-1")),
                z.read("moduledata"), z.read("savedata"))


def write_vsav(path, plain, moduledata, savedata, key: int):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("moduledata", moduledata)
        z.writestr("savedata", savedata)
        z.writestr("savedGame", encode_saved(plain, key).encode("ascii"))
