local Device = require("device")
local Event = require("ui/event")
local JSON = require("json")
local NetworkMgr = require("ui/network/manager")
local UIManager = require("ui/uimanager")
local http = require("socket.http")
local ltn12 = require("ltn12")
local mime = require("mime")
local socketutil = require("socketutil")
local logger = require("logger")

local Landscape = {}
local Sleep
local Screen = Device.screen
local PREFIX = "/api/kindle/landscape"
local WIDTH, HEIGHT = 1024, 758
local INTERVAL = 30
local SUSPEND_TIMEOUT = 8
local pages = { todo = true, calendar = true, pomodoro = true, muse = true }

local function privateBase(url)
    if type(url) ~= "string" then return nil end
    local host, port = url:match("^http://([%d.]+):?(%d*)/?$")
    if not host then return nil end
    local a, b, c, d = host:match("^(%d+)%.(%d+)%.(%d+)%.(%d+)$")
    a, b, c, d = tonumber(a), tonumber(b), tonumber(c), tonumber(d)
    if not (a and a <= 255 and b <= 255 and c <= 255 and d <= 255) then return nil end
    local canonical = string.format("%d.%d.%d.%d", a, b, c, d)
    if host ~= canonical then return nil end
    if a == 10 or (a == 172 and b >= 16 and b <= 31) or (a == 192 and b == 168) then
        if port == "" then return "http://" .. canonical end
        local number = tonumber(port)
        if number >= 1 and number <= 65535 then return "http://" .. canonical .. ":" .. number end
    end
end

