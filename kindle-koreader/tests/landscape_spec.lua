local mode, pending_wifi, offline, fail_fetch, fail_render = 0, nil, false, false, false
local requests, paints, layouts, completed_refreshes = {}, 0, 0, 0
local scheduled, next_ticks, logs = {}, {}, {}
local suspend_calls, fail_suspend = 0, false
local light_on, brightness, topmost = true, 12, nil
local light = {
    getCapacity = function() return 71 end,
    isFrontlightOn = function() return light_on end,
    frontlightIntensity = function() return light_on and brightness or 0 end,
    turnOffFrontlight = function() light_on = false end,
    turnOnFrontlight = function() light_on = true end,
    setIntensity = function(_, value) brightness = value end,
}
local function runNextTick()
    local callback = table.remove(next_ticks, 1)
    assert(callback)
    callback()
end
local width, height = 1024, 758
local task = { x = 40, y = 115, w = 85, h = 81, action = "complete",
    task_id = 9, completed = true, capability = "test-capability" }
local tabs = {}
for index, page in ipairs({ "todo", "calendar", "pomodoro", "muse" }) do
    tabs[index] = { x = (index-1)*230, y = 666, w = 230, h = 92,
        action = "navigate", page = page, number = 1 }
end

local power = { x = 920, y = 666, w = 104, h = 92, action = "suspend" }
local next_page = { x = 780, y = 530, w = 200, h = 60, action = "navigate", number = 2 }
local function stub(name, value)
    package.loaded[name] = value
end

