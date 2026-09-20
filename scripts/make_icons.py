from pathlib import Path

from PIL import Image, ImageDraw

dest = Path("web/public/icons")
dest.mkdir(parents=True, exist_ok=True)
for size, name in [(192, "icon-192"), (512, "icon-512"), (512, "maskable-512")]:
    im = Image.new("RGB", (size, size), "#123c38")
    d = ImageDraw.Draw(im)
    # Abstract rising research mark, inside the Android mask safe zone.
    s = size / 512
    points = [
        (int(x * s), int(y * s))
        for x, y in [
            (148, 350),
            (148, 162),
            (175, 162),
            (175, 266),
            (296, 162),
            (335, 162),
            (214, 270),
            (350, 350),
            (298, 350),
            (175, 285),
            (175, 350),
        ]
    ]
    d.polygon(points, fill="#f5f4ed")
    im.save(dest / (name + ".png"), optimize=True)