local function request(session, method, path, payload)
    local chunks, size = {}, 0
    local options = {
        url = session.base .. PREFIX .. path,
        method = method,
        redirect = false,
        headers = { ["access-token"] = session.token, ["Accept"] = "application/json" },
        sink = function(chunk, err)
            if chunk then
                size = size + #chunk
                if size > 1024 * 1024 then return nil, "Response too large" end
                chunks[#chunks + 1] = chunk
            end
            if err then return nil, err end
            return 1
        end,
    }
    if method == "GET" then
        local ok, battery = pcall(function()
            if Device:hasBattery() then return Device:getPowerDevice():getCapacity() end
        end)
        if ok and type(battery) == "number" and battery >= 0 and battery <= 100 then
            options.headers["percent-charged"] = tostring(math.floor(battery + 0.5))
        end
        -- Omit Wi-Fi if the current action may have turned it on temporarily.
        local wifi_ok, wifi_stays_on = pcall(function()
            return NetworkMgr:isConnected() and (not NetworkMgr:getBeforeActionFlag() or
                G_reader_settings:readSetting("wifi_disable_action") == "leave_on")
        end)
        if wifi_ok and wifi_stays_on then options.headers["dashboard-wifi"] = "connected" end
    end
    if payload then
        local body = JSON.encode(payload)
        options.headers["Content-Type"] = "application/json"
        options.headers["Content-Length"] = tostring(#body)
        options.source = ltn12.source.string(body)
    end
    socketutil:set_timeout(6, 12)
    local ok, result, status = pcall(http.request, options)
    socketutil:reset_timeout()
    if ok and result == 1 then return tonumber(status), table.concat(chunks) end
end

local function validNumber(value, min, max)
    return type(value) == "number" and value >= min and value <= max and value % 1 == 0
end

local function decodeFrame(body, page)
    local ok, frame = pcall(JSON.decode, body)
    if not ok or type(frame) ~= "table" or frame.page ~= page or
        not validNumber(frame.number, 1, 2147483647) or frame.width ~= WIDTH or frame.height ~= HEIGHT or
        frame.refresh_rate ~= INTERVAL or type(frame.filename) ~= "string" or
        not frame.filename:match("^landscape%-%x+%.png$") or type(frame.png) ~= "string" or
        type(frame.regions) ~= "table" or #frame.regions < 3 or #frame.regions > 13 then
        return nil
    end
    for _, region in ipairs(frame.regions) do
        if type(region) ~= "table" or not validNumber(region.x, 0, WIDTH - 1) or
            not validNumber(region.y, 0, HEIGHT - 1) or not validNumber(region.w, 1, WIDTH - region.x) or
            not validNumber(region.h, 1, HEIGHT - region.y) then return nil end
        if region.action == "navigate" then
            if not pages[region.page] or not validNumber(region.number, 1, 2147483647) then return nil end
        elseif region.action == "suspend" then
            if region.x ~= 920 or region.y ~= 666 or region.w ~= 104 or region.h ~= 92 then return nil end
        elseif region.action == "complete" then
            if page ~= "todo" or not validNumber(region.task_id, 1, 9007199254740991) or
                type(region.completed) ~= "boolean" or type(region.capability) ~= "string" then return nil end
        else
            return nil
        end
    end
    local png = mime.unb64(frame.png)
    -- Reject a mismatched IHDR before mapping any gestures against the frame.
    if not png or png:sub(1, 8) ~= "\137PNG\r\n\26\n" or
        png:sub(13, 24) ~= "IHDR\0\0\4\0\0\0\2\246" then return nil end
    frame.png = png
    return frame
end

function Landscape.hit(frame, bounds, x, y)
    x, y = x - bounds.x, y - bounds.y
    if x < 0 or y < 0 or x >= bounds.w or y >= bounds.h then return nil end
    x, y = math.floor(x * frame.width / bounds.w), math.floor(y * frame.height / bounds.h)
    for _, region in ipairs(frame.regions) do
        if x >= region.x and x < region.x + region.w and y >= region.y and y < region.y + region.h then
            return region
        end
    end
end

local function schedule(session)
    UIManager:unschedule(session.refresh)
    UIManager:scheduleIn(INTERVAL, session.refresh)
end

local function rotate(plugin, target)
    if Screen:getRotationMode() == target then return end
    Screen:setRotationMode(target)
    local size = Screen:getSize()
    if plugin.ui.onScreenResize then plugin.ui:onScreenResize(size) end
    plugin.ui:handleEvent(Event:new("SetDimensions", size))
    plugin.ui:handleEvent(Event:new("InitScrollPageStates"))
    UIManager:setDirty("all", "full")
end

local function clearSuspendRequest(session)
    session.suspend_requested = nil
    UIManager:unschedule(session.suspend_timeout)
end

local function finishSleep(session, defer_close)
    local state = session.sleep
    if not state then return end
    session.sleep = nil
    -- Kindle's native afterResume reads the light state immediately after its Resume broadcast.
    Sleep.restoreLight(state)
    if defer_close then
        UIManager:nextTick(function() Sleep.closeScreen(state) end)
    else
        Sleep.closeScreen(state)
    end
end

local function lifecycle(plugin, session, asleep, origin)
    if plugin.landscape_session ~= session or session.closing then return end
    logger.info("TRMNL landscape:", asleep and "Suspend event" or "Resume event", origin,
        Screen:getRotationMode())
    clearSuspendRequest(session)
    if asleep then
        local needs_screen = not session.suspended and not session.sleep and session.widget
        session.suspended = true
        if needs_screen then
            -- Some device paths broadcast Suspend without calling Screensaver:show().
            UIManager:nextTick(function()
                if plugin.landscape_session == session and session.suspended and not session.sleep then
                    Sleep.showScreen(session)
                end
            end)
        end
        session.pending = nil
        UIManager:unschedule(session.refresh)
    else
        local repaint = session.suspended and session.widget
        session.suspended = false
        finishSleep(session, true)
        if repaint then
            if Screen:getRotationMode() ~= session.display_rotation then
                rotate(plugin, session.display_rotation)
            end
            UIManager:setDirty(session.widget, "full")
        end
        schedule(session)
    end
end

local function requestSuspend(session)
    logger.info("TRMNL landscape: power button tapped")
    if session.suspend_requested then
        logger.info("TRMNL landscape: suspend already requested")
        return
    end
    if type(Device.canSuspend) ~= "function" or not Device:canSuspend() or type(UIManager.suspend) ~= "function" then
        logger.warn("TRMNL landscape: normal KOReader suspend unavailable")
        return
    end
    session.suspend_requested = true
    session.pending = nil
    UIManager:unschedule(session.refresh)
    UIManager:scheduleIn(SUSPEND_TIMEOUT, session.suspend_timeout)
    logger.info("TRMNL landscape: requesting UIManager suspend")
    local ok, result = pcall(UIManager.suspend, UIManager)
    if not ok or result == false then
        clearSuspendRequest(session)
        finishSleep(session)
        if not session.suspended then schedule(session) end
        logger.warn("TRMNL landscape: suspend request rejected")
    end
end

local function stop(plugin, reason)
    local session = plugin.landscape_session
    if not session then return end
    plugin.landscape_session = nil
    UIManager:unschedule(session.refresh)
    clearSuspendRequest(session)
    finishSleep(session)
    session.uninstall_screensaver()
    if session.widget then
        plugin.image_widget = nil
        if not pcall(UIManager.close, UIManager, session.widget) then
            logger.warn("TRMNL landscape: dashboard widget close failed")
        end
    end
    if session.rotation ~= nil then
        logger.info("TRMNL landscape: restoring orientation", reason, Screen:getRotationMode(), session.rotation)
        local ok = pcall(rotate, plugin, session.rotation)
        if ok and Screen:getRotationMode() == session.rotation then
            logger.info("TRMNL landscape: orientation restored", Screen:getRotationMode())
        else
            logger.warn("TRMNL landscape: orientation restoration incomplete", Screen:getRotationMode())
        end
    end
end

local function fetch(plugin, session, page, number, change)
    if plugin.landscape_session ~= session or session.suspended or session.suspend_requested or
        session.closing or session.pending then return end
    if Device.screen_saver_mode then
        schedule(session)
        return
    end
    UIManager:unschedule(session.refresh)
    local attempt = {}
    session.pending = attempt
    -- The Wi-Fi manager may never invoke its callback after a failed connection.
    UIManager:scheduleIn(INTERVAL, session.refresh)
    NetworkMgr:runWhenConnected(function()
        if plugin.landscape_session ~= session or session.pending ~= attempt or session.suspended or session.closing then
            return
        end
        local ok, reason = pcall(function()
            if change then
                local status = request(session, "PUT", "/tasks/" .. string.format("%.0f", change.task_id) .. "/completion",
                    { completed = change.completed, capability = change.capability })
                -- After a rejected or uncertain update, wait for the normal refresh.
                -- The last successfully displayed image and regions remain paired.
                if status ~= 204 then return end
            end
            local status, body = request(session, "GET", "/frame?page=" .. page .. "&number=" .. number .. "&ui=2")
            local frame = status == 200 and decodeFrame(body, page)
            if not frame then return end
            if session.rotation == nil then
                session.rotation = Screen:getRotationMode()
            end
            if Screen:getWidth() < Screen:getHeight() then
                rotate(plugin, Screen.DEVICE_ROTATED_COUNTER_CLOCKWISE)
            end
            local function handleTap(widget, gesture)
                if session.suspended or session.closing or session.frame ~= frame or session.widget ~= widget or
                    not gesture or not gesture.pos then return end
                local region = Landscape.hit(frame, widget.dimen, gesture.pos.x, gesture.pos.y)
                if Screen:getRotationMode() ~= session.display_rotation or
                    Screen:getWidth() ~= widget.dimen.w or Screen:getHeight() ~= widget.dimen.h then
                    if region and region.action == "suspend" then
                        logger.warn("TRMNL landscape: power tap ignored while screen geometry changed",
                            Screen:getRotationMode(), session.display_rotation)
                    end
                    return
                end
                if not region then return end
                if region.action == "navigate" then
                    local target_number = region.number
                    if frame.page == "muse" and region.page == "todo" then
                        target_number = session.todo_number or target_number
                    end
                    if region.page ~= frame.page or target_number ~= frame.number then
                        fetch(plugin, session, region.page, target_number)
                    end
                elseif region.action == "suspend" then
                    requestSuspend(session)
                else
                    fetch(plugin, session, frame.page, frame.number, region)
                end
            end
            if plugin:displayImage(nil, {
                png = frame.png,
                tap = handleTap,
                close = function(widget, gesture)
                    if session.widget ~= widget or plugin.landscape_session ~= session then return end
                    logger.info("TRMNL landscape: long-press event", gesture and gesture.ges or "unknown")
                    if session.closing then return end
                    session.closing = true
                    UIManager:unschedule(session.refresh)
                    -- Let KOReader finish dispatching the gesture before closing and resizing.
                    UIManager:nextTick(function()
                        if plugin.landscape_session == session then stop(plugin, "long press") end
                    end)
                end,
                lifecycle = function(widget, asleep)
                    if session.widget == widget then lifecycle(plugin, session, asleep, "image widget") end
                end,
            }) then
                session.widget = plugin.image_widget
                UIManager:forceRePaint()
                if UIManager.waitForVSync then UIManager:waitForVSync() end
                session.frame = frame
                if frame.page == "todo" then session.todo_number = frame.number end
                session.display_rotation = Screen:getRotationMode()
                frame.png = nil
            end
        end)
        if not ok then logger.warn("TRMNL landscape frame failed", type(reason)) end
        if not session.widget and session.rotation ~= nil then
            rotate(plugin, session.rotation)
            session.rotation = nil
        end
        session.pending = nil
        NetworkMgr:afterWifiAction()
        if plugin.landscape_session == session and not session.suspended and not session.suspend_requested
            and not session.closing then schedule(session) end
    end)
end

function Landscape.attach(plugin)
    local plugin_dir = plugin:getPluginDir()
    Sleep = dofile(plugin_dir .. "sleep.lua")
    local addToMainMenu = plugin.addToMainMenu
    local onSuspend, onResume, onCloseWidget = plugin.onSuspend, plugin.onResume, plugin.onCloseWidget
    local fetchAndDisplay, startAutoRefresh = plugin.fetchAndDisplay, plugin.startAutoRefresh

    function plugin:startLandscape()
        if self.landscape_session or self.auto_refresh_enabled or self.image_widget then return end
        local base = privateBase(self.settings.base_url)
        local token = self.settings.api_key
        if not Device:isTouchDevice() or not base or not token or token == "" then
            self:showError("Interactive dashboard requires a touchscreen, a private IPv4 HTTP Base URL and an API key.")
            return
        end
        local ok, revision = pcall(function() return require("version"):getCurrentRevision() end)
        logger.info("TRMNL landscape: starting; KOReader revision", ok and revision or "unknown")
        local session = { base = base, token = token, sleep_image = plugin_dir .. "sleep.png" }
        session.suspend_timeout = function()
            if self.landscape_session ~= session or not session.suspend_requested then return end
            clearSuspendRequest(session)
            finishSleep(session)
            logger.warn("TRMNL landscape: no Suspend event; power button can be retried")
            if not session.suspended and not session.closing then schedule(session) end
        end
        session.refresh = function()
            session.pending = nil
            local frame = session.frame
            fetch(self, session, frame and frame.page or "todo", frame and frame.number or 1)
        end
        self.portrait_generation = (self.portrait_generation or 0) + 1
        self.landscape_session = session
        session.uninstall_screensaver = Sleep.install(session, function()
            return self.landscape_session == session and session.widget ~= nil and not session.closing
        end)
        fetch(self, session, "todo", 1)
    end

    function plugin:addToMainMenu(menu_items)
        addToMainMenu(self, menu_items)
        table.insert(menu_items.trmnl.sub_item_table, 1, {
            text = "Start interactive landscape dashboard",
            callback = function() self:startLandscape() end,
        })
        table.insert(menu_items.trmnl.sub_item_table, 2, {
            text = "Stop interactive landscape dashboard",
            show_func = function() return self.landscape_session ~= nil end,
            callback = function() stop(self, "menu") end,
        })
    end

    function plugin:fetchAndDisplay()
        local session = self.landscape_session
        if not session then return fetchAndDisplay(self) end
        local frame = session.frame
        fetch(self, session, frame and frame.page or "todo", frame and frame.number or 1)
    end

    function plugin:startAutoRefresh()
        if not self.landscape_session then return startAutoRefresh(self) end
    end

    function plugin:onSuspend()
        local session = self.landscape_session
        if session then lifecycle(self, session, true, "plugin") end
        onSuspend(self)
    end

    function plugin:onResume()
        local session = self.landscape_session
        if not session then return onResume(self) end
        lifecycle(self, session, false, "plugin")
    end

    function plugin:onCloseWidget()
        stop(self, "plugin close")
        onCloseWidget(self)
    end
end

return Landscape