local function screenWidth() return mode % 2 == 1 and 512 or 379 end
local function screenHeight() return mode % 2 == 1 and 379 or 512 end
local screen = {
    DEVICE_ROTATED_COUNTER_CLOCKWISE = 3, getWidth = screenWidth, getHeight = screenHeight,
    getRotationMode = function() return mode end,
    setRotationMode = function(_, target) mode = target end,
    getSize = function() return { w = screenWidth(), h = screenHeight() } end,
}
stub("device", { screen = screen, isTouchDevice = function() return true end,
    hasBattery = function() return true end,
    canSuspend = function() return true end,
    hasFrontlight = function() return true end,
    getPowerDevice = function() return light end,
})
local constructor = { new = function(_, spec) return spec end }
stub("ffi/blitbuffer", { COLOR_WHITE = 255 })
stub("ui/widget/container/centercontainer", constructor)
stub("ui/widget/container/framecontainer", constructor)
stub("ui/geometry", constructor)
stub("ui/widget/imagewidget", constructor)
stub("ui/event", { new = function(_, name) return name end })
stub("ui/network/manager", {
    runWhenConnected = function(_, callback)
        assert(not pending_wifi, "Overlapping Wi-Fi requests")
        if offline then pending_wifi = callback else callback() end
    end,
    afterWifiAction = function() end,
    isConnected = function() return true end,
    getBeforeActionFlag = function() return false end,
})
stub("ui/uimanager", {
    scheduleIn = function(_, seconds, callback)
        assert((seconds == 30 or seconds == 8) and not scheduled[callback])
        scheduled[callback] = seconds
    end,
    unschedule = function(_, callback) scheduled[callback] = nil end,
    nextTick = function(_, callback) next_ticks[#next_ticks + 1] = callback end,
    suspend = function()
        assert(topmost and topmost[1][1].file:match("sleep%.png$") and not light_on)
        suspend_calls = suspend_calls + 1
        if fail_suspend then error("test suspend failure") end
    end,
    getTopmostVisibleWidget = function() return topmost end,
    show = function(_, widget)
        assert(widget.background == 255 and widget.modal)
        topmost = widget
    end,
    close = function(_, widget)
        if topmost == widget then topmost = nil end
        widget.closed = true
    end,
    setDirty = function() end,
    forceRePaint = function() paints = paints + 1 end,
    waitForVSync = function() completed_refreshes = completed_refreshes + 1 end,
})
stub("socketutil", { set_timeout = function() end, reset_timeout = function() end })
stub("ltn12", { source = { string = function(body) return function() return body end end } })
local function log(...)
    local fields = { ... }
    for index, value in ipairs(fields) do fields[index] = tostring(value) end
    logs[#logs+1] = table.concat(fields, " ")
end
stub("logger", { info = log, warn = log })
stub("version", { getCurrentRevision = function() return "fixture-version" end })
local png = "\137PNG\r\n\26\n\0\0\0\13IHDR\0\0\4\0\0\0\2\246"
stub("mime", { unb64 = function() return png end })
stub("json", {
    encode = function(data)
        assert(data.completed == true and data.capability == "test-capability")
        return "completion"
    end,
    decode = function(body)
        local page, number = body:match("page=(%a+)&number=(%d+)&ui=2$")
        number = tonumber(number)
        local regions = { tabs[1], tabs[2], tabs[3], tabs[4], power }
        if page == "todo" then regions[6] = task end
        if (page == "todo" or page == "muse") and number == 1 then
            regions[#regions + 1] = setmetatable({ page = page }, { __index = next_page })
        end
        return {
            page = page, number = number, width = width, height = height, filename = "landscape-abcd.png",
            png = "test-fixture", regions = regions, refresh_rate = 30,
        }
    end,
})
stub("socket.http", { request = function(options)
    requests[#requests+1] = options
    assert(options.headers["access-token"] == "test-credential" and options.redirect == false)
    if options.method == "PUT" then
        assert(options.url:match("/tasks/9/completion$") and options.source() == "completion")
        return 1, 204
    end
    assert(options.headers["percent-charged"] == "71" and options.headers["dashboard-wifi"] == "connected")
    if fail_fetch then return nil, "timeout" end
    options.sink(assert(options.url:match("(page=%a+&number=%d+&ui=2)$")))
    return 1, 200
end })

local landscape = dofile("kindle-koreader/landscape.lua")
local prototype = {
    getPluginDir = function() return "kindle-koreader/" end,
    addToMainMenu = function(_, menu) menu.trmnl = { sub_item_table = {} } end,
    onSuspend = function() end, onResume = function() end, onCloseWidget = function() end,
    fetchAndDisplay = function(self) self.portrait = true end,
    startAutoRefresh = function(self) self.auto_refresh_enabled = true end,
    showError = function(self) self.error = true end,
    displayImage = function(self, _, interaction)
        assert(interaction.png == png)
        if fail_render then return false end
        if self.image_widget then self.image_widget.closed = true end
        self.image_widget = {
            dimen = { x = 0, y = 0, w = screenWidth(), h = screenHeight() },
            tap = interaction.tap, exit = interaction.close, lifecycle = interaction.lifecycle,
        }
        return true
    end,
}
landscape.attach(prototype)

local function plugin(base)
    return setmetatable({
        settings = { base_url = base or "http://192.168.10.11:8765", api_key = "test-credential" },
        ui = { handleEvent = function(_, event)
            if event == "SetDimensions" then layouts = layouts + 1 end
        end },
    }, { __index = prototype })
end

local p = plugin()
p:fetchAndDisplay()
assert(p.portrait)
p:startLandscape()
assert(mode == 3 and p.landscape_session.frame.page == "todo" and paints == 1)
p:startAutoRefresh()
assert(not p.auto_refresh_enabled)

local function tap(x, y, widget)
    widget = widget or p.image_widget
    widget.tap(widget, { pos = { x = x, y = y } })
end

tap(100, 100) -- Empty area.
assert(#requests == 1)
local stale_widget = p.image_widget
tap(27, 70)
assert(#requests == 3 and paints == 2 and stale_widget.closed)
tap(27, 70, stale_widget)
assert(#requests == 3)
tap(222, 350)
assert(p.landscape_session.frame.page == "calendar")
tap(280, 350)
assert(p.landscape_session.frame.page == "pomodoro")
fail_fetch = true
tap(22, 350)
assert(p.landscape_session.frame.page == "pomodoro" and not p.image_widget.closed)
fail_fetch = false
fail_render = true
tap(22, 350)
assert(p.landscape_session.frame.page == "pomodoro" and not p.image_widget.closed)
fail_render = false
local session = p.landscape_session
scheduled[session.refresh] = nil
session.refresh()
assert(p.landscape_session.frame.page == "pomodoro")
tap(22, 350)
assert(p.landscape_session.frame.page == "todo")
tap(420, 275)
assert(session.frame.number == 2)
tap(390, 350)
assert(session.frame.page == "muse" and session.frame.number == 1)
tap(420, 275)
assert(session.frame.page == "muse" and session.frame.number == 2)
scheduled[session.refresh] = nil
session.refresh()
assert(session.frame.page == "muse" and session.frame.number == 2)
local before_power = #requests
fail_suspend = true
tap(460, 333)
assert(suspend_calls == 1 and not session.suspend_requested and scheduled[session.refresh] == 30)
assert(light_on and brightness == 12 and not topmost and not session.sleep)
fail_suspend = false
tap(460, 333)
tap(511, 378)
assert(suspend_calls == 2 and #requests == before_power and scheduled[session.suspend_timeout] == 8)
assert(not scheduled[session.refresh] and not light_on and topmost)
session.suspend_timeout() -- No lifecycle event, so the control must become tappable again.
assert(not session.suspend_requested and scheduled[session.refresh] == 30)
assert(light_on and brightness == 12 and not topmost and not session.sleep)
tap(511, 378)
assert(suspend_calls == 3 and session.suspend_requested and not light_on)
local original_sleep_screen = topmost
mode = 0 -- The native screensaver may switch to portrait and place its own widget on top.
topmost = { native = true }
p.image_widget.lifecycle(p.image_widget, true)
p:onSuspend() -- Receiving the same event through both KOReader paths is safe.
assert(not scheduled[session.refresh] and session.suspended and not scheduled[session.suspend_timeout])
runNextTick()
assert(original_sleep_screen.closed and topmost[1].dimen.w == 379 and not light_on)
mode = 3 -- KOReader restores the dashboard orientation before broadcasting Resume.
brightness = 5 -- Verify the saved brightness is restored even if the native setting changed.
p.image_widget.lifecycle(p.image_widget, false)
p:onResume()
assert(scheduled[session.refresh] == 30 and not session.suspended and light_on and brightness == 12)
runNextTick()
assert(not topmost and not session.sleep)
scheduled[session.refresh] = nil
session.refresh()
assert(session.frame.page == "muse" and session.frame.number == 2)
light_on = false
tap(511, 378)
assert(suspend_calls == 4 and session.suspend_requested and not light_on)
p:onSuspend()
runNextTick()
light_on = true -- Simulate a firmware wake that turned on an originally off light.
p:onResume()
runNextTick()
assert(not light_on and brightness == 12 and not topmost)
tap(22, 350)
assert(session.frame.page == "todo" and session.frame.number == 2)
offline = true
tap(27, 70)
local before = #requests
tap(27, 70)
assert(#requests == before and pending_wifi)
p:onSuspend()
assert(not scheduled[session.refresh])
local callback = pending_wifi
pending_wifi = nil
callback() -- Late callback after suspension must have no effect.
assert(#requests == before)
p:onResume()
assert(scheduled[session.refresh])
local current_widget = p.image_widget
stale_widget.exit(stale_widget, { ges = "hold" })
assert(#next_ticks == 0 and p.landscape_session == session)
current_widget.exit(current_widget, { ges = "hold_release" })
current_widget.exit(current_widget, { ges = "hold" })
assert(#next_ticks == 1 and p.landscape_session == session)
runNextTick()
assert(completed_refreshes == paints)
assert(mode == 0 and layouts == 2 and not p.landscape_session and not p.image_widget)
assert(not scheduled[session.refresh])
local captured = table.concat(logs, "\n")
for _, message in ipairs({
    "fixture-version", "power button tapped", "requesting UIManager suspend", "suspend request rejected",
    "no Suspend event", "Suspend event image widget", "Resume event image widget",
    "long-press event hold_release", "orientation restored 0",
    "frontlight off for sleep", "frontlight state restored",
}) do
    assert(captured:find(message, 1, true), message)
end

local invalid = plugin("http://example.com")
invalid:startLandscape()
assert(invalid.error and not invalid.landscape_session)
local edge = { x = 10, y = 10, w = 512, h = 379 }
local frame = { width = 1024, height = 758, regions = { task } }
assert(landscape.hit(frame, edge, 30, 68) == task)
assert(not landscape.hit(frame, edge, 30, 108))
assert(not landscape.hit(frame, edge, 9, 68))
