import os, sys
from PIL import Image

BF = r"E:\LaunchBox\Images\VASSAL\Box - Front"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "web", "covers")

GAME_COVERS = {
    "tobruk": "Tobruk_ Tank Battles in North Africa 1942-01.jpg",
    "blue-and-gray-chickamauga": "Blue & Gray_ Four American Civil War Battles-01.jpg",
    "westwall-arnhem": "Westwall_ Four Battles to Germany-01.jpg",
    "afrika-korps-classic-ah": "Afrika Korps-01.jpg",
    "austerlitz-gmt": "Austerlitz_ Napoleon_s Greatest Victory-01.jpg",
    "siege-of-jerusalem": "The Siege of Jerusalem-01.jpg",
    "napoleon-at-waterloo": "Napoleon at Waterloo (2nd & 3rd Ed)-01.jpg",
}

ROTATOR = [
    "Advanced Squad Leader-01.jpg",
    "Squad Leader-01.jpg",
    "PanzerBlitz-01.jpg",
    "Panzer Leader-01.jpg",
    "The Russian Campaign-01.jpg",
    "Twilight Struggle-01.jpg",
    "Paths of Glory-01.jpg",
    "Here I Stand-01.jpg",
    "Commands & Colors_ Ancients-01.jpg",
    "Combat Commander_ Europe-01.jpg",
    "For the People-01.jpg",
    "Empire of the Sun_ The Pacific War 1941-1945-01.jpg",
    "Victory in the Pacific-01.jpg",
    "Wooden Ships & Iron Men-01.jpg",
    "Diplomacy-01.jpg",
    "Midway-01.jpg",
]

MAX_DIM = 420


def thumb(src, dst):
    im = Image.open(src)
    im = im.convert("RGB")
    im.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)
    im.save(dst, "JPEG", quality=85, optimize=True)
    return im.size


def main():
    os.makedirs(os.path.join(OUT, "rotator"), exist_ok=True)
    for slug, fn in GAME_COVERS.items():
        src = os.path.join(BF, fn)
        if not os.path.isfile(src):
            sys.exit(f"missing cover: {fn}")
        w, h = thumb(src, os.path.join(OUT, slug + ".jpg"))
        print(f"{slug}: {fn} -> {w}x{h}")
    for i, fn in enumerate(ROTATOR, 1):
        src = os.path.join(BF, fn)
        if not os.path.isfile(src):
            sys.exit(f"missing rotator cover: {fn}")
        w, h = thumb(src, os.path.join(OUT, "rotator", f"{i:02d}.jpg"))
        print(f"rotator/{i:02d}: {fn} -> {w}x{h}")


if __name__ == "__main__":
    main()
