from io import BytesIO
from pathlib import Path
from sys import path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "kindle-koreader"
UPSTREAM = PLUGIN / "upstream/trmnl.koplugin"
OUTPUT = PLUGIN / "trmnl-landscape-muse.zip"
path.insert(0, str(ROOT / "backend"))


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError("Upstream plugin hook changed: " + old.splitlines()[0])
    return source.replace(old, new, 1)


def patched_main():
    source = (UPSTREAM / "main.lua").read_text()
    source = replace_once(source, "function TrmnlDisplay:displayImage(image_path)",
                          "function TrmnlDisplay:displayImage(image_path, interaction)")
    source = replace_once(source, """    local image_bb = RenderImage:renderImageFile(
        image_path,
        true, -- enable caching
        screen_width,
        screen_height
    )""", """    local image_bb
    if interaction then
        local png = interaction.png
        image_bb = RenderImage:renderImageData(png, #png, false, screen_width, screen_height)
        interaction.png = nil
    else
        image_bb = RenderImage:renderImageFile(image_path, true, screen_width, screen_height)
    end""")
    source = replace_once(source, "self.image_widget.onGestureClose = function()",
                          """self.image_widget.onGestureClose = function(widget, _, gesture)
        if interaction then
            interaction.close(widget, gesture)
            return true
        end""")
    source = replace_once(source, '        if self.settings.close_gesture == "hold" then',
                          '''        if interaction then
            self.image_widget.onLandscapeTap = function(widget, _, gesture)
                interaction.tap(widget, gesture)
                return true
            end
            self.image_widget.ges_events = {
                GestureClose = { anywhere("hold")[1], anywhere("hold_release")[1] },
                LandscapeTap = anywhere("tap"),
            }
            self.image_widget.onSuspend = function(widget) interaction.lifecycle(widget, true) end
            self.image_widget.onResume = function(widget) interaction.lifecycle(widget, false) end
        elseif self.settings.close_gesture == "hold" then''')
    source = replace_once(source, "    if Device:hasKeys() then\n        self.image_widget.key_events",
                          "    if not interaction and Device:hasKeys() then\n        self.image_widget.key_events")
    source = replace_once(source, """    NetworkMgr:runWhenConnected(function()
        self:_doFetchAndDisplay()
    end)""", """    local generation = self.portrait_generation
    NetworkMgr:runWhenConnected(function()
        if generation == self.portrait_generation then self:_doFetchAndDisplay() end
    end)""")
    source = replace_once(source, """    UIManager:scheduleIn(2, function()
        self:_performFetch()
    end)""", """    local generation = self.portrait_generation
    UIManager:scheduleIn(2, function()
        if generation == self.portrait_generation then self:_performFetch() end
    end)""")
    return replace_once(source, "\nreturn TrmnlDisplay", '''
dofile(TrmnlDisplay:getPluginDir() .. "landscape.lua").attach(TrmnlDisplay)

return TrmnlDisplay''')


def sleep_image():
    from PIL import Image, ImageDraw
    from app.rendering.typography import font

    image = Image.new("L", (1024, 758), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse((467, 227, 557, 317), fill=0)
    draw.ellipse((493, 207, 579, 293), fill=255)
    draw.text((512, 397), "Sleeping", font=font(61, "Bold"), fill=0, anchor="ms")
    draw.text((512, 460), "Press the power button to wake", font=font(34), fill=0, anchor="ms")
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def main():
    files = {
        "main.lua": patched_main().encode(),
        "_meta.lua": (UPSTREAM / "_meta.lua").read_bytes(),
        "landscape.lua": (PLUGIN / "landscape.lua").read_bytes(),
        "sleep.lua": (PLUGIN / "sleep.lua").read_bytes(),
        "sleep.png": sleep_image(),
        "LICENSE": (PLUGIN / "upstream/LICENSE").read_bytes(),
    }
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in files.items():
            entry = ZipInfo(f"trmnl.koplugin/{name}", (2026, 1, 1, 0, 0, 0))
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, content, compress_type=ZIP_DEFLATED)
    print(OUTPUT)


if __name__ == "__main__":
    main()
