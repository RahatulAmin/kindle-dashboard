local mode, pending_wifi, offline, fail_fetch, fail_render = 0, nil, false, false, false
local requests, paints, layouts, completed_refreshes = {}, 0, 0, 0
local scheduled = {}
local width, height = 1024, 758
local task = { x = 40, y = 115, w = 85, h = 81, action = "complete",
    task_id = 9, completed = true, capability = "test-capability" }
local tabs = {}
for index, page in ipairs({ "todo", "calendar", "pomodoro" }) do
    tabs[index] = { x = (index-1)*341, y = 666, w = 341, h = 92,
        action = "navigate", page = page, number = 1 }
end

local function stub(name, value)
    package.loaded[name] = value
end

local function screenWidth() return mode % 2 == 1 and 512 or 379 end
local function screenHeight() return mode % 2 == 1 and 379 or 512 end
local screen = {
    DEVICE_ROTATED_CLOCKWISE = 1, getWidth = screenWidth, getHeight = screenHeight,
    getRotationMode = function() return mode end,
    setRotationMode = function(_, target) mode = target end,
    getSize = function() return { w = screenWidth(), h = screenHeight() } end,
}
stub("device", { screen = screen, isTouchDevice = function() return true end,
    hasBattery = function() return true end,
    getPowerDevice = function() return { getCapacity = function() return 71 end } end,
})
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
        assert(seconds == 30 and not scheduled[callback])
        scheduled[callback] = true
    end,
    unschedule = function(_, callback) scheduled[callback] = nil end,
    close = function(_, widget) widget.closed = true end,
    setDirty = function() end,
    forceRePaint = function() paints = paints + 1 end,
    waitForVSync = function() completed_refreshes = completed_refreshes + 1 end,
})
stub("socketutil", { set_timeout = function() end, reset_timeout = function() end })
stub("ltn12", { source = { string = function(body) return function() return body end end } })
stub("logger", { warn = function() end })
local png = "\137PNG\r\n\26\n\0\0\0\13IHDR\0\0\4\0\0\0\2\246"
stub("mime", { unb64 = function() return png end })
stub("json", {
    encode = function(data)
        assert(data.completed == true and data.capability == "test-capability")
        return "completion"
    end,
    decode = function(page)
        local regions = { tabs[1], tabs[2], tabs[3] }
        if page == "todo" then regions[4] = task end
        return {
            page = page, number = 1, width = width, height = height, filename = "landscape-abcd.png",
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
    options.sink(assert(options.url:match("page=(%a+)")))
    return 1, 200
end })

local landscape = dofile("kindle-koreader/landscape.lua")
local prototype = {
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
            tap = interaction.tap, exit = interaction.close,
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
assert(mode == 1 and p.landscape_session.frame.page == "todo" and paints == 1)
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
tap(420, 350)
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
p.image_widget.exit()
assert(completed_refreshes == paints)
assert(mode == 0 and layouts == 2 and not p.landscape_session and not p.image_widget)
assert(not scheduled[session.refresh])

local invalid = plugin("http://example.com")
invalid:startLandscape()
assert(invalid.error and not invalid.landscape_session)
local edge = { x = 10, y = 10, w = 512, h = 379 }
local frame = { width = 1024, height = 758, regions = { task } }
assert(landscape.hit(frame, edge, 30, 68) == task)
assert(not landscape.hit(frame, edge, 30, 108))
assert(not landscape.hit(frame, edge, 9, 68))
